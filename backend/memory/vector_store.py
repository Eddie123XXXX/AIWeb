import json
import os
from typing import Any

import asyncio
from pymilvus import (
    connections,
    utility,
    FieldSchema,
    CollectionSchema,
    DataType,
    Collection,
)


_collection: Collection | None = None


def _get_params() -> dict:
    host = os.getenv("MILVUS_HOST", "localhost")
    port = os.getenv("MILVUS_PORT", "19530")
    return {"host": host, "port": port}


def _connect(alias: str = "default") -> None:
    """
    按需建立 Milvus 连接（多次调用幂等）。
    """
    params = _get_params()
    connections.connect(alias, **params)


def _get_collection_name() -> str:
    return os.getenv("MILVUS_MEMORY_COLLECTION", "agent_memories_vectors")


def _get_or_create_collection(dim: int | None = None) -> Collection:
    """
    获取（或在第一次调用时创建）用于记忆向量的 collection。

    Schema:
    - id: VARCHAR 主键（与 PostgreSQL agent_memories.id 一致）
    - user_id: INT64（用于按用户过滤）
    - domain: VARCHAR（领域路由过滤）
    - content: VARCHAR（原文本，便于人类阅读）
    - vector: FLOAT_VECTOR(dim)
    """
    global _collection
    if _collection is not None:
        return _collection

    _connect()
    name = _get_collection_name()

    if not utility.has_collection(name):
        if dim is None:
            raise RuntimeError("Milvus collection 尚未创建且未提供向量维度 dim")
        fields = [
            FieldSchema(
                name="id",
                dtype=DataType.VARCHAR,
                is_primary=True,
                auto_id=False,
                max_length=64,
            ),
            FieldSchema(name="user_id", dtype=DataType.INT64),
            FieldSchema(name="domain", dtype=DataType.VARCHAR, max_length=64),
            FieldSchema(name="content", dtype=DataType.VARCHAR, max_length=4096),
            FieldSchema(name="vector", dtype=DataType.FLOAT_VECTOR, dim=dim),
        ]
        schema = CollectionSchema(fields, description="Agent memories vector store")
        coll = Collection(name, schema)
        index_params = {
            "metric_type": "COSINE",
            "index_type": "HNSW",
            "params": {"M": 8, "efConstruction": 64},
        }
        coll.create_index(field_name="vector", index_params=index_params)
        _collection = coll
        return _collection

    _collection = Collection(name)
    return _collection


async def upsert_memories(
    *,
    ids: list[str],
    embeddings: list[list[float]],
    metadatas: list[dict[str, Any]],
) -> None:
    """
    将记忆写入 Milvus。与 PostgreSQL 中的 agent_memories 使用相同的 id。

    - ids: 记忆 ID（UUID 字符串）
    - embeddings: 对应的向量表示
    - metadatas: 至少包含 user_id；可选 content 存原文本便于人类阅读
    """
    if not ids:
        return
    if not embeddings or len(embeddings) != len(ids):
        raise ValueError("embeddings 与 ids 数量不一致")

    dim = len(embeddings[0])
    coll = _get_or_create_collection(dim=dim)

    # 从 metadata 中提取 user_id、domain、content
    user_ids: list[int] = []
    domains: list[str] = []
    contents: list[str] = []
    for md in metadatas:
        if "user_id" not in md:
            raise ValueError("metadatas 中缺少 user_id 字段")
        user_ids.append(int(md["user_id"]))
        domains.append(str(md.get("domain", "general_chat"))[:64])
        contents.append(str(md.get("content", ""))[:4096])

    def _insert():
        coll.load()
        entities = [ids, user_ids, domains, contents, embeddings]
        coll.insert(entities)
        coll.flush()

    await asyncio.to_thread(_insert)


async def query_memories(
    *,
    query_embeddings: list[list[float]],
    where: dict[str, Any] | None = None,
    n_results: int = 50,
) -> dict[str, Any]:
    """
    语义检索，返回与 Chroma 类似的结构：
    {
      "ids": [[id1, id2, ...]],
      "distances": [[d1, d2, ...]],
    }
    """
    if not query_embeddings:
        return {"ids": [[]], "distances": [[]]}

    coll = _get_or_create_collection()

    # 支持 where={"user_id": xxx, "domains": [d1,d2]} 过滤
    expr = None
    if where:
        parts = []
        if "user_id" in where:
            parts.append(f"user_id == {int(where['user_id'])}")
        if "domains" in where and where["domains"]:
            doms = where["domains"]
            if isinstance(doms, (list, tuple)):
                dom_str = ", ".join(f'"{str(d)}"' for d in doms)
                parts.append(f"domain in [{dom_str}]")
        if parts:
            expr = " and ".join(parts)

    def _search():
        coll.load()
        search_params = {"metric_type": "COSINE", "params": {"nprobe": 10}}
        results = coll.search(
            data=query_embeddings,
            anns_field="vector",
            param=search_params,
            limit=n_results,
            expr=expr,
            output_fields=["id", "user_id", "domain", "content"],
        )
        all_ids: list[list[str]] = []
        all_distances: list[list[float]] = []
        for hits in results:
            ids_row: list[str] = []
            dist_row: list[float] = []
            for hit in hits:
                ids_row.append(str(hit.id))
                dist_row.append(float(hit.distance))
            all_ids.append(ids_row)
            all_distances.append(dist_row)
        return {"ids": all_ids, "distances": all_distances}

    return await asyncio.to_thread(_search)


async def delete_memories(*, ids: list[str]) -> int:
    """
    从 Milvus 中删除指定 ID 的记忆向量。

    与 PostgreSQL 软删除配合使用，确保遗忘的记忆在向量库中同步移除，
    避免孤儿向量占用存储并干扰检索。

    - ids: 要删除的记忆 ID 列表（与 agent_memories.id 一致）
    - 返回：实际删除的条数（Milvus 返回的 delete_count）
    """
    if not ids:
        return 0

    _connect()
    name = _get_collection_name()
    if not utility.has_collection(name):
        return 0

    coll = Collection(name)

    # VARCHAR 主键：expr 格式 id in ["uuid1", "uuid2"]
    expr = f"id in {json.dumps(ids)}"

    def _delete():
        coll.load()
        res = coll.delete(expr)
        return getattr(res, "delete_count", 0)

    return await asyncio.to_thread(_delete)

