"""
RAG 知识库 FastAPI 路由（挂载于 /api/rag）

实现流程概要：上传(防重/秒传)→MinIO；process 触发解析→Block 规范化→切块→PostgreSQL+Milvus；
search 为三段式检索(精确+Sparse+Dense→RRF→Reranker)，支持 document_ids 限定范围；
markdown 返回片段与来源指南(summary)，无则生成并入库。详见 backend/rag/README.md。
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from . import parsers, service
from .chunk_repository import chunk_repository
from .document_repository import document_repository
from .notebook_repository import notebook_repository
from .models import (
    ChunkOut,
    DocumentBrief,
    DocumentOut,
    NotebookCreate,
    NotebookOut,
    SearchRequest,
    SearchResponse,
)

logger = logging.getLogger("rag.router")

router = APIRouter(prefix="/rag", tags=["rag"])

# TODO: 接入真实用户认证后替换为 Depends(get_current_user)
_DEFAULT_USER_ID = 1


# ---------------------------------------------------------------------------
# 笔记本
# ---------------------------------------------------------------------------

@router.get("/notebooks", summary="笔记本列表")
async def list_notebooks(
    user_id: int = _DEFAULT_USER_ID,
    limit: int = 50,
    offset: int = 0,
):
    """按用户查询笔记本列表，含知识源数量与最后更新时间"""
    rows = await notebook_repository.list_by_user(user_id, limit=limit, offset=offset)
    return [
        NotebookOut(
            id=r["id"],
            title=r["title"],
            user_id=r["user_id"],
            source_count=r.get("source_count", 0),
            last_updated=r.get("last_updated"),
            created_at=r["created_at"],
            updated_at=r["updated_at"],
        )
        for r in rows
    ]


@router.post("/notebooks", response_model=NotebookOut, summary="创建笔记本")
async def create_notebook(
    body: NotebookCreate,
    user_id: int = _DEFAULT_USER_ID,
):
    """创建新笔记本，返回 id 供后续上传文档使用"""
    import uuid
    notebook_id = str(uuid.uuid4())
    row = await notebook_repository.create(
        id=notebook_id,
        title=body.title or "未命名笔记本",
        user_id=user_id,
    )
    return NotebookOut(
        id=row["id"],
        title=row["title"],
        user_id=row["user_id"],
        source_count=0,
        last_updated=None,
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


@router.put("/notebooks/{notebook_id}", response_model=NotebookOut, summary="更新笔记本")
async def update_notebook(notebook_id: str, body: NotebookCreate):
    row = await notebook_repository.update(notebook_id, body.title or "未命名笔记本")
    if not row:
        raise HTTPException(status_code=404, detail="笔记本不存在")
    r = await notebook_repository.get_by_id_with_stats(notebook_id)
    if not r:
        raise HTTPException(status_code=404, detail="笔记本不存在")
    return NotebookOut(**r)


@router.delete("/notebooks/{notebook_id}", summary="删除笔记本")
async def delete_notebook(notebook_id: str):
    ok = await notebook_repository.delete(notebook_id)
    if not ok:
        raise HTTPException(status_code=404, detail="笔记本不存在")
    return {"deleted": notebook_id}


# ---------------------------------------------------------------------------
# 上传
# ---------------------------------------------------------------------------

@router.post("/documents/upload", response_model=DocumentOut, summary="上传文档")
async def upload_document(
    file: UploadFile = File(...),
    notebook_id: str = Form(...),
    user_id: int = Form(_DEFAULT_USER_ID),
):
    """
    上传文档到知识库。

    - 自动计算 SHA-256 防重
    - 同笔记本同文件直接返回已有记录
    - 跨笔记本同文件自动秒传 (复制切片 + 向量)
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="文件名不能为空")
    if not parsers.is_supported(file.filename):
        supported = ", ".join(sorted(set(parsers.SUPPORTED_EXTENSIONS.keys())))
        raise HTTPException(
            status_code=400,
            detail=f"不支持的文件类型。支持: {supported}",
        )

    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="文件内容为空")

    content_type = file.content_type or "application/octet-stream"

    try:
        logger.info(f"[RAG] 收到文档上传: {file.filename} -> notebook_id={notebook_id}")
        doc = await service.upload_document(
            notebook_id=notebook_id,
            user_id=user_id,
            filename=file.filename,
            file_data=data,
            content_type=content_type,
        )
        logger.info(f"[RAG] 文档已入库: doc_id={doc.get('id')}, status={doc.get('status')}")
        return DocumentOut(**doc)
    except Exception as e:
        logger.error(f"[RAG] 上传失败: {e}")
        raise HTTPException(status_code=500, detail=f"上传失败: {e}")


