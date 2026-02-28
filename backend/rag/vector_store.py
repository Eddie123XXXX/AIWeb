"""
Milvus 混合检索向量存储 (Dense + Sparse)

核心能力:
- 多租户 Collection (notebook_id 作为 partition key)
- HNSW 稠密向量索引 + SPARSE_INVERTED_INDEX 稀疏向量索引
- 混合检索 (hybrid search) 支持 RRF / 加权融合
- 动态 JSON 元数据过滤
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from typing import Any, Optional

from pymilvus import (
    Collection,
    CollectionSchema,
    DataType,
    FieldSchema,
    MilvusException,
    connections,
    utility,
    AnnSearchRequest,
    RRFRanker,
)

logger = logging.getLogger("rag.vector_store")

_collection: Collection | None = None


def _entity_field(entity: Any, key: str, default: Any = "") -> Any:
    """兼容 pymilvus 2.2/2.4: entity 可能是 dict 或 Hit，get() 可能不支持 default 参数"""
    if entity is None:
        return default
    if isinstance(entity, dict):
        return entity.get(key, default)
    try:
        val = getattr(entity, key, None)
        return default if val is None else val
    except Exception:
        return default

COLLECTION_NAME = "enterprise_rag_knowledge"
# 与 embedding 模块一致，text-embedding-v4 默认 1536
DENSE_DIM = 1536


def _get_params() -> dict:
    host = os.getenv("MILVUS_HOST", "localhost")
    port = os.getenv("MILVUS_PORT", "19530")
    return {"host": host, "port": port}


def _env_int(name: str, default: int, min_value: int = 1) -> int:
    raw = os.getenv(name)
    if raw is None:
        return max(min_value, default)
    try:
        return max(min_value, int(raw.strip()))
    except Exception:
        return max(min_value, default)


def _connect(alias: str = "default") -> None:
    params = _get_params()
    connections.connect(alias, **params)


# ---------------------------------------------------------------------------
# Collection 初始化
# ---------------------------------------------------------------------------

def _get_or_create_collection(dense_dim: int = DENSE_DIM) -> Collection:
    global _collection
    if _collection is not None:
        return _collection

    _connect()
    if utility.has_collection(COLLECTION_NAME):
        _collection = Collection(COLLECTION_NAME)
        return _collection

    chunk_id = FieldSchema(
        name="chunk_id",
        dtype=DataType.VARCHAR,
        max_length=36,
        is_primary=True,
    )
    notebook_id = FieldSchema(
        name="notebook_id",
        dtype=DataType.VARCHAR,
        max_length=36,
        is_partition_key=True,
    )
    document_id = FieldSchema(
        name="document_id",
        dtype=DataType.VARCHAR,
        max_length=36,
    )
    chunk_type = FieldSchema(
        name="chunk_type",
        dtype=DataType.VARCHAR,
        max_length=20,
    )
    metadata = FieldSchema(
        name="metadata",
        dtype=DataType.JSON,
    )
    dense_vector = FieldSchema(
        name="dense_vector",
        dtype=DataType.FLOAT_VECTOR,
        dim=dense_dim,
    )
    sparse_vector = FieldSchema(
        name="sparse_vector",
        dtype=DataType.SPARSE_FLOAT_VECTOR,
    )

    schema = CollectionSchema(
        fields=[chunk_id, notebook_id, document_id, chunk_type, metadata, dense_vector, sparse_vector],
        description="Multi-tenant Hybrid RAG Collection",
        enable_dynamic_field=False,
    )

    coll = Collection(name=COLLECTION_NAME, schema=schema)

    # 稠密向量索引 (HNSW)
    coll.create_index(
        field_name="dense_vector",
        index_params={
            "metric_type": "COSINE",
            "index_type": "HNSW",
            "params": {"M": 16, "efConstruction": 256},
        },
    )

    # 稀疏向量索引 (SPARSE_INVERTED_INDEX)
    coll.create_index(
        field_name="sparse_vector",
        index_params={
            "metric_type": "IP",
            "index_type": "SPARSE_INVERTED_INDEX",
            "params": {"drop_ratio_build": 0.2},
        },
    )

    logger.info(f"[RAG] Milvus collection '{COLLECTION_NAME}' created with hybrid indexes")
    _collection = coll
    return _collection


# ---------------------------------------------------------------------------
# 写入
# ---------------------------------------------------------------------------

async def upsert_chunks(
    *,
    chunk_ids: list[str],
    notebook_ids: list[str],
    document_ids: list[str],
    chunk_types: list[str],
    metadatas: list[dict[str, Any]],
    dense_vectors: list[list[float]],
    sparse_vectors: list[dict[int, float]],
) -> int:
    """
    批量写入切片向量到 Milvus。

    sparse_vectors: 稀疏向量，格式为 [{token_id: weight, ...}, ...}
    """
    if not chunk_ids:
        return 0

    total = len(chunk_ids)
    if not (
        len(notebook_ids) == total
        and len(document_ids) == total
        and len(chunk_types) == total
        and len(metadatas) == total
        and len(dense_vectors) == total
        and len(sparse_vectors) == total
    ):
        raise ValueError("Milvus upsert 参数长度不一致")

    dense_dim = len(dense_vectors[0])
    batch_size = _env_int("RAG_MILVUS_UPSERT_BATCH_SIZE", 200, min_value=1)
    max_retries = _env_int("RAG_MILVUS_UPSERT_RETRIES", 2, min_value=0)
    retry_delay_ms = _env_int("RAG_MILVUS_UPSERT_RETRY_DELAY_MS", 800, min_value=100)
    flush_each_write = os.getenv("RAG_MILVUS_FLUSH_EACH_WRITE", "true").lower() in ("true", "1", "yes")

    def _insert():
        global _collection
        coll = _get_or_create_collection(dense_dim=dense_dim)
        inserted = 0

        for start in range(0, total, batch_size):
            end = min(start + batch_size, total)
            entities = [
                chunk_ids[start:end],
                notebook_ids[start:end],
                document_ids[start:end],
                chunk_types[start:end],
                metadatas[start:end],
                dense_vectors[start:end],
                sparse_vectors[start:end],
            ]

            attempt = 0
            while True:
                try:
                    coll.insert(entities)
                    if flush_each_write:
                        coll.flush()
                    inserted += (end - start)
                    break
                except MilvusException as e:
                    if attempt >= max_retries:
                        raise
                    logger.warning(
                        "[RAG] Milvus 批量写入失败，准备重试: "
                        f"batch={start}:{end}, attempt={attempt + 1}/{max_retries + 1}, err={e}"
                    )
                    # 强制重连并指数退避，提升 Milvus 短暂抖动时的成功率
                    try:
                        connections.disconnect("default")
                    except Exception:
                        pass
                    _collection = None
                    time.sleep((retry_delay_ms * (2 ** attempt)) / 1000.0)
                    _connect()
                    coll = _get_or_create_collection(dense_dim=dense_dim)
                    attempt += 1

        return inserted

    return await asyncio.to_thread(_insert)


# ---------------------------------------------------------------------------
# 混合检索 (Dense + Sparse)
# ---------------------------------------------------------------------------

async def hybrid_search(
    *,
    dense_query: list[float],
    sparse_query: dict[int, float],
    notebook_id: str,
    document_ids: Optional[list[str]] = None,
    chunk_types: Optional[list[str]] = None,
    metadata_filter: Optional[str] = None,
    top_k: int = 10,
) -> list[dict[str, Any]]:
    """
    执行 Dense + Sparse 混合检索，使用 RRF (Reciprocal Rank Fusion) 融合排序。

    返回 [{chunk_id, document_id, chunk_type, metadata, score}, ...]
    """
    coll = _get_or_create_collection()

    # 构建过滤表达式
    expr_parts = [f"notebook_id == '{notebook_id}'"]
    if document_ids:
        ids_str = ", ".join(f"'{d}'" for d in document_ids)
        expr_parts.append(f"document_id in [{ids_str}]")
    if chunk_types:
        types_str = ", ".join(f"'{t}'" for t in chunk_types)
        expr_parts.append(f"chunk_type in [{types_str}]")
    if metadata_filter:
        expr_parts.append(metadata_filter)
    expr = " and ".join(expr_parts)

    def _search():
        coll.load()

        dense_req = AnnSearchRequest(
            data=[dense_query],
            anns_field="dense_vector",
            param={"metric_type": "COSINE", "params": {"ef": 128}},
            limit=top_k,
            expr=expr,
        )

        sparse_req = AnnSearchRequest(
            data=[sparse_query],
            anns_field="sparse_vector",
            param={"metric_type": "IP", "params": {}},
            limit=top_k,
            expr=expr,
        )

        ranker = RRFRanker(k=60)

        results = coll.hybrid_search(
            reqs=[dense_req, sparse_req],
            ranker=ranker,
            limit=top_k,
            output_fields=["chunk_id", "document_id", "chunk_type", "metadata"],
        )

        hits = []
        for hit in results[0]:
            entity = getattr(hit, "entity", None)
            hits.append({
                "chunk_id": hit.id,
                "document_id": _entity_field(entity, "document_id", ""),
                "chunk_type": _entity_field(entity, "chunk_type", "TEXT"),
                "metadata": _entity_field(entity, "metadata", {}),
                "score": float(hit.distance),
            })
        return hits

    return await asyncio.to_thread(_search)


# ---------------------------------------------------------------------------
# 仅稠密向量检索 (fallback: 未生成稀疏向量时)
# ---------------------------------------------------------------------------

async def dense_search(
    *,
    dense_query: list[float],
    notebook_id: str,
    document_ids: Optional[list[str]] = None,
    chunk_types: Optional[list[str]] = None,
    top_k: int = 10,
) -> list[dict[str, Any]]:
    """仅使用稠密向量检索 (当稀疏向量不可用时的降级方案)"""
    coll = _get_or_create_collection()

    expr_parts = [f"notebook_id == '{notebook_id}'"]
    if document_ids:
        ids_str = ", ".join(f"'{d}'" for d in document_ids)
        expr_parts.append(f"document_id in [{ids_str}]")
    if chunk_types:
        types_str = ", ".join(f"'{t}'" for t in chunk_types)
        expr_parts.append(f"chunk_type in [{types_str}]")
    expr = " and ".join(expr_parts)

    def _search():
        coll.load()
        results = coll.search(
            data=[dense_query],
            anns_field="dense_vector",
            param={"metric_type": "COSINE", "params": {"ef": 128}},
            limit=top_k,
            expr=expr,
            output_fields=["chunk_id", "document_id", "chunk_type", "metadata"],
        )

        hits = []
        for hit in results[0]:
            entity = getattr(hit, "entity", None)
            hits.append({
                "chunk_id": hit.id,
                "document_id": _entity_field(entity, "document_id", ""),
                "chunk_type": _entity_field(entity, "chunk_type", "TEXT"),
                "metadata": _entity_field(entity, "metadata", {}),
                "score": float(hit.distance),
            })
        return hits

    return await asyncio.to_thread(_search)


# ---------------------------------------------------------------------------
# 仅稀疏向量检索 (三路召回 Path-2: 关键词匹配)
# ---------------------------------------------------------------------------

async def sparse_search(
    *,
    sparse_query: dict[int, float],
    notebook_id: str,
    document_ids: Optional[list[str]] = None,
    chunk_types: Optional[list[str]] = None,
    top_k: int = 10,
) -> list[dict[str, Any]]:
    """
    仅使用稀疏向量检索 (关键词 / 专有名词 / 行业术语精准匹配)。

    稀疏向量 (BGE-M3 / TF-IDF) 本质上是 BM25 的神经网络升级版，
    擅长捕捉字面级别的关键词命中，不会发生语义漂移。
    """
    coll = _get_or_create_collection()

    expr_parts = [f"notebook_id == '{notebook_id}'"]
    if document_ids:
        ids_str = ", ".join(f"'{d}'" for d in document_ids)
        expr_parts.append(f"document_id in [{ids_str}]")
    if chunk_types:
        types_str = ", ".join(f"'{t}'" for t in chunk_types)
        expr_parts.append(f"chunk_type in [{types_str}]")
    expr = " and ".join(expr_parts)

    def _search():
        coll.load()
        results = coll.search(
            data=[sparse_query],
            anns_field="sparse_vector",
            param={"metric_type": "IP", "params": {}},
            limit=top_k,
            expr=expr,
            output_fields=["chunk_id", "document_id", "chunk_type", "metadata"],
        )

        hits = []
        for hit in results[0]:
            entity = getattr(hit, "entity", None)
            hits.append({
                "chunk_id": hit.id,
                "document_id": _entity_field(entity, "document_id", ""),
                "chunk_type": _entity_field(entity, "chunk_type", "TEXT"),
                "metadata": _entity_field(entity, "metadata", {}),
                "score": float(hit.distance),
            })
        return hits

    return await asyncio.to_thread(_search)


# ---------------------------------------------------------------------------
# 删除
# ---------------------------------------------------------------------------

async def delete_by_document(document_id: str) -> int:
    """按 document_id 批量删除向量"""
    _connect()
    if not utility.has_collection(COLLECTION_NAME):
        return 0

    coll = Collection(COLLECTION_NAME)
    expr = f"document_id == '{document_id}'"

    def _delete():
        coll.load()
        res = coll.delete(expr)
        return getattr(res, "delete_count", 0)

    return await asyncio.to_thread(_delete)


async def delete_by_ids(chunk_ids: list[str]) -> int:
    """按 chunk_id 列表删除"""
    if not chunk_ids:
        return 0

    _connect()
    if not utility.has_collection(COLLECTION_NAME):
        return 0

    coll = Collection(COLLECTION_NAME)
    expr = f"chunk_id in {json.dumps(chunk_ids)}"

    def _delete():
        coll.load()
        res = coll.delete(expr)
        return getattr(res, "delete_count", 0)

    return await asyncio.to_thread(_delete)
