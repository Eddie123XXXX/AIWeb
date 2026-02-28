"""
多模态图像入库流水线 (Image Processing Pipeline)

全部使用同一 VLM（默认 Qwen 3.5 Plus）:
  - 初筛 (Triage) → FLOWCHART / CHART / PHOTO / OTHER
  - FLOWCHART → 大模型详细描述（节点、连线、拓扑）
  - CHART → VLM + 提示词提取结构化数据（表格、关键数值、趋势）
  - PHOTO/OTHER → VLM 生成通用描述

防护: 超时降级、CHART 输出 Token 上限、MinIO 原图落盘与元数据。
"""
from __future__ import annotations

import asyncio
import base64
import io
import logging
import os
import uuid
from typing import Any, Optional

logger = logging.getLogger("rag.image_pipeline")

# 初筛类别
IMAGE_TYPE_FLOWCHART = "FLOWCHART"
IMAGE_TYPE_CHART = "CHART"
IMAGE_TYPE_PHOTO = "PHOTO"
IMAGE_TYPE_OTHER = "OTHER"

# 默认配置：qwen3-vl-plus，API 统一使用 QWEN_API_KEY + QWEN_API_BASE
DEFAULT_VLM_MODEL = "qwen3-vl-plus"
# 仅配置 QWEN_API_KEY 未配置 QWEN_API_BASE 时，默认走通义 DashScope 兼容模式，避免误请求到 OpenAI
DEFAULT_QWEN_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
DEFAULT_TIMEOUT = float(os.getenv("RAG_IMAGE_PIPELINE_TIMEOUT", "30"))
CHART_OUTPUT_MAX_TOKENS = int(os.getenv("RAG_IMAGE_CHART_MAX_TOKENS", "1500"))
APPROX_CHARS_PER_TOKEN = 3


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def estimate_tokens(text: str) -> int:
    if not text:
        return 0
    return max(1, len(text) // APPROX_CHARS_PER_TOKEN)


def _truncate_to_tokens(text: str, max_tokens: int, suffix: str = "\n\n[... 已截断]") -> str:
    if estimate_tokens(text) <= max_tokens:
        return text
    max_chars = max_tokens * APPROX_CHARS_PER_TOKEN - len(suffix)
    return text[:max_chars].rstrip() + suffix


# ---------------------------------------------------------------------------
# 获取图像字节（block 内 b64_image / image_bytes）
# ---------------------------------------------------------------------------

def get_image_bytes_from_block(block: dict[str, Any]) -> Optional[bytes]:
    """从 MinerU block 中取出图像字节，便于后续 VLM 调用。"""
    raw = block.get("image_bytes")
    if isinstance(raw, bytes):
        return raw
    b64 = block.get("b64_image") or block.get("base64_image")
    if isinstance(b64, str) and b64.strip():
        try:
            return base64.b64decode(b64)
        except Exception:
            return None
    return None


def upload_image_to_minio(
    image_bytes: bytes,
    document_id: str,
    notebook_id: str,
    *,
    object_prefix: str = "rag/images",
    expires_seconds: int = 86400 * 7,
) -> Optional[str]:
    """
    将图片上传到 MinIO，返回预签名访问 URL。
    用于图片类 block 统一上传，chunk 内容存该 URL。
    """
    try:
        from infra.minio.service import upload_object, get_presigned_url
        ext = "png"
        object_name = f"{object_prefix}/{notebook_id}/{document_id}/{uuid.uuid4().hex}.{ext}"
        upload_object(object_name, io.BytesIO(image_bytes), len(image_bytes), content_type="image/png")
        return get_presigned_url(object_name, expires_seconds=expires_seconds)
    except Exception as e:
        logger.warning("[RAG] 图片上传 MinIO 失败: %s", e)
        return None


# ---------------------------------------------------------------------------
# VLM 视觉调用（OpenAI 兼容：image_url 或 base64）
# ---------------------------------------------------------------------------

async def _call_vision(
    image_bytes: bytes,
    prompt: str,
    *,
    model: Optional[str] = None,
    timeout: float = 30.0,
    max_tokens: int = 1024,
) -> str:
    """调用视觉模型，返回文本。支持 DashScope（qwen3-vl-plus）、通义、OpenAI 等 OpenAI 兼容 API。"""
    try:
        from openai import AsyncOpenAI
    except ImportError:
        logger.warning("[RAG] image_pipeline 需要 openai 包")
        return ""

    model = model or os.getenv("RAG_IMAGE_VLM_MODEL") or os.getenv("RAG_IMAGE_TRIAGE_MODEL") or DEFAULT_VLM_MODEL
    base_url = os.getenv("RAG_IMAGE_VLM_BASE_URL") or os.getenv("QWEN_API_BASE")
    api_key = os.getenv("QWEN_API_KEY", "")
    if not api_key:
        logger.warning("[RAG] 未配置 QWEN_API_KEY，跳过 VLM")
        return ""
    # 未配置 base_url 时默认用通义 DashScope，避免请求误发到 OpenAI 导致 401
    if not base_url:
        base_url = DEFAULT_QWEN_BASE_URL

    client = AsyncOpenAI(api_key=api_key, base_url=base_url)
    b64 = base64.b64encode(image_bytes).decode("ascii")
    data_uri = f"data:image/png;base64,{b64}"

    try:
        resp = await asyncio.wait_for(
            client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "user", "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": data_uri}},
                    ]},
                ],
                max_tokens=max_tokens,
            ),
            timeout=timeout,
        )
        if resp.choices and resp.choices[0].message.content:
            return resp.choices[0].message.content.strip()
    except asyncio.TimeoutError:
        logger.warning("[RAG] VLM 调用超时")
    except Exception as e:
        logger.warning("[RAG] VLM 调用失败: %s", e)
    return ""


