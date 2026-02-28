"""
Reranker 精排服务

三段式 Pipeline 第三段：将 RRF 融合后的 Top 20 交给 Reranker 做深度阅读理解，
按及格线过滤，返回所有及格结果 (不设 top 上限)。

支持:
- Jina Rerank API: Cross-Encoder（需 JINA_API_KEY）
- Embedding 降级: 用 Query-Chunk 余弦相似度近似 (无额外依赖，无 API Key 时自动启用)
"""
from __future__ import annotations

import logging
import os
from typing import Any

import httpx

from . import embedding

logger = logging.getLogger("rag.reranker")

JINA_RERANK_URL = "https://api.jina.ai/v1/rerank"


async def rerank(
    query: str,
    documents: list[str],
    top_n: int | None = None,
    rerank_threshold: float | None = 0.2,
    fallback_cosine_threshold: float | None = 0.85,
) -> list[tuple[int, float]]:
    """
    对 documents 按与 query 的语义相关性精排，按及格线过滤。

    重要: Jina Cross-Encoder 与 Embedding 余弦相似度量纲不同！
    - Jina: 绝对相关性 (0~1)，建议 threshold=0.2
    - Embedding 降级: 余弦相似度 (通常 0.7~1.0)，建议 threshold=0.85

    Args:
        query: 用户检索问题
        documents: 待精排的文档列表 (chunk content)
        top_n: 最大返回条数，None 表示仅按及格线过滤、不设上限
        rerank_threshold: Jina 及格线；None 表示不过滤
        fallback_cosine_threshold: Embedding 降级时余弦及格线；None 表示不过滤

    Returns:
        [(original_index, score), ...] 按 score 降序，仅返回及格线以上的结果
    """
    if not documents:
        return []

    api_key = os.getenv("JINA_API_KEY", "").strip()
    if api_key:
        try:
            return await _jina_rerank(query, documents, top_n, rerank_threshold, api_key)
        except Exception as e:
            logger.warning(f"[RAG] Jina Rerank 失败，降级为 Embedding 精排: {e}")

    return await _embedding_rerank(query, documents, top_n, fallback_cosine_threshold)


async def _jina_rerank(
    query: str,
    documents: list[str],
    top_n: int | None,
    threshold: float | None,
    api_key: str,
) -> list[tuple[int, float]]:
    """调用 Jina Rerank API，按及格线过滤，不设 top 上限"""
    model = os.getenv("RAG_RERANKER_MODEL", "jina-reranker-v3")
    # 请求全部文档打分，以便按及格线过滤
    api_top_n = len(documents)
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            JINA_RERANK_URL,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "query": query,
                "documents": documents,
                "top_n": api_top_n,
                "return_documents": False,
            },
        )
        resp.raise_for_status()
        data = resp.json()

    results = data.get("results", [])
    output: list[tuple[int, float]] = []
    for r in results:
        idx = r.get("index", r.get("document", {}).get("index", -1))
        if isinstance(idx, dict):
            idx = idx.get("index", -1)
        score = float(r.get("relevance_score", r.get("score", 0.0)))
        if threshold is not None and score < threshold:
            continue
        output.append((idx, score))

    output.sort(key=lambda x: x[1], reverse=True)
    if top_n is not None:
        output = output[:top_n]
    return output


async def _embedding_rerank(
    query: str,
    documents: list[str],
    top_n: int | None,
    fallback_cosine_threshold: float | None,
) -> list[tuple[int, float]]:
    """
    Embedding 降级精排：Query 与各 Chunk 的余弦相似度，按及格线过滤。
    """
    if not documents:
        return []

    query_vec = await embedding.embed_dense_single(query)
    doc_vecs = await embedding.embed_dense(documents)

    def _cosine(a: list[float], b: list[float]) -> float:
        dot = sum(x * y for x, y in zip(a, b))
        na = sum(x * x for x in a) ** 0.5
        nb = sum(x * x for x in b) ** 0.5
        if na == 0 or nb == 0:
            return 0.0
        return dot / (na * nb)

    scored = [(i, _cosine(query_vec, dv)) for i, dv in enumerate(doc_vecs)]
    scored = [(i, s) for i, s in scored if fallback_cosine_threshold is None or s >= fallback_cosine_threshold]
    scored.sort(key=lambda x: x[1], reverse=True)
    if top_n is not None:
        scored = scored[:top_n]
    return scored
