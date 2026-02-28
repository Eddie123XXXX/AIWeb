"""
RAG 核心业务服务

全流程编排 (版面感知 Layout-Aware Pipeline):
  上传 → SHA-256 防重 → MinIO 存储 → MinerU 结构化解析
  → 版面感知切块 (Parent-Child) → 仅 Child Chunk 做 Dense+Sparse 向量化
  → Milvus 写入 → 状态流转

检索 (小块检索，大块生成):
  Query → Dense+Sparse Embedding → Milvus 混合检索 (只命中 Child)
  → PostgreSQL 回查 Parent 完整上下文 → 组装 Prompt 给 LLM
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import logging
import re
import os
import tempfile
import traceback
import uuid
import zipfile
from io import BytesIO
from typing import Any, Optional

import httpx
from openai import AsyncOpenAI

from . import chunking, embedding, image_pipeline, parsers, vector_store
from .chunk_repository import chunk_repository
from .document_repository import document_repository
from .models import (
    ChunkType,
    DocumentOut,
    DocumentStatus,
    SearchHit,
    SearchRequest,
    SearchResponse,
)

logger = logging.getLogger("rag.service")


# ---------------------------------------------------------------------------
# 辅助: MinIO 操作 (复用 infra.minio.service)
# ---------------------------------------------------------------------------

def _upload_to_minio(object_name: str, data: bytes, content_type: str) -> str:
    from infra.minio.service import upload_object
    upload_object(object_name, BytesIO(data), len(data), content_type=content_type)
    return object_name


def _get_minio_internal_url(storage_path: str) -> str:
    from infra.minio.service import get_presigned_url
    return get_presigned_url(storage_path, expires_seconds=3600)


def _get_minio_public_url(storage_path: str) -> str:
    """生成可供公网拉取的预签名 URL（用于 MinerU 外部 API）。优先使用 MINIO_PUBLIC_ENDPOINT（隧道地址）。"""
    from infra.minio.service import get_presigned_url_for_external
    return get_presigned_url_for_external(storage_path, expires_seconds=3600)


def _get_minio_object(storage_path: str) -> bytes:
    """从 MinIO 下载文件内容"""
    from infra.minio.service import get_object
    data, _ = get_object(storage_path)
    return data


# ---------------------------------------------------------------------------
# 辅助: MinerU 结构化解析（优先外部 API，参考 https://mineru.net/apiManage/docs ）
# ---------------------------------------------------------------------------

# 外部 API 轮询间隔(秒)与最大等待时间(秒)
_MINERU_EXTERNAL_POLL_INTERVAL = 5
_MINERU_EXTERNAL_POLL_TIMEOUT = 600

# ZIP 内图片扩展名（MinerU 常用）
_ZIP_IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp")


def _inject_image_bytes_from_zip(
    zf: zipfile.ZipFile,
    zip_names: list[str],
    content_list: list[dict[str, Any]],
) -> None:
    """
    从 MinerU 外部 API 返回的 ZIP 中读取图片文件，注入到 content_list 里图片类 block 的 image_bytes。
    block 中常见路径字段：img_path, image_path, path, image_save_path, save_path（相对路径如 images/0.png）。
    """
    if not content_list:
        return
    # ZIP 内所有图片条目（按名字排序便于按序匹配）
    image_names = sorted(
        n for n in zip_names
        if not n.endswith("/") and n.lower().endswith(_ZIP_IMAGE_EXTENSIONS)
    )
    if not image_names:
        logger.debug("[RAG] MinerU ZIP 内未发现图片文件")
        return

    def _normalize_path(p: str) -> str:
        return (p or "").strip().replace("\\", "/").lstrip("./")

    def _find_image_in_zip(rel_path: str) -> str | None:
        if not rel_path:
            return None
        norm = _normalize_path(rel_path)
        # 精确或后缀匹配（ZIP 内可能是 task_id/images/0.png）
        for name in image_names:
            nnorm = name.replace("\\", "/")
            if nnorm == norm or nnorm.endswith("/" + norm) or nnorm.endswith(norm):
                return name
        return None

    # 图片类 type（与 chunking.IMAGE_FAMILY + figure/img 等一致）
    image_types = frozenset({
        "image", "image_caption", "image_footnote", "image_body", "figure", "img", "picture",
    })
    path_keys = ("img_path", "image_path", "path", "image_save_path", "save_path", "image_src")

    injected_by_path = 0
    image_blocks_without_bytes: list[int] = []
    for i, block in enumerate(content_list):
        if block.get("image_bytes") or block.get("b64_image") or block.get("base64_image"):
            continue
        raw_type = (block.get("type") or block.get("content_type") or block.get("block_type") or "").strip().lower()
        if raw_type not in image_types and not any(block.get(k) for k in path_keys):
            continue
        rel_path = None
        for k in path_keys:
            v = block.get(k)
            if isinstance(v, str) and v.strip():
                rel_path = v.strip()
                break
        if rel_path:
            zip_member = _find_image_in_zip(rel_path)
            if zip_member:
                try:
                    data = zf.read(zip_member)
                    if data:
                        block["image_bytes"] = data
                        injected_by_path += 1
                except Exception as e:
                    logger.debug("[RAG] ZIP 读取图片失败 %s: %s", zip_member, e)
                continue
        image_blocks_without_bytes.append(i)

    # 按序兜底：未匹配到路径的图片 block 按出现顺序与 ZIP 内图片顺序一一对应
    if image_blocks_without_bytes and image_names:
        used_names: set[str] = set()
        for idx in image_blocks_without_bytes:
            block = content_list[idx]
            if block.get("image_bytes"):
                continue
            for name in image_names:
                if name in used_names:
                    continue
                try:
                    data = zf.read(name)
                    if data:
                        block["image_bytes"] = data
                        used_names.add(name)
                        injected_by_path += 1
                        break
                except Exception:
                    pass

    if injected_by_path:
        logger.info(f"[RAG] MinerU ZIP 已向 content_list 注入 {injected_by_path} 个图片的 image_bytes")
    return None


def _inject_image_bytes_from_local_response(normalized: dict[str, Any], result: dict[str, Any]) -> None:
    """
    从本地 MinerU API 响应的 results.xxx.images 中读取图片 base64，注入到 content_list 的图片 block。
    与外部 API 的 ZIP 注入逻辑一致，使本地也能实现图片上传 MinIO 与召回。
    """
    content_list = normalized.get("content_list")
    if not content_list or not isinstance(content_list, list):
        return
    raw_results = result.get("results")
    if not isinstance(raw_results, dict) or not raw_results:
        return
    first_doc = next(iter(raw_results.values()))
    if not isinstance(first_doc, dict):
        return
    images = first_doc.get("images")
    if not isinstance(images, dict) or not images:
        logger.debug("[RAG] 本地 MinerU 响应中无 results.xxx.images")
        return

    def _decode_b64(s: str) -> bytes | None:
        if not s or not isinstance(s, str):
            return None
        s = s.strip()
        if s.startswith("data:"):
            idx = s.find(",")
            if idx != -1:
                s = s[idx + 1 :]
        try:
            return base64.b64decode(s)
        except Exception:
            return None

    # 建立 文件名 -> 字节 的映射（兼容 key 为 "0.png" 或 "images/0.png"）
    name_to_bytes: dict[str, bytes] = {}
    for k, v in images.items():
        if not isinstance(v, str):
            continue
        decoded = _decode_b64(v)
        if decoded:
            name_to_bytes[k] = decoded
            base_name = k.split("/")[-1] if "/" in k else k
            if base_name not in name_to_bytes:
                name_to_bytes[base_name] = decoded

    image_types = frozenset({"image", "image_caption", "image_footnote", "image_body", "figure", "img", "picture"})
    path_keys = ("img_path", "image_path", "path", "image_save_path", "save_path")
    injected = 0
    for block in content_list:
        if block.get("image_bytes") or block.get("b64_image"):
            continue
        raw_type = (block.get("type") or block.get("content_type") or block.get("block_type") or "").strip().lower()
        if raw_type not in image_types and not any(block.get(k) for k in path_keys):
            continue
        rel_path = None
        for key in path_keys:
            v = block.get(key)
            if isinstance(v, str) and v.strip():
                rel_path = v.strip().replace("\\", "/")
                break
        if rel_path:
            base_name = rel_path.split("/")[-1] if "/" in rel_path else rel_path
            for candidate in (rel_path, base_name, rel_path.lstrip("./")):
                if candidate in name_to_bytes:
                    block["image_bytes"] = name_to_bytes[candidate]
                    injected += 1
                    break

    # 按序兜底：仍未注入的图片 block 与 name_to_bytes 按 key 排序后一一对应
    if name_to_bytes:
        sorted_names = sorted(name_to_bytes.keys(), key=lambda x: (x.count("/"), x))
        used_names: set[str] = set()
        for block in content_list:
            if block.get("image_bytes"):
                continue
            raw_type = (block.get("type") or block.get("content_type") or block.get("block_type") or "").strip().lower()
            if raw_type not in image_types:
                continue
            for name in sorted_names:
                if name in used_names:
                    continue
                block["image_bytes"] = name_to_bytes[name]
                used_names.add(name)
                injected += 1
                break

    if injected:
        logger.info(f"[RAG] 本地 MinerU 已向 content_list 注入 {injected} 个图片的 image_bytes")
    return None


def _normalize_mineru_response(result: dict[str, Any]) -> dict[str, Any]:
    """将 MinerU 返回（含 results 包装）规范为统一 { markdown, content_list } 格式。"""
    normalized = result
    raw_results = result.get("results")
    first = None
    if isinstance(raw_results, list) and raw_results:
        first = raw_results[0]
    elif isinstance(raw_results, dict) and raw_results:
        first = next(iter(raw_results.values()))
    if first is not None and isinstance(first, dict):
        normalized = dict(first)
        if "md" in first and "markdown" not in first:
            normalized["markdown"] = first.get("md", "")
        if "md_content" in first and "markdown" not in first:
            normalized["markdown"] = first.get("md_content", "")
    content_list = normalized.get("content_list", [])
    if isinstance(content_list, str):
        try:
            parsed = json.loads(content_list)
            if isinstance(parsed, list):
                normalized["content_list"] = parsed
            elif isinstance(parsed, dict):
                normalized["content_list"] = parsed.get("content_list") or parsed.get("items") or []
            else:
                normalized["content_list"] = []
        except Exception:
            normalized["content_list"] = []
    return normalized


async def _call_mineru_external_api(file_url: str, filename: str) -> dict[str, Any]:
    """
    调用 MinerU 官方外部 API（mineru.net）解析文档，返回结构化结果。

    参考: https://mineru.net/apiManage/docs
    - 创建任务: POST /api/v4/extract/task，body: url, model_version 等
    - 轮询结果: GET /api/v4/extract/task/{task_id}，完成后返回 full_zip_url
    - 下载 ZIP 后提取 markdown / content_list，规范为与本地 API 一致的结构
    """
    base = os.getenv("MINERU_EXTERNAL_API_BASE_URL", "https://mineru.net").rstrip("/")
    token = (os.getenv("MINERU_API_TOKEN") or "").strip()
    if not token:
        raise ValueError("MINERU_API_TOKEN 未配置，无法使用 MinerU 外部 API")

    # 与本地 MINERU_BACKEND 对齐: pipeline / vlm -> vlm / pipeline / MinerU-HTML
    backend = (os.getenv("MINERU_BACKEND", "pipeline") or "pipeline").strip().lower()
    external_ver = (os.getenv("MINERU_EXTERNAL_MODEL_VERSION") or "").strip()
    if external_ver:
        model_version = external_ver
    elif "vlm" in backend:
        model_version = "vlm"
    elif "html" in backend:
        model_version = "MinerU-HTML"
    else:
        model_version = "pipeline"

    create_url = f"{base}/api/v4/extract/task"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}",
    }
    body = {
        "url": file_url,
        "model_version": model_version,
        "language": "ch",
        "enable_formula": True,
        "enable_table": True,
    }

    logger.info(f"[RAG] MinerU 外部 API 创建任务: url={create_url}, file_url={file_url[:80]}...")
    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(create_url, headers=headers, json=body)
        resp.raise_for_status()
        create_data = resp.json()

    data = create_data.get("data") or create_data
    task_id = data.get("task_id") or data.get("id") or data.get("taskId")
    if not task_id:
        logger.warning(f"[RAG] MinerU 外部 API 未返回 task_id: {list(create_data.keys())}")
        raise ValueError("MinerU 外部 API 未返回任务 ID")

    # 轮询任务结果
    query_url = f"{base}/api/v4/extract/task/{task_id}"
    full_zip_url: Optional[str] = None
    elapsed = 0
    while elapsed < _MINERU_EXTERNAL_POLL_TIMEOUT:
        await asyncio.sleep(_MINERU_EXTERNAL_POLL_INTERVAL)
        elapsed += _MINERU_EXTERNAL_POLL_INTERVAL
        async with httpx.AsyncClient(timeout=30.0) as client:
            q = await client.get(query_url, headers=headers)
            q.raise_for_status()
            task_body = q.json()
        task_data = task_body.get("data") or task_body
        full_zip_url = task_data.get("full_zip_url") or task_data.get("fullZipUrl") or task_data.get("result_url")
        status = (task_data.get("status") or task_data.get("state") or "").lower()
        if full_zip_url:
            break
        if status in ("failed", "error", "failure"):
            raise RuntimeError(f"MinerU 任务失败: {task_data.get('message') or task_data}")
        logger.info(f"[RAG] MinerU 外部 API 轮询: status={status}, elapsed={elapsed}s")

    if not full_zip_url:
        raise RuntimeError("MinerU 外部 API 轮询超时，未获取到解析结果")

    # 下载 ZIP 并提取 markdown / content_list
    async with httpx.AsyncClient(timeout=120.0) as client:
        zip_resp = await client.get(full_zip_url)
        zip_resp.raise_for_status()
        zip_bytes = zip_resp.content

    md_parts: list[str] = []
    content_list: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory() as tmpdir:
        zip_path = os.path.join(tmpdir, "out.zip")
        with open(zip_path, "wb") as f:
            f.write(zip_bytes)
        with zipfile.ZipFile(zip_path, "r") as zf:
            names = sorted(zf.namelist())
            json_names = [n for n in names if n.endswith(".json")]
            for name in names:
                if name.endswith(".md"):
                    with zf.open(name) as f:
                        md_parts.append(f.read().decode("utf-8", errors="replace"))
            # 从任意 JSON 中提取 content_list（mineru.net ZIP 可能带前缀、camelCase、多层包装）
            def _is_likely_block_list(lst: list) -> bool:
                if not lst or not isinstance(lst, list):
                    return False
                first = lst[0]
                if not isinstance(first, dict):
                    return False
                # MinerU block 常见字段：text, type, content, md, page_idx 等
                block_keys = ("text", "type", "content", "md", "page_idx", "content_type")
                return any(k in first for k in block_keys)

            def _extract_content_list_from_obj(obj: Any, depth: int = 0) -> list[dict[str, Any]] | None:
                if depth > 4:
                    return None
                if isinstance(obj, list):
                    return obj if _is_likely_block_list(obj) else None
                if not isinstance(obj, dict):
                    return None
                # 根级多种 key 名（含 camelCase）
                for key in ("content_list", "items", "content_list_v2", "contentList", "blocks", "contentListV2"):
                    cl = obj.get(key)
                    if isinstance(cl, list) and _is_likely_block_list(cl):
                        return cl
                for key in ("results", "data"):
                    wrap = obj.get(key)
                    if isinstance(wrap, list) and _is_likely_block_list(wrap):
                        return wrap
                    if isinstance(wrap, dict) and wrap:
                        for v in wrap.values():
                            out = _extract_content_list_from_obj(v, depth + 1)
                            if out:
                                return out
                # 单键包装递归：{ "uuid": { ... } } 或 { "uuid": [ ... ] }
                if len(obj) == 1:
                    only = next(iter(obj.values()))
                    return _extract_content_list_from_obj(only, depth + 1)
                return None

            for name in json_names:
                try:
                    with zf.open(name) as f:
                        raw = json.load(f)
                    cl = _extract_content_list_from_obj(raw)
                    if isinstance(cl, list) and cl:
                        content_list = cl
                        logger.info(f"[RAG] MinerU 外部 API 从 ZIP 内 {name} 解析到 content_list: {len(cl)} blocks")
                        break
                except Exception as e:
                    logger.debug(f"[RAG] ZIP 内 {name} 解析跳过: {e}")

            # 从 ZIP 内读取图片文件并注入到 content_list 的 image block（block 中常为 img_path/image_path 等相对路径）
            _inject_image_bytes_from_zip(zf, names, content_list)

            # 诊断：content_list 相关文件名仍未解析到时，打印实际结构便于排查
            if not content_list:
                for name in json_names:
                    if "content_list" in name.lower():
                        try:
                            with zf.open(name) as f:
                                raw = json.load(f)
                            if isinstance(raw, dict):
                                keys = list(raw.keys())
                                first_val = raw[keys[0]] if keys else None
                                sub = isinstance(first_val, dict) and list(first_val.keys()) if first_val else None
                                logger.warning(f"[RAG] MinerU ZIP 诊断 {name}: 根 keys={keys}, 首值类型={type(first_val).__name__}" + (f", 首值 keys={sub}" if sub else ""))
                            else:
                                logger.warning(f"[RAG] MinerU ZIP 诊断 {name}: 根类型={type(raw).__name__}, len={len(raw) if isinstance(raw, (list, dict)) else 'n/a'}")
                        except Exception as e:
                            logger.warning(f"[RAG] MinerU ZIP 诊断 {name} 读取失败: {e}")
                        break
    markdown = "\n\n".join(md_parts) if md_parts else ""
    if not content_list and json_names:
        logger.info(f"[RAG] MinerU 外部 API ZIP 内未找到 content_list，已扫描 JSON: {json_names}")
    normalized = {"markdown": markdown, "content_list": content_list}
    logger.info(f"[RAG] MinerU 外部 API 解析完成: markdown={len(markdown)} chars, content_list={len(content_list)} blocks")
    return normalized


async def _call_mineru_parse(file_data: bytes, filename: str) -> dict[str, Any]:
    """
    调用本地 MinerU Web API 解析 PDF，返回结构化结果。

    MinerU 本地 API: POST /file_parse, multipart/form-data
    - files: 上传的 PDF 文件
    - return_md: 返回 Markdown
    - return_content_list: 返回结构化 content_list
    - lang_list: ch (中英)
    - backend: pipeline (通用多语言)

    兼容策略:
    - 优先取 content_list (结构化 Block)
    - 若无，尝试 pdf_info 等其他字段
    - 最终降级为纯 markdown
    """
    base = os.getenv("MINERU_API_BASE_URL", "http://localhost:9999").rstrip("/")
    url = f"{base}/file_parse"

    files = {"files": (filename, file_data, "application/pdf")}
    # 后端引擎:
    # - pipeline: 经典小模型管线 (默认)
    # - vlm-auto-engine: VLM 模式 (视觉+文本大模型)
    # - hybrid-auto-engine: 混合模式
    mineru_backend = os.getenv("MINERU_BACKEND", "pipeline").strip() or "pipeline"
    data = {
        "return_md": "true",
        "return_content_list": "true",
        "return_images": "true",  # 本地 MinerU 返回图片 base64，便于与 API 路径一致做图片上传与召回
        "lang_list": "ch",
        "backend": mineru_backend,
    }

    logger.info(f"[RAG] 调用 MinerU: url={url}, size={len(file_data)} bytes")
    async with httpx.AsyncClient(timeout=600.0) as client:
        resp = await client.post(url, files=files, data=data)
        resp.raise_for_status()
        result = resp.json()

    if not isinstance(result, dict):
        logger.warning(f"[RAG] MinerU 返回非 dict: {type(result)}")
        return {"markdown": str(result), "content_list": []}

    raw_results = result.get("results")
    rlen = len(raw_results) if isinstance(raw_results, (list, dict)) else "N/A"
    logger.info(f"[RAG] MinerU results 类型: {type(raw_results).__name__}, len={rlen}")
    normalized = _normalize_mineru_response(result)
    _inject_image_bytes_from_local_response(normalized, result)

    cl = normalized.get("content_list", [])
    md_len = len(
        normalized.get("markdown", "")
        or normalized.get("md_content", "")
        or normalized.get("text", "")
        or normalized.get("md", "")
    )
    logger.info(f"[RAG] MinerU 解析完成: content_list={len(cl)} blocks, markdown={md_len} chars")
    return normalized


async def _parse_document(storage_path: str, filename: str) -> dict[str, Any]:
    """
    根据文件类型选择解析器:
    - PDF: MinerU 远程解析。
    - Word/Excel/MD/TXT/MP3 等: 本地解析 (parsers.parse_local)。
    """
    parser_name = parsers.get_parser_for_file(filename)
    if not parser_name:
        raise ValueError(f"不支持的文件类型: {filename}")

    if parser_name == "mineru":
        data = _get_minio_object(storage_path)
        logger.info(f"[RAG] 从 MinIO 拉取 PDF: {len(data)} bytes")

        # 优先使用 MinerU 外部 API（mineru.net），需配置 MINERU_API_TOKEN 且文件 URL 可被公网拉取
        use_external = bool((os.getenv("MINERU_API_TOKEN") or "").strip())
        if use_external:
            try:
                # 优先用 MINIO_PUBLIC_ENDPOINT（隧道）生成可被 mineru.net 拉取的 URL
                file_url = _get_minio_public_url(storage_path)
                # 外部 API 需能访问该 URL，若 MinIO 仅内网可访问会失败，届时自动降级本地
                out = await _call_mineru_external_api(file_url, filename)
                logger.info("[RAG] MinerU 外部 API 解析成功")
                return out
            except Exception as e:
                logger.warning(f"[RAG] MinerU 外部 API 失败 ({e})，降级为本地 MinerU 或 pdfplumber")

        try:
            out = await _call_mineru_parse(data, filename)
            logger.info("[RAG] MinerU 本地解析成功")
            return out
        except Exception as e:
            logger.warning(f"[RAG] MinerU 本地解析失败 ({e})，降级为本地 pdfplumber 解析")
            out = parsers._parse_pdf_local(data)
            cl = out.get("content_list", [])
            md_len = len(out.get("markdown", "") or "")
            logger.info(f"[RAG] pdfplumber 降级完成: content_list={len(cl)} blocks, markdown={md_len} chars")
            return out

    # 其他格式: 下载后本地解析
    data = _get_minio_object(storage_path)
    return parsers.parse_local(data, filename)


def _normalize_page_idx(page_idx: Any) -> list[int]:
    """统一 page_idx 为 list[int]，与 chunking 一致。"""
    if isinstance(page_idx, int):
        return [page_idx]
    if isinstance(page_idx, (list, tuple)):
        return [int(p) for p in page_idx]
    return []


def _normalize_content_list_block(block: dict[str, Any]) -> dict[str, Any]:
    """
    将 content_list 中的单条 block 规范为统一结构，与 pdf_info 路径及外部 API 后续处理一致。
    保证本地 MinerU 与 API 调用后的文件召回逻辑一致。
    """
    raw_type = block.get("type") or block.get("content_type") or block.get("block_type") or "text"
    text = (block.get("text") or block.get("content") or block.get("md") or "").strip()
    page_idx = _normalize_page_idx(block.get("page_idx", block.get("page_no", 0)))
    out: dict[str, Any] = {
        "type": _normalize_block_type(raw_type),
        "text": text,
        "page_idx": page_idx,
    }
    # 保留图片相关字段，供 _preprocess_image_blocks / chunking 使用
    for key in ("image_bytes", "b64_image", "base64_image", "img_path", "image_path", "path", "_image_url"):
        if key in block and block[key] is not None:
            out[key] = block[key]
    for key in ("table_body", "content_type", "block_type"):
        if key in block and block[key] is not None:
            out[key] = block[key]
    return out


def _extract_blocks(mineru_result: dict[str, Any]) -> list[dict[str, Any]]:
    """
    从 MinerU 返回结果中提取结构化 Block 列表。

    按优先级尝试:
    1. content_list — MinerU 标准输出（本地与 API 均统一规范化 block 结构）
    2. pdf_info → 遍历每页的 blocks/preproc_blocks
    3. 空列表 (触发 Markdown 降级)
    """
    # 优先: content_list（统一做 block 规范化，与 API 路径召回逻辑一致）
    if "content_list" in mineru_result:
        blocks = mineru_result["content_list"]
        if isinstance(blocks, str):
            try:
                blocks = json.loads(blocks)
            except Exception:
                blocks = []
        if isinstance(blocks, dict):
            blocks = blocks.get("content_list") or blocks.get("items") or []
        if isinstance(blocks, list) and blocks:
            return [_normalize_content_list_block(b) for b in blocks]

    # 次优: pdf_info (MinerU 某些版本的中间格式)
    pdf_info = mineru_result.get("pdf_info", [])
    if isinstance(pdf_info, list) and pdf_info:
        blocks: list[dict[str, Any]] = []
        for page in pdf_info:
            page_idx = page.get("page_idx", page.get("page_no", 0))
            for key in ("preproc_blocks", "blocks", "layout_dets"):
                raw_blocks = page.get(key, [])
                if not raw_blocks:
                    continue
                for b in raw_blocks:
                    block_type = b.get("type", b.get("category_type", "text"))
                    text = b.get("text", "")
                    if text:
                        blocks.append({
                            "type": _normalize_block_type(block_type),
                            "text": text,
                            "page_idx": page_idx,
                        })
        if blocks:
            return blocks

    return []


def _normalize_block_type(raw_type: Any) -> str:
    """统一各版本 MinerU 的 block type 名称"""
    if isinstance(raw_type, int):
        type_map = {0: "text", 1: "title", 2: "text", 3: "table", 4: "image", 5: "image_caption"}
        return type_map.get(raw_type, "text")
    s = str(raw_type).lower().strip()
    if s in ("title", "heading", "header"):
        return "title"
    if s in ("table",):
        return "table"
    if s in ("image", "figure", "image_body"):
        return "image"
    if s in ("image_caption", "figure_caption", "caption"):
        return "image_caption"
    if s in ("interline_equation", "equation"):
        return "interline_equation"
    return "text"


# ---------------------------------------------------------------------------
# 1. 文档上传
# ---------------------------------------------------------------------------

async def upload_document(
    *,
    notebook_id: str,
    user_id: int,
    filename: str,
    file_data: bytes,
    content_type: str = "application/pdf",
) -> dict[str, Any]:
    """
    上传文档, 返回文档记录。

    流程:
    1. 计算 SHA-256 哈希
    2. 同笔记本防重 (file_hash 唯一索引)
    3. 跨笔记本秒传 (复制切片 + 向量)
    4. 上传到 MinIO
    5. 写入 documents 表 (UPLOADED)
    """
    file_hash = hashlib.sha256(file_data).hexdigest()
    byte_size = len(file_data)

    existing = await document_repository.find_by_notebook_and_hash(notebook_id, file_hash)
    if existing:
        logger.info(f"[RAG] 文档已存在 (同笔记本防重): {existing.get('id')}")
        return existing

    doc_id = str(uuid.uuid4())
    storage_path = f"rag/{notebook_id}/{doc_id}/{filename}"

    _upload_to_minio(storage_path, file_data, content_type)

    donor = await document_repository.find_any_by_hash(file_hash)

    doc = await document_repository.create(
        id=doc_id,
        notebook_id=notebook_id,
        user_id=user_id,
        filename=filename,
        file_hash=file_hash,
        byte_size=byte_size,
        storage_path=storage_path,
    )

    if donor:
        logger.info(f"[RAG] 跨笔记本秒传: 复制 {donor['id']} → {doc_id}")
        try:
            await _clone_from_donor(donor_doc_id=donor["id"], new_doc=doc)
            return await document_repository.get_by_id(doc_id)
        except Exception as e:
            logger.warning(f"[RAG] 秒传失败, 走正常解析流程: {e}")

    return doc


# ---------------------------------------------------------------------------
# 1.5 图片 Pipeline 预处理（VLM 初筛 + 专家分支 + 融合注入 block.text）
# ---------------------------------------------------------------------------

async def _preprocess_image_blocks(
    blocks: list[dict[str, Any]],
    document_id: str,
    notebook_id: str,
) -> list[dict[str, Any]]:
    """
    图片类 block 统一处理：
    1) 有 image bytes 的 block 一律上传 MinIO，并设置 block["_image_url"]，chunk 入库时以该 URL 为内容；
    2) 若开启 RAG_IMAGE_PIPELINE_ENABLE，再跑 VLM 融合并覆盖 block["text"]（可选说明）。
    """
    # 为每个 block 构建到当前为止的 title 栈（用于 pipeline 上下文）
    heading_stacks: list[list[str]] = []
    stack: list[str] = []
    for b in blocks:
        t = (b.get("type") or "").strip().lower()
        if t == "title":
            raw = (b.get("text") or b.get("content") or "").strip()
            if raw:
                stack.append(raw)
        heading_stacks.append(list(stack))

    vlm_enabled = os.getenv("RAG_IMAGE_PIPELINE_ENABLE", "").strip().lower() in ("true", "1", "yes")
    timeout = float(os.getenv("RAG_IMAGE_PIPELINE_TIMEOUT", "30"))

    for i, block in enumerate(blocks):
        btype = (block.get("type") or "").strip().lower()
        if btype not in chunking.IMAGE_FAMILY:
            continue
        image_bytes = image_pipeline.get_image_bytes_from_block(block)
        if not image_bytes:
            continue
        # 1) 图片一律上传 MinIO，chunk 内容存图片 URL
        if not block.get("_image_url"):
            url = image_pipeline.upload_image_to_minio(image_bytes, document_id, notebook_id)
            if url:
                block["_image_url"] = url
        # 2) 可选：VLM 生成/融合说明，写入 block["text"]
        if vlm_enabled:
            try:
                result = await asyncio.wait_for(
                    image_pipeline.process_multimodal_image(
                        image_bytes,
                        block,
                        document_id,
                        notebook_id,
                        heading_stacks[i],
                        timeout=timeout,
                        upload_to_minio=False,
                        source_image_url=block.get("_image_url"),
                    ),
                    timeout=timeout + 5,
                )
                block["text"] = result.get("content", "")
                if result.get("metadata"):
                    block["_image_pipeline_metadata"] = result["metadata"]
            except asyncio.TimeoutError:
                logger.warning("[RAG] 图片 Pipeline 单张超时，保留原注")
            except Exception as e:
                logger.warning("[RAG] 图片 Pipeline 失败，保留原注: %s", e)
    return blocks


# ---------------------------------------------------------------------------
# 2. 版面感知解析 Pipeline
# ---------------------------------------------------------------------------

async def process_document(doc_id: str) -> dict[str, Any]:
    """
    驱动文档全流程:
      UPLOADED → PARSING → PARSED → EMBEDDING → READY / FAILED

    版面感知流程:
    1. 调用 MinerU 获取结构化 JSON
    2. 提取 Block 列表 (或降级为 Markdown 分段)
    3. Layout-Aware Chunking: 标题驱动 Parent-Child 切块
    4. 全量写入 PostgreSQL (Parent + Child)
    5. 仅 Child Chunk 做 Dense+Sparse 向量化写入 Milvus

    幂等: 已 READY 的文档直接返回。
    """
    doc = await document_repository.get_by_id(doc_id)
    if not doc:
        raise ValueError(f"文档不存在: {doc_id}")

    if doc["status"] == "READY":
        return doc

    try:
        # ① UPLOADED → PARSING
        filename = doc.get("filename", "") or doc["storage_path"].split("/")[-1]
        logger.info(f"[RAG] 开始解析: doc_id={doc_id}, filename={filename}")
        await document_repository.update_status(doc_id, "PARSING")

        parse_result = await _parse_document(doc["storage_path"], filename)

        blocks = _extract_blocks(parse_result)
        md_len = len(
            parse_result.get("markdown", "")
            or parse_result.get("md_content", "")
            or parse_result.get("text", "")
            or ""
        )
        logger.info(f"[RAG] 解析完成: blocks={len(blocks)}, markdown_len={md_len}, keys={list(parse_result.keys())}")

        # ② PARSING → PARSED
        await document_repository.update_status(doc_id, "PARSED")

        # ③ 图片 block：一律上传 MinIO 并设 block["_image_url"]；若开启 VLM 再融合说明到 block["text"]
        if blocks:
            blocks = await _preprocess_image_blocks(
                blocks,
                document_id=doc_id,
                notebook_id=doc["notebook_id"],
            )

        # ④ 版面感知切块
        if blocks:
            logger.info(f"[RAG] 结构化切块: {len(blocks)} blocks")
            chunks = chunking.process_mineru_blocks(
                blocks,
                document_id=doc_id,
                notebook_id=doc["notebook_id"],
            )
        else:
            # 降级: 未返回结构化数据，用 Markdown 分段
            markdown = (
                parse_result.get("markdown", "")
                or parse_result.get("md_content", "")
                or parse_result.get("text", "")
            )
            if not markdown:
                await document_repository.update_status(doc_id, "FAILED", error_log="解析返回空内容")
                return await document_repository.get_by_id(doc_id)
            logger.info("[RAG] 降级为 Markdown 切块 (未返回结构化 Block)")
            chunks = chunking.chunk_markdown(markdown, document_id=doc_id, notebook_id=doc["notebook_id"])

        if not chunks:
            await document_repository.update_status(doc_id, "FAILED", error_log="解析后无有效切片")
            return await document_repository.get_by_id(doc_id)

        parent_count = sum(1 for c in chunks if c.is_parent)
        child_count = len(chunks) - parent_count
        logger.info(f"[RAG] 切块完成: {parent_count} parents + {child_count} children")

        # ④ 全量写入 PostgreSQL (Parent + Child)
        await chunk_repository.deactivate_by_document(doc_id)
        logger.info(f"[RAG] 即将写入 PostgreSQL: {len(chunks)} 条切片")
        chunk_dicts = [
            {
                "id": c.id,
                "document_id": c.document_id,
                "notebook_id": c.notebook_id,
                "parent_chunk_id": c.parent_chunk_id,
                "chunk_index": c.chunk_index,
                "page_numbers": c.page_numbers,
                "chunk_type": c.chunk_type,
                "content": c.content,
                "token_count": c.token_count,
            }
            for c in chunks
        ]
        inserted = await chunk_repository.bulk_create(chunk_dicts)
        logger.info(f"[RAG] PostgreSQL 切片已写入: {inserted} 条")

        # ⑤ PARSED → EMBEDDING (仅 Child Chunk)
        await document_repository.update_status(doc_id, "EMBEDDING")

        child_chunks = [c for c in chunks if not c.is_parent]
        if child_chunks:
            logger.info(f"[RAG] 即将向量化并写入 Milvus: {len(child_chunks)} 个 Child Chunk")
            await _embed_children(doc["notebook_id"], child_chunks)
            logger.info(f"[RAG] Milvus 向量已写入: {len(child_chunks)} 条")
        else:
            logger.warning(f"[RAG] 无 Child Chunk 需向量化 (仅 Parent 块)")

        # ⑥ EMBEDDING → READY
        await document_repository.update_status(doc_id, "READY")
        logger.info(f"[RAG] 文档处理完成: {doc_id}, 向量化 {len(child_chunks)} 个 Child Chunk")

        return await document_repository.get_by_id(doc_id)

    except Exception as e:
        error_msg = f"{type(e).__name__}: {e}\n{traceback.format_exc()}"
        logger.error(f"[RAG] 文档处理失败 {doc_id}: {error_msg}")
        await document_repository.update_status(doc_id, "FAILED", error_log=error_msg[:4000])
        return await document_repository.get_by_id(doc_id)


# ---------------------------------------------------------------------------
# 3. 仅 Child Chunk 向量化 (小块检索，大块生成)
# ---------------------------------------------------------------------------

async def _embed_children(notebook_id: str, children: list[chunking.Chunk]) -> None:
    """
    仅对 Child Chunk 做 Dense + Sparse 向量化并写入 Milvus。

    Parent Chunk 不进 Milvus:
    - 长文本做 Embedding 会产生"大百科全书效应"，向量语义模糊
    - Child 短小精悍，语义聚焦，检索命中率极高
    - 召回 Child 后，通过 parent_chunk_id 回查 Parent 给 LLM 完整上下文
    """
    texts = [chunking.get_content_for_embedding(c) for c in children]

    # Dense/Sparse 可并发计算，减少总等待时间
    dense_vectors, sparse_vectors = await asyncio.gather(
        embedding.embed_dense(texts),
        embedding.embed_sparse_batch(texts),
    )

    metadatas = []
    for c in children:
        # 便于在 Milvus 侧直接观察 chunk 文本，存一份可控长度预览
        raw_content = c.content or ""
        content_preview = raw_content if len(raw_content) <= 2000 else raw_content[:2000] + "...[truncated]"
        metadatas.append({
            "page_numbers": c.page_numbers,
            "chunk_index": c.chunk_index,
            "has_parent": c.parent_chunk_id is not None,
            "content_preview": content_preview,
        })

    await vector_store.upsert_chunks(
        chunk_ids=[c.id for c in children],
        notebook_ids=[notebook_id] * len(children),
        document_ids=[c.document_id for c in children],
        chunk_types=[c.chunk_type for c in children],
        metadatas=metadatas,
        dense_vectors=dense_vectors,
        sparse_vectors=sparse_vectors,
    )


# ---------------------------------------------------------------------------
# 4. 跨笔记本秒传
# ---------------------------------------------------------------------------

async def _clone_from_donor(donor_doc_id: str, new_doc: dict[str, Any]) -> None:
    """
    从已就绪的文档复制切片和向量到新文档。

    - 复制 PostgreSQL 切片: Parent + Child 全部复制 (生成新 ID)
    - 复制 Milvus 向量: 仅对 Child Chunk 重新 Embedding 写入
    """
    donor_chunks = await chunk_repository.list_by_document(donor_doc_id, active_only=True)
    if not donor_chunks:
        raise ValueError("Donor 文档无切片数据")

    new_doc_id = new_doc["id"]
    new_notebook_id = new_doc["notebook_id"]
    id_mapping: dict[str, str] = {}

    new_chunks: list[dict[str, Any]] = []
    for dc in donor_chunks:
        new_id = str(uuid.uuid4())
        id_mapping[dc["id"]] = new_id

        new_chunks.append({
            "id": new_id,
            "document_id": new_doc_id,
            "notebook_id": new_notebook_id,
            "parent_chunk_id": None,
            "chunk_index": dc["chunk_index"],
            "page_numbers": dc.get("page_numbers", []),
            "chunk_type": dc.get("chunk_type", "TEXT"),
            "content": dc["content"],
            "token_count": dc.get("token_count", 0),
        })

    # 重映射 parent_chunk_id
    for nc, dc in zip(new_chunks, donor_chunks):
        old_parent = dc.get("parent_chunk_id")
        if old_parent and old_parent in id_mapping:
            nc["parent_chunk_id"] = id_mapping[old_parent]

    await chunk_repository.bulk_create(new_chunks)

    # 仅对 Child Chunk (有 parent_chunk_id 的) 做向量化
    child_chunks = [nc for nc in new_chunks if nc.get("parent_chunk_id") is not None]
    # 也包含没有 parent 的独立小块 (独立段落)
    standalone = [nc for nc in new_chunks if nc.get("parent_chunk_id") is None and nc.get("chunk_type") != "TEXT"]
    embed_chunks = child_chunks + standalone

    # 如果全部都没有 parent (例如很短的文档)，则全量 Embedding
    if not embed_chunks:
        embed_chunks = new_chunks

    if embed_chunks:
        texts = [chunking.get_content_for_embedding(nc) for nc in embed_chunks]
        dense_vectors, sparse_vectors = await asyncio.gather(
            embedding.embed_dense(texts),
            embedding.embed_sparse_batch(texts),
        )

        metadatas = [
            {
                "page_numbers": nc.get("page_numbers", []),
                "chunk_index": nc["chunk_index"],
                "has_parent": nc.get("parent_chunk_id") is not None,
                "content_preview": (
                    nc.get("content", "")
                    if len(nc.get("content", "")) <= 2000
                    else nc.get("content", "")[:2000] + "...[truncated]"
                ),
            }
            for nc in embed_chunks
        ]

        await vector_store.upsert_chunks(
            chunk_ids=[nc["id"] for nc in embed_chunks],
            notebook_ids=[new_notebook_id] * len(embed_chunks),
            document_ids=[new_doc_id] * len(embed_chunks),
            chunk_types=[nc.get("chunk_type", "TEXT") for nc in embed_chunks],
            metadatas=metadatas,
            dense_vectors=dense_vectors,
            sparse_vectors=sparse_vectors,
        )

    await document_repository.update_status(new_doc_id, "READY")
    logger.info(f"[RAG] 秒传完成: {new_doc_id}, {len(new_chunks)} 切片, {len(embed_chunks)} 向量化")


# ---------------------------------------------------------------------------
# 5. 三段式 Pipeline (Recall → RRF → Rerank)
# ---------------------------------------------------------------------------

# 召回阶段：每路 Top-K (大厂标准)
RECALL_DENSE = 60
RECALL_SPARSE = 60
RECALL_EXACT = 10

# RRF 粗排：融合后 Top 20
RRF_TOP = 20
RRF_K = 60


def _rrf_fuse(
    ranked_lists: list[list[tuple[str, float, str]]],
    k: int = RRF_K,
) -> list[tuple[str, float, list[str]]]:
    """
    Reciprocal Rank Fusion (RRF) 多路融合排序。

    每路输入: [(chunk_id, original_score, source_label), ...]
    输出: [(chunk_id, fused_score, [source_labels]), ...] 按融合分降序

    RRF 公式: score(d) = Σ 1 / (k + rank_i(d))
    k=60 是原论文推荐值，对各路排名做倒数加权求和，
    天然平衡不同量纲的打分体系 (如 cosine vs. IP vs. FTS rank)。
    """
    scores: dict[str, float] = {}
    sources: dict[str, set[str]] = {}

    for ranked_list in ranked_lists:
        for rank, (chunk_id, _, source) in enumerate(ranked_list):
            rrf_score = 1.0 / (k + rank + 1)
            scores[chunk_id] = scores.get(chunk_id, 0.0) + rrf_score
            if chunk_id not in sources:
                sources[chunk_id] = set()
            sources[chunk_id].add(source)

    fused = [
        (cid, score, sorted(sources[cid]))
        for cid, score in scores.items()
    ]
    fused.sort(key=lambda x: x[1], reverse=True)
    return fused


async def search(request: SearchRequest) -> SearchResponse:
    """
    三段式 Pipeline：

    第一段：多路召回 (Recall)
      - Milvus Dense Top 60
      - Milvus Sparse Top 60
      - (可选) PostgreSQL 精确匹配 Top 10
      约 100+ 条可能相关的 Chunk，含噪音

    第二段：数学粗排 (RRF Fusion)
      - Python 内存 RRF 合并去重，选出 Top 20
      - 纯数学运算，耗时 < 1ms

    第三段：大模型精排 (Rerank)
      - Top 20 + Query 丢给 Reranker 深度阅读理解
      - 按及格线过滤，返回所有及格结果 (top_k 可选作安全上限)

    最后：Parent-Child 溯源与 LLM 生成
      - 拿及格线以上的结果，去 PostgreSQL 捞出 Parent Chunk
      - 组装进 Prompt 发给 LLM
    """
    import asyncio as aio

    from . import reranker

    # 限定文档范围为空时不做召回（仅勾选的知识源参与检索）
    if request.document_ids is not None and len(request.document_ids) == 0:
        return SearchResponse(query=request.query, hits=[], total=0, path_stats={})

    chunk_types_str = [ct.value for ct in request.chunk_types] if request.chunk_types else None
    path_stats: dict[str, int] = {}

    # ========== 第一段：多路召回 ==========
    tasks: dict[str, aio.Task] = {}

    if request.enable_exact:
        tasks["exact"] = aio.create_task(
            _path_exact(request.query, request.notebook_id, request.document_ids, chunk_types_str, RECALL_EXACT)
        )

    if request.enable_sparse:
        tasks["sparse"] = aio.create_task(
            _path_sparse(request.query, request.notebook_id, request.document_ids, chunk_types_str, RECALL_SPARSE)
        )

    if request.enable_dense:
        tasks["dense"] = aio.create_task(
            _path_dense(request.query, request.notebook_id, request.document_ids, chunk_types_str, RECALL_DENSE)
        )

    ranked_lists: list[list[tuple[str, float, str]]] = []
    for source, task in tasks.items():
        try:
            result = await task
            ranked_lists.append(result)
            path_stats[source] = len(result)
        except Exception as e:
            logger.warning(f"[RAG] Path-{source} 召回失败 (已跳过): {e}")
            path_stats[source] = 0

    if not ranked_lists or all(not rl for rl in ranked_lists):
        return SearchResponse(query=request.query, hits=[], total=0, path_stats=path_stats)

    # ========== 第二段：RRF 粗排 Top 20 ==========
    fused = _rrf_fuse(ranked_lists)
    fused = fused[:RRF_TOP]
    path_stats["rrf_top"] = len(fused)

    if not fused:
        return SearchResponse(query=request.query, hits=[], total=0, path_stats=path_stats)

    # 从 PostgreSQL 获取完整切片内容
    chunk_ids = [cid for cid, _, _ in fused]
    pg_chunks = await chunk_repository.get_by_ids(chunk_ids)
    pg_map = {c["id"]: c for c in pg_chunks}

    # 构建 Reranker 输入 (仅包含 pg 中存在的)
    fused_map = {cid: (rrf_score, sources) for cid, rrf_score, sources in fused}
    ordered_ids = [cid for cid in chunk_ids if pg_map.get(cid)]
    ordered_chunks = [pg_map[cid]["content"] for cid in ordered_ids]

    # ========== 第三段：Reranker 精排 ==========
    if request.enable_rerank and ordered_chunks:
        try:
            # 按及格线过滤，不设 top 上限；top_k 仅作安全上限 (防止过多)
            rerank_results = await reranker.rerank(
                query=request.query,
                documents=ordered_chunks,
                top_n=request.top_k,  # 安全上限，None 则仅按及格线
                rerank_threshold=request.rerank_threshold if request.rerank_threshold is not None else 0.2,
                fallback_cosine_threshold=request.fallback_cosine_threshold if request.fallback_cosine_threshold is not None else 0.85,
            )
            path_stats["rerank_top"] = len(rerank_results)

            final_order: list[tuple[str, float, list[str], float | None]] = []
            for idx, rscore in rerank_results:
                if 0 <= idx < len(ordered_ids):
                    cid = ordered_ids[idx]
                    rrf_score, sources = fused_map.get(cid, (0.0, []))
                    final_order.append((cid, rrf_score, sources, rscore))
        except Exception as e:
            logger.warning(f"[RAG] Reranker 精排失败，降级为 RRF 粗排: {e}")
            path_stats["rerank_top"] = 0
            limit = request.top_k if request.top_k is not None else RRF_TOP
            final_order = [(cid, rrf_score, sources, None) for cid, rrf_score, sources in fused[:limit]]
    else:
        path_stats["rerank_top"] = 0
        limit = request.top_k if request.top_k is not None else RRF_TOP
        final_order = [(cid, rrf_score, sources, None) for cid, rrf_score, sources in fused[:limit]]

    # ========== 最后：Parent-Child 溯源 ==========
    final_ids = [x[0] for x in final_order]
    parent_contents: dict[str, str] = {}
    if request.use_parent:
        child_ids_with_parent = [
            cid for cid in final_ids
            if pg_map.get(cid, {}).get("parent_chunk_id")
        ]
        if child_ids_with_parent:
            parents = await chunk_repository.get_parents_batch(child_ids_with_parent)
            parent_contents = {cid: p.get("content", "") for cid, p in parents.items()}

    hits: list[SearchHit] = []
    for cid, rrf_score, sources, rerank_score in final_order:
        pg = pg_map.get(cid, {})
        if not pg:
            continue

        display_score = rerank_score if rerank_score is not None else rrf_score

        hits.append(SearchHit(
            chunk_id=cid,
            document_id=pg.get("document_id", ""),
            content=pg.get("content", ""),
            chunk_type=ChunkType(pg.get("chunk_type", "TEXT")),
            page_numbers=pg.get("page_numbers", []),
            score=round(display_score, 6),
            rerank_score=round(rerank_score, 6) if rerank_score is not None else None,
            sources=sources,
            parent_content=parent_contents.get(cid),
        ))

    return SearchResponse(
        query=request.query,
        hits=hits,
        total=len(hits),
        path_stats=path_stats,
    )


# ---------------------------------------------------------------------------
# Path-1: 精确匹配 (PostgreSQL FTS + ILIKE)
# ---------------------------------------------------------------------------

async def _path_exact(
    query: str,
    notebook_id: str,
    document_ids: list[str] | None,
    chunk_types: list[str] | None,
    limit: int,
) -> list[tuple[str, float, str]]:
    """PostgreSQL 全文搜索 + ILIKE, 返回 [(chunk_id, fts_rank, 'exact'), ...]"""
    rows = await chunk_repository.fulltext_search(
        query=query,
        notebook_id=notebook_id,
        document_ids=document_ids,
        chunk_types=chunk_types,
        limit=limit,
    )
    return [(r["id"], r.get("fts_rank", 0.5), "exact") for r in rows]


# ---------------------------------------------------------------------------
# Path-2: 关键词匹配 (Milvus Sparse Vector)
# ---------------------------------------------------------------------------

async def _path_sparse(
    query: str,
    notebook_id: str,
    document_ids: list[str] | None,
    chunk_types: list[str] | None,
    limit: int,
) -> list[tuple[str, float, str]]:
    """Milvus 稀疏向量检索, 返回 [(chunk_id, ip_score, 'sparse'), ...]"""
    sparse_query = await embedding.embed_sparse_single(query)
    hits = await vector_store.sparse_search(
        sparse_query=sparse_query,
        notebook_id=notebook_id,
        document_ids=document_ids,
        chunk_types=chunk_types,
        top_k=limit,
    )
    return [(h["chunk_id"], h["score"], "sparse") for h in hits]


# ---------------------------------------------------------------------------
# Path-3: 语义匹配 (Milvus Dense Vector)
# ---------------------------------------------------------------------------

async def _path_dense(
    query: str,
    notebook_id: str,
    document_ids: list[str] | None,
    chunk_types: list[str] | None,
    limit: int,
) -> list[tuple[str, float, str]]:
    """Milvus 稠密向量检索, 返回 [(chunk_id, cosine_score, 'dense'), ...]"""
    dense_query = await embedding.embed_dense_single(query)
    hits = await vector_store.dense_search(
        dense_query=dense_query,
        notebook_id=notebook_id,
        document_ids=document_ids,
        chunk_types=chunk_types,
        top_k=limit,
    )
    return [(h["chunk_id"], h["score"], "dense") for h in hits]


# ---------------------------------------------------------------------------
# 6. 删除文档
# ---------------------------------------------------------------------------

async def delete_document(doc_id: str) -> bool:
    await vector_store.delete_by_document(doc_id)
    return await document_repository.delete(doc_id)


# ---------------------------------------------------------------------------
# 7. 重新解析
# ---------------------------------------------------------------------------

async def reparse_document(doc_id: str) -> dict[str, Any]:
    """
    重新解析文档: 废弃旧切片 + 旧向量, 用最新 MinerU 版本重跑全流程。
    适用: MinerU 算法升级后定向回滚重解析。
    """
    doc = await document_repository.get_by_id(doc_id)
    if not doc:
        raise ValueError(f"文档不存在: {doc_id}")

    await vector_store.delete_by_document(doc_id)
    await chunk_repository.deactivate_by_document(doc_id)
    await document_repository.update_status(doc_id, "UPLOADED")

    return await process_document(doc_id)


# ---------------------------------------------------------------------------
# 8. 文档 Markdown 还原（供「展开文件」预览）
# ---------------------------------------------------------------------------

def _reconstruct_segments(chunks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    按 chunk 列表还原为带类型的片段：父块 (parent) 与独立块 (standalone) 按 chunk_index 排序。
    返回 [ {"type": "parent"|"standalone", "content": "...", "chunk_id": "..."}, ... ]，供前端定位与高亮检索 chunk。
    """
    if not chunks:
        return []
    referenced_parent_ids = {c["parent_chunk_id"] for c in chunks if c.get("parent_chunk_id")}
    parents = [c for c in chunks if c["id"] in referenced_parent_ids]
    standalone = [
        c for c in chunks
        if c.get("parent_chunk_id") is None and c["id"] not in referenced_parent_ids
    ]
    ordered = sorted(parents, key=lambda c: int(c.get("chunk_index", 0))) + sorted(
        standalone, key=lambda c: int(c.get("chunk_index", 0))
    )
    segments = []
    for c in ordered:
        text = (c.get("content") or "").rstrip()
        if not text:
            continue
        seg_type = "parent" if c["id"] in referenced_parent_ids else "standalone"
        segments.append({"type": seg_type, "content": text, "chunk_id": c["id"]})
    return segments