# ---------------------------------------------------------------------------
# 1. 初筛 (Triage)
# ---------------------------------------------------------------------------

TRIAGE_PROMPT = """请分析这张图片，仅输出其类别。只能从以下四个词中严格选择一个（只输出一个单词）：
FLOWCHART
CHART
PHOTO
OTHER

说明：FLOWCHART=流程图/架构图/拓扑图/脑图；CHART=柱状图/折线图/饼图/数据图表；PHOTO=普通照片/截图；OTHER=其他。"""


async def classify_image_type(image_bytes: bytes, *, timeout: float = DEFAULT_TIMEOUT) -> str:
    """VLM 初筛：返回 FLOWCHART | CHART | PHOTO | OTHER。使用统一 VLM（默认 Qwen 3.5 Plus）。"""
    model = os.getenv("RAG_IMAGE_TRIAGE_MODEL") or os.getenv("RAG_IMAGE_VLM_MODEL") or DEFAULT_VLM_MODEL
    out = await _call_vision(image_bytes, TRIAGE_PROMPT, model=model, timeout=timeout)
    if not out:
        return IMAGE_TYPE_OTHER
    upper = out.strip().upper()
    for label in (IMAGE_TYPE_FLOWCHART, IMAGE_TYPE_CHART, IMAGE_TYPE_PHOTO, IMAGE_TYPE_OTHER):
        if label in upper or upper == label:
            return label
    return IMAGE_TYPE_OTHER


# ---------------------------------------------------------------------------
# 2. 专家分支
# ---------------------------------------------------------------------------

def _flowchart_prompt(heading_stack: list[str]) -> str:
    ctx = " > ".join(heading_stack) if heading_stack else "无"
    return f"""你是一个资深的架构分析师。请结合这张图所在的文档上下文（章节：{ctx}）：
1. 详细描述该图纸或流程图中包含的所有核心组件/模块。
2. 梳理并列出这些组件之间的连接关系、数据流向或控制逻辑。
3. 请使用专业的工程术语，以 Markdown 列表格式输出。"""


async def describe_flowchart(
    image_bytes: bytes,
    heading_stack: list[str],
    *,
    timeout: float = DEFAULT_TIMEOUT,
) -> str:
    """流程图/架构图：VLM 详细描述（统一 Qwen 3.5 Plus）。"""
    prompt = _flowchart_prompt(heading_stack)
    model = os.getenv("RAG_IMAGE_VLM_MODEL") or DEFAULT_VLM_MODEL
    return await _call_vision(image_bytes, prompt, model=model, timeout=timeout, max_tokens=2048)


CHART_EXTRACT_PROMPT = """这是一张数据类图表（柱状图、折线图、饼图或表格图）。请完成以下任务，便于后续检索与理解：

1. 用 Markdown 表格形式列出图中的主要数据（行列对应图例与坐标）。
2. 简要写出关键数值、占比或趋势结论（一两句话）。
3. 若图中有标题、图例、坐标轴标签，请在描述中体现。

请直接输出：先表格，再简短结论。不要输出与图表无关的内容。"""


