"""
Embedding 服务封装


- Dense Embedding: 通义千问 text-embedding-v4 (DashScope OpenAI 兼容接口)
- 可通过 RAG_EMBEDDING_* 覆盖，默认与 MEMORY_EMBEDDING_MODEL 对齐
- Sparse Embedding: BGE-M3/SPLADE 神经稀疏优先，TF-IDF 仅作降级

设计原则:
- 异步非阻塞
- 批量处理 (batch embedding)
- 统一接口，便于替换底层模型
"""
from __future__ import annotations

import hashlib
import logging
import math
import os
import re
from collections import Counter
from typing import Any

from openai import AsyncOpenAI

logger = logging.getLogger("rag.embedding")

# ---------------------------------------------------------------------------
# Dense Embedding (与 memory 模块一致: 通义千问 text-embedding-v4)
# ---------------------------------------------------------------------------

_dense_client: AsyncOpenAI | None = None


def _get_dense_client() -> AsyncOpenAI:
    """
    与 memory 模块一致：优先使用 Qwen (DashScope) OpenAI 兼容接口。
    若配置 RAG_EMBEDDING_BASE_URL 则覆盖为自定义端点。
    """
    global _dense_client
    if _dense_client is not None:
        return _dense_client

    base_url = os.getenv("RAG_EMBEDDING_BASE_URL")
    if base_url:
        api_key = os.getenv("RAG_EMBEDDING_API_KEY") or os.getenv("OPENAI_API_KEY", "")
        _dense_client = AsyncOpenAI(api_key=api_key, base_url=base_url)
    elif os.getenv("QWEN_API_KEY"):
        api_key = os.getenv("QWEN_API_KEY")
        base_url = os.getenv(
            "QWEN_API_BASE",
            "https://dashscope.aliyuncs.com/compatible-mode/v1",
        )
        _dense_client = AsyncOpenAI(api_key=api_key, base_url=base_url)
    else:
        api_key = os.getenv("OPENAI_API_KEY", "")
        base_url = os.getenv("OPENAI_API_BASE")
        _dense_client = AsyncOpenAI(api_key=api_key, base_url=base_url)
    return _dense_client


def _get_dense_model() -> str:
    return os.getenv("RAG_EMBEDDING_MODEL") or os.getenv("MEMORY_EMBEDDING_MODEL", "text-embedding-v4")


def get_dense_dim() -> int:
    """返回当前 Dense 模型向量维度 (text-embedding-v4 默认 1024，可指定 1536)"""
    return int(os.getenv("RAG_EMBEDDING_DIM", "1536"))


def _get_dense_batch_size() -> int:
    """
    返回 dense embedding 单次请求批大小。

    不同供应商限制差异很大，默认保守为 10，避免 400 InvalidParameter。
    可通过 RAG_EMBEDDING_BATCH_SIZE 覆盖。
    """
    raw = os.getenv("RAG_EMBEDDING_BATCH_SIZE", "10").strip()
    try:
        val = int(raw)
    except Exception:
        val = 10
    return max(1, val)


async def embed_dense(texts: list[str]) -> list[list[float]]:
    """
    批量生成稠密向量。

    自动分批调用，避免超过 API 限制。
    text-embedding-v4 支持 dimensions 参数，默认 1536 以兼容 Milvus schema。
    """
    if not texts:
        return []

    client = _get_dense_client()
    model = _get_dense_model()
    dim = get_dense_dim()
    batch_size = _get_dense_batch_size()
    all_embeddings: list[list[float]] = []

    for i in range(0, len(texts), batch_size):
        batch = texts[i:i + batch_size]
        kwargs: dict[str, Any] = {"model": model, "input": batch}
        if "text-embedding-v" in model:
            kwargs["dimensions"] = dim
        resp = await client.embeddings.create(**kwargs)
        sorted_data = sorted(resp.data, key=lambda x: x.index)
        all_embeddings.extend([d.embedding for d in sorted_data])

    return all_embeddings