# 将单独一行的图片 URL 转为 Markdown 图片语法，便于前端直接渲染为 <img>
_IMAGE_URL_LINE = re.compile(
    r"^(https?://[^\s]+\.(png|jpg|jpeg|gif|webp|bmp)(?:\?[^\s]*)?)$", re.IGNORECASE
)

# 来源指南：大文档总结时送入 LLM 的最大字符数，避免超长上下文
SUMMARY_MAX_CHARS = int(os.getenv("RAG_SUMMARY_MAX_CHARS", "6000"))

_summary_client: AsyncOpenAI | None = None


def _get_summary_client() -> AsyncOpenAI | None:
    """用于生成文档总结的 LLM 客户端。RAG_SUMMARY_* 优先，其次 DeepSeek（与默认模型 deepseek-chat 一致），再 Qwen / OpenAI。"""
    global _summary_client
    if _summary_client is not None:
        return _summary_client
    base_url = os.getenv("RAG_SUMMARY_BASE_URL")
    if base_url:
        api_key = os.getenv("RAG_SUMMARY_API_KEY") or os.getenv("OPENAI_API_KEY", "")
        _summary_client = AsyncOpenAI(api_key=api_key, base_url=base_url)
        return _summary_client
    if os.getenv("DEEPSEEK_API_KEY"):
        api_key = os.getenv("DEEPSEEK_API_KEY")
        base_url = os.getenv("DEEPSEEK_API_BASE", "https://api.deepseek.com/v1")
        _summary_client = AsyncOpenAI(api_key=api_key, base_url=base_url)
        return _summary_client
    if os.getenv("QWEN_API_KEY"):
        api_key = os.getenv("QWEN_API_KEY")
        base_url = os.getenv(
            "QWEN_API_BASE",
            "https://dashscope.aliyuncs.com/compatible-mode/v1",
        )
        _summary_client = AsyncOpenAI(api_key=api_key, base_url=base_url)
        return _summary_client
    if os.getenv("OPENAI_API_KEY"):
        api_key = os.getenv("OPENAI_API_KEY")
        base_url = os.getenv("OPENAI_API_BASE") or "https://api.openai.com/v1"
        _summary_client = AsyncOpenAI(api_key=api_key, base_url=base_url)
        return _summary_client
    return None