# ---------------------------------------------------------------------------
# 解析流水线
# ---------------------------------------------------------------------------

@router.post("/documents/{doc_id}/process", summary="触发解析流水线")
async def process_document(doc_id: str):
    """
    触发文档全流程: MinerU 解析 → 语义切块 → Dense+Sparse 向量化 → Milvus 写入

    - RAG_USE_QUEUE=true 且 Redis 可用时: 任务入队，立即返回 202，客户端轮询 GET /documents/{id} 查看状态
    - 否则: 同步执行，阻塞直到完成

    幂等: 已 READY 的文档直接返回。
    """
    from . import tasks

    doc = await document_repository.get_by_id(doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="文档不存在")
    if doc["status"] == "READY":
        return DocumentOut(**doc)

    logger.info(f"[RAG] 触发解析流水线: doc_id={doc_id}, status={doc.get('status')}")
    use_queue = __import__("os").getenv("RAG_USE_QUEUE", "false").lower() in ("true", "1", "yes")
    if use_queue and tasks.is_queue_available():
        job_id = tasks.enqueue_process_document(doc_id)
        if job_id:
            logger.info(f"[RAG] 任务已入队: doc_id={doc_id}, job_id={job_id} (Worker 将异步处理)")
            await document_repository.update_status(doc_id, "PARSING")
            return {
                "status": "PARSING",
                "message": "任务已入队，请轮询 GET /rag/documents/{doc_id} 查看进度",
                "doc_id": doc_id,
                "job_id": job_id,
            }
        logger.warning("[RAG] 入队失败，降级为同步执行")

    try:
        logger.info(f"[RAG] 同步执行解析: doc_id={doc_id} (MinerU 解析 → 切块 → 向量化)")
        doc = await service.process_document(doc_id)
        if not doc:
            raise HTTPException(status_code=404, detail="文档不存在")
        return DocumentOut(**doc)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"[RAG] 处理失败: {e}")
        raise HTTPException(status_code=500, detail=f"处理失败: {e}")


@router.post("/documents/{doc_id}/reparse", response_model=DocumentOut, summary="重新解析文档")
async def reparse_document(doc_id: str):
    """
    重新解析文档: 废弃旧切片+向量, 用最新 MinerU 版本重跑全流程。
    """
    try:
        doc = await service.reparse_document(doc_id)
        return DocumentOut(**doc)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"[RAG] 重新解析失败: {e}")
        raise HTTPException(status_code=500, detail=f"重新解析失败: {e}")


# ---------------------------------------------------------------------------
# 查询
# ---------------------------------------------------------------------------

@router.get("/documents", response_model=list[DocumentBrief], summary="文档列表")
async def list_documents(
    notebook_id: str,
    limit: int = 50,
    offset: int = 0,
):
    """按笔记本查询文档列表"""
    docs = await document_repository.list_by_notebook(notebook_id, limit=limit, offset=offset)
    return [DocumentBrief(**d) for d in docs]


@router.get("/documents/{doc_id}", response_model=DocumentOut, summary="文档详情")
async def get_document(doc_id: str):
    doc = await document_repository.get_by_id(doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="文档不存在")
    return DocumentOut(**doc)


@router.get("/documents/{doc_id}/chunks", response_model=list[ChunkOut], summary="文档切片列表")
async def list_chunks(doc_id: str, active_only: bool = True):
    """查看文档的所有切片 (含 parent-child 关系)"""
    chunks = await chunk_repository.list_by_document(doc_id, active_only=active_only)
    return [ChunkOut(**c) for c in chunks]