async def embed_dense_single(text: str) -> list[float]:
    """单条文本生成稠密向量"""
    results = await embed_dense([text])
    return results[0]


# ---------------------------------------------------------------------------
# Sparse Embedding (神经稀疏向量)
#
# 优先级:
#   1. RAG_SPARSE_EMBEDDING_URL: 自定义 BGE-M3/SPLADE 推理服务
#   2. RAG_SPARSE_PROVIDER=bge_m3: 本地 FlagEmbedding (需 pip install FlagEmbedding)
#   3. TF-IDF: 纯字面统计，仅作降级 (无语义扩展，搜"图像识别"无法命中"计算机视觉")
# ---------------------------------------------------------------------------

_idf_cache: dict[str, float] = {}
_TOKENIZE_RE = re.compile(r"[\w\u4e00-\u9fff]+", re.UNICODE)

# BGE-M3 本地模型 (懒加载)
_bge_m3_model: Any = None


def _tokenize(text: str) -> list[str]:
    """简单分词: 英文单词 + 中文单字"""
    return _TOKENIZE_RE.findall(text.lower())


def _term_to_id(term: str) -> int:
    """将词映射为稳定的正整数 ID (Milvus sparse key 需为 uint32)"""
    h = hashlib.md5(term.encode("utf-8")).hexdigest()
    return int(h[:8], 16)


def _embed_sparse_tfidf(texts: list[str]) -> list[dict[int, float]]:
    """TF-IDF 稀疏向量 (降级用，无语义扩展)"""
    if not texts:
        return []

    all_tokens = [_tokenize(t) for t in texts]
    doc_freq: Counter = Counter()
    for tokens in all_tokens:
        doc_freq.update(set(tokens))

    n_docs = len(texts)
    results: list[dict[int, float]] = []

    for tokens in all_tokens:
        if not tokens:
            results.append({_term_to_id("__empty__"): 0.01})
            continue

        tf = Counter(tokens)
        total = len(tokens)
        sparse: dict[int, float] = {}

        for term, count in tf.items():
            tf_val = count / total
            idf_val = math.log((n_docs + 1) / (doc_freq.get(term, 0) + 1)) + 1.0
            weight = tf_val * idf_val
            if weight > 1e-6:
                sparse[_term_to_id(term)] = round(weight, 6)

        if len(sparse) > 256:
            top_items = sorted(sparse.items(), key=lambda x: x[1], reverse=True)[:256]
            sparse = dict(top_items)

        if not sparse:
            sparse = {_term_to_id("__empty__"): 0.01}

        results.append(sparse)

    return results


async def _embed_sparse_api(texts: list[str]) -> list[dict[int, float]]:
    """调用自定义 BGE-M3/SPLADE 推理服务"""
    import httpx

    url = os.getenv("RAG_SPARSE_EMBEDDING_URL", "").strip().rstrip("/")
    if not url or not url.startswith(("http://", "https://")):
        return []

    if "/encode" not in url and "/embeddings" not in url:
        url = f"{url}/encode" if not url.endswith("/") else f"{url}encode"

    api_key = os.getenv("RAG_SPARSE_EMBEDDING_API_KEY", "").strip()
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    body = {"input": texts} if "embeddings" in url else {"texts": texts}
    if "encode" in url:
        body = body if "texts" in body else {"texts": texts}
        body["return_sparse"] = True

    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(url, json=body, headers=headers)
        resp.raise_for_status()
        data = resp.json()

    results: list[dict[int, float]] = []
    items = data.get("data", data.get("sparse", data.get("results", [])))

    for item in items:
        if isinstance(item, dict):
            if "indices" in item and "values" in item:
                vec = dict(zip(item["indices"], item["values"]))
            else:
                vec = {int(k): float(v) for k, v in item.items() if str(k).isdigit() or isinstance(k, int)}
        elif isinstance(item, list):
            vec = {}
            for sub in item:
                if isinstance(sub, dict):
                    vec.update({int(k): float(v) for k, v in sub.items()})
                elif isinstance(sub, (list, tuple)) and len(sub) >= 2:
                    vec[sub[0]] = float(sub[1])
        else:
            vec = {}

        if len(vec) > 256:
            top_items = sorted(vec.items(), key=lambda x: x[1], reverse=True)[:256]
            vec = dict(top_items)
        if not vec:
            vec = {_term_to_id("__empty__"): 0.01}
        results.append(vec)

    return results