def _get_summary_model() -> str:
    return os.getenv("RAG_SUMMARY_MODEL", "deepseek-chat")


def _build_summary_input(segments: list[dict[str, Any]], max_chars: int) -> str:
    """从 segments 拼出纯文本并截断到 max_chars，供总结用。"""
    parts = [seg.get("content", "").strip() for seg in segments if seg.get("content")]
    text = "\n\n".join(parts)
    if len(text) <= max_chars:
        return text
    return text[:max_chars].rstrip() + "…"


async def _generate_and_save_summary(
    doc_id: str, filename: str, segments: list[dict[str, Any]]
) -> str | None:
    """
    根据 segments 生成 2～4 句话总结并写入 documents.summary。
    大文档会截断到 SUMMARY_MAX_CHARS 再送 LLM，失败时返回 None 不写库。
    """
    if not segments:
        return None
    client = _get_summary_client()
    if not client:
        logger.warning("RAG summary: 未配置 LLM (OPENAI_API_KEY / RAG_SUMMARY_*)，跳过生成")
        return None
    input_text = _build_summary_input(segments, SUMMARY_MAX_CHARS)
    prompt = (
        "你是一位文档总结助手。请根据以下文档内容，用 2～4 句话概括文档的主要内容和用途。"
        "只输出总结文字，不要标题、不要编号、不要其他解释。\n\n---\n\n"
    ) + input_text
    try:
        resp = await client.chat.completions.create(
            model=_get_summary_model(),
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=500,
        )
        summary = (resp.choices[0].message.content or "").strip()
        if not summary:
            return None
        await document_repository.update_summary(doc_id, summary)
        return summary
    except Exception as e:
        logger.warning("RAG summary 生成失败 doc_id=%s: %s", doc_id, e)
        return None