@router.get("/documents/{doc_id}/markdown", summary="文档还原 Markdown + 来源指南（展开文件预览）")
async def get_document_markdown(doc_id: str):
    """
    按 chunk 顺序还原为片段列表供前端预览；含来源指南总结。

    实现：从 PostgreSQL 拉取该文档的 active chunks，按 parent/standalone 与 chunk_index 排序，
    每段返回 type、content、chunk_id（便于前端定位高亮）。若 documents.summary 为空，
    则截断内容（默认 6000 字）调用 LLM 生成总结并写入库。图片 URL 单独行会转为 Markdown 图片语法。

    返回：{ filename, segments: [{ type, content, chunk_id }], summary }。
    """
    try:
        data = await service.get_document_markdown(doc_id)
        return data
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


# ---------------------------------------------------------------------------
# 删除
# ---------------------------------------------------------------------------

@router.delete("/documents/{doc_id}", summary="删除文档")
async def delete_document(doc_id: str):
    """删除文档及其所有切片和向量"""
    ok = await service.delete_document(doc_id)
    if not ok:
        raise HTTPException(status_code=404, detail="文档不存在")
    return {"deleted": doc_id}


# ---------------------------------------------------------------------------
# 诊断
# ---------------------------------------------------------------------------

@router.get("/stats", summary="RAG 数据统计（诊断用）")
async def rag_stats():
    """
    返回文档数、切片数、Milvus 向量数，用于排查「切片未入库」等问题。
    """
    import os
    import asyncpg
    from . import vector_store

    stats = {"documents": {}, "chunks": 0, "milvus_entities": None, "milvus_error": None}
    dsn = (
        f"postgresql://{os.getenv('POSTGRES_USER', 'aiweb')}:{os.getenv('POSTGRES_PASSWORD', 'aiweb')}"
        f"@{os.getenv('POSTGRES_HOST', 'localhost')}:{os.getenv('POSTGRES_PORT', '5432')}/{os.getenv('POSTGRES_DB', 'aiweb')}"
    )
    try:
        conn = await asyncpg.connect(dsn)
        try:
            rows = await conn.fetch(
                "SELECT status, COUNT(*)::int as cnt FROM documents GROUP BY status"
            )
            stats["documents"] = {r["status"]: r["cnt"] for r in rows}
            chunk_row = await conn.fetchrow(
                "SELECT COUNT(*)::int as cnt FROM document_chunks WHERE is_active = TRUE"
            )
            stats["chunks"] = chunk_row["cnt"] if chunk_row else 0
        finally:
            await conn.close()
    except Exception as e:
        stats["db_error"] = str(e)
    try:
        coll = vector_store._get_or_create_collection()
        stats["milvus_entities"] = coll.num_entities
    except Exception as e:
        stats["milvus_error"] = str(e)
    return stats


# ---------------------------------------------------------------------------
# 三路召回检索
# ---------------------------------------------------------------------------

@router.post("/search", response_model=SearchResponse, summary="三段式检索")
async def search_knowledge(body: SearchRequest):
    """
    三段式 Pipeline：多路召回 → RRF 粗排 → Reranker 精排。

    第一段召回:
    - **Path-1 精确匹配** (enable_exact): PostgreSQL FTS + ILIKE,
      适用于特定代码、型号、API 名称等绝对精确的字面查询
    - **Path-2 关键词匹配** (enable_sparse): Milvus Sparse Vector,
      适用于行业术语、专有名词的扩展匹配 (BM25 神经网络升级版)
    - **Path-3 语义匹配** (enable_dense): Milvus Dense Vector,
      适用于意图理解、同义改写、概念关联等模糊语义查询

    第二段: RRF 融合 Top 20；第三段: Reranker 按及格线过滤。

    支持:
    - notebook_id 级租户隔离
    - document_ids 文档范围限定
    - chunk_types 切片类型过滤
    - Parent-Child 上下文扩展 (use_parent=true)
    - 可按需开关任意一路 (enable_exact / enable_sparse / enable_dense / enable_rerank)
    """
    try:
        return await service.search(body)
    except Exception as e:
        logger.error(f"[RAG] 检索失败: {e}")
        raise HTTPException(status_code=500, detail=f"检索失败: {e}")