async def extract_chart_vlm(
    image_bytes: bytes,
    *,
    max_tokens: int = CHART_OUTPUT_MAX_TOKENS,
    timeout: float = DEFAULT_TIMEOUT,
) -> str:
    """数据图表：使用同一 VLM（Qwen 3.5 Plus）+ 提示词提取结构化数据，并做 Token 上限截断。"""
    model = os.getenv("RAG_IMAGE_VLM_MODEL") or DEFAULT_VLM_MODEL
    raw = await _call_vision(
        image_bytes,
        CHART_EXTRACT_PROMPT,
        model=model,
        timeout=timeout,
        max_tokens=max(1024, max_tokens),
    )
    return _truncate_to_tokens(raw.strip(), max_tokens)


CAPTION_PHOTO_PROMPT = "请生成一段简洁的图片描述，便于检索与理解。"


async def caption_photo(image_bytes: bytes, *, timeout: float = DEFAULT_TIMEOUT) -> str:
    """普通照片/截图：VLM 生成描述（统一 Qwen 3.5 Plus）。"""
    model = os.getenv("RAG_IMAGE_VLM_MODEL") or DEFAULT_VLM_MODEL
    return await _call_vision(image_bytes, CAPTION_PHOTO_PROMPT, model=model, timeout=timeout)


# ---------------------------------------------------------------------------
# 3. 融合 + 4. 落库结构（返回可写入 chunk 的 dict）
# ---------------------------------------------------------------------------

async def process_multimodal_image(
    image_bytes: bytes,
    block: dict[str, Any],
    document_id: str,
    notebook_id: str,
    heading_stack: list[str],
    *,
    timeout: float = DEFAULT_TIMEOUT,
    upload_to_minio: bool = True,
    source_image_url: Optional[str] = None,
    object_prefix: str = "rag/images",
) -> dict[str, Any]:
    """
    单张图片处理：初筛 → 专家分支 → 上下文融合 → 返回 chunk 结构。

    - 超时则降级为仅使用 MinerU 原注 (block.text)。
    - 若传入 source_image_url 则不再上传；否则 upload_to_minio=True 时上传并得到 URL。
    """
    original_caption = (block.get("text") or block.get("content") or "").strip()
    page_idx = block.get("page_idx") or block.get("page_no")
    if isinstance(page_idx, int):
        page_numbers = [page_idx]
    elif isinstance(page_idx, (list, tuple)):
        page_numbers = list(page_idx)
    else:
        page_numbers = []

    if source_image_url is None and upload_to_minio:
        source_image_url = upload_image_to_minio(image_bytes, document_id, notebook_id, object_prefix=object_prefix)

    try:
        result = await asyncio.wait_for(
            _run_pipeline(image_bytes, original_caption, heading_stack, source_image_url),
            timeout=timeout,
        )
    except asyncio.TimeoutError:
        logger.warning("[RAG] 图片 Pipeline 超时，降级为原注")
        result = _fusion_content(original_caption, "", None, source_image_url)

    content = result["content"]
    metadata = result.get("metadata") or {}

    return {
        "id": str(uuid.uuid4()),
        "document_id": document_id,
        "notebook_id": notebook_id,
        "parent_chunk_id": None,
        "chunk_index": 0,
        "content": content,
        "token_count": estimate_tokens(content),
        "chunk_type": "IMAGE_CAPTION",
        "page_numbers": page_numbers,
        "metadata": metadata,
    }


async def _run_pipeline(
    image_bytes: bytes,
    original_caption: str,
    heading_stack: list[str],
    source_image_url: Optional[str],
) -> dict[str, Any]:
    image_type = await classify_image_type(image_bytes)
    extracted = ""
    if image_type == IMAGE_TYPE_FLOWCHART:
        extracted = await describe_flowchart(image_bytes, heading_stack)
    elif image_type == IMAGE_TYPE_CHART:
        extracted = await extract_chart_vlm(image_bytes)
    else:
        extracted = await caption_photo(image_bytes)

    content = _fusion_content(original_caption, extracted, image_type, source_image_url)
    metadata = {
        "image_type_inferred": image_type,
        "source_image_url": source_image_url,
    }
    return {"content": content, "metadata": metadata}


def _fusion_content(
    original_caption: str,
    extracted: str,
    image_type: Optional[str],
    source_image_url: Optional[str],
) -> str:
    parts = ["【图表/图像分析】"]
    if original_caption:
        parts.append(f"原注：{original_caption}")
    if extracted:
        parts.append(f"解析内容：\n{extracted}")
    if not extracted and not original_caption:
        parts.append("（无可用描述）")
    return "\n".join(parts)