def _ensure_image_urls_as_markdown(md: str) -> str:
    lines = md.split("\n")
    out = []
    for line in lines:
        stripped = line.strip()
        if _IMAGE_URL_LINE.fullmatch(stripped):
            out.append(f"![image]({stripped})")
        else:
            out.append(line)
    return "\n".join(out)


async def get_document_markdown(doc_id: str) -> dict[str, Any]:
    """
    返回文档还原后的片段、文件名及来源指南总结，供前端「展开文件」预览。
    segments: [ {"type": "parent"|"standalone", "content": "markdown"}, ... ]
    summary: 文档总结（若无则异步生成并入库，大文档会截断后再生成）。
    """
    doc = await document_repository.get_by_id(doc_id)
    if not doc:
        raise ValueError("文档不存在")
    filename = doc.get("filename") or "document"
    chunks = await chunk_repository.list_by_document(doc_id, active_only=True)
    if not chunks:
        return {"filename": filename, "segments": [], "summary": doc.get("summary") or ""}
    segments = _reconstruct_segments(chunks)
    for seg in segments:
        seg["content"] = _ensure_image_urls_as_markdown(seg["content"])
    summary = (doc.get("summary") or "").strip()
    if not summary:
        summary = await _generate_and_save_summary(doc_id, filename, segments) or ""
    return {"filename": filename, "segments": segments, "summary": summary}