def _embed_sparse_bge_m3_sync(texts: list[str]) -> list[dict[int, float]]:
    """本地 BGE-M3 神经稀疏向量 (需 FlagEmbedding)"""
    global _bge_m3_model
    try:
        from FlagEmbedding import BGEM3FlagModel
    except ImportError:
        logger.warning("[RAG] FlagEmbedding 未安装，Sparse 降级为 TF-IDF。pip install FlagEmbedding 启用 BGE-M3")
        return []

    if _bge_m3_model is None:
        model_name = os.getenv("RAG_SPARSE_BGE_M3_MODEL", "BAAI/bge-m3")
        _bge_m3_model = BGEM3FlagModel(model_name, use_fp16=True)

    output = _bge_m3_model.encode(
        texts,
        return_dense=False,
        return_sparse=True,
        return_colbert_vecs=False,
        max_length=8192,
        batch_size=32,
    )
    lexical = output.get("lexical_weights", output.get("sparse", []))
    if not lexical:
        return []

    results: list[dict[int, float]] = []
    for lw in lexical:
        if hasattr(lw, "items"):
            vec = {int(k): float(v) for k, v in lw.items() if v > 1e-6}
        elif isinstance(lw, (list, tuple)):
            vec = {}
            for t in lw:
                if isinstance(t, (list, tuple)) and len(t) >= 2:
                    vec[int(t[0])] = float(t[1])
        else:
            vec = {}

        if len(vec) > 256:
            top_items = sorted(vec.items(), key=lambda x: x[1], reverse=True)[:256]
            vec = dict(top_items)
        if not vec:
            vec = {_term_to_id("__empty__"): 0.01}
        results.append(vec)

    return results


async def embed_sparse_batch(texts: list[str]) -> list[dict[int, float]]:
    """
    批量生成稀疏向量（神经稀疏优先）。

    优先级: 自定义 API > BGE-M3 本地 > TF-IDF 降级
    返回格式: [{token_id: weight, ...}, ...]，每条保留 top-256 非零维度。
    """
    if not texts:
        return []

    provider = os.getenv("RAG_SPARSE_PROVIDER", "auto").lower()

    # 1. 自定义 API (BGE-M3/SPLADE 推理服务，需完整 URL 含 http(s)://)
    url = os.getenv("RAG_SPARSE_EMBEDDING_URL", "").strip()
    if url and url.startswith(("http://", "https://")):
        try:
            result = await _embed_sparse_api(texts)
            if result and len(result) == len(texts):
                return result
        except Exception as e:
            logger.warning(f"[RAG] Sparse API 失败，降级: {e}")

    # 2. 本地 BGE-M3
    if provider in ("bge_m3", "bge-m3"):
        try:
            import asyncio
            result = await asyncio.to_thread(_embed_sparse_bge_m3_sync, texts)
            if result and len(result) == len(texts):
                return result
        except Exception as e:
            logger.warning(f"[RAG] BGE-M3 失败，降级 TF-IDF: {e}")

    # 3. TF-IDF 降级
    return _embed_sparse_tfidf(texts)


async def embed_sparse_single(text: str) -> dict[int, float]:
    """单条文本生成稀疏向量 (异步)"""
    results = await embed_sparse_batch([text])
    return results[0] if results else {_term_to_id("__empty__"): 0.01}
