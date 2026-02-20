"""
Milvus 服务封装（pymilvus，简单单机测试用）
"""
import os
from typing import Any, List

from pymilvus import (
    connections,
    utility,
    FieldSchema,
    CollectionSchema,
    DataType,
    Collection,
)


def _get_params() -> dict:
    host = os.getenv("MILVUS_HOST", "localhost")
    port = os.getenv("MILVUS_PORT", "19530")
    return {"host": host, "port": port}


def _connect(alias: str = "default") -> None:
    """
    按需建立连接（多次调用是幂等的）。
    """
    params = _get_params()
    connections.connect(alias, **params)


def list_collections() -> list[str]:
    """
    列出已存在的 collection。
    """
    _connect()
    return utility.list_collections()


def create_simple_collection(
    name: str,
    dim: int = 128,
) -> None:
    """
    创建一个最简 collection：
    - id: Int64 主键
    - vector: FloatVector 向量
    """
    _connect()
    if utility.has_collection(name):
        return

    fields = [
        FieldSchema(name="id", dtype=DataType.INT64, is_primary=True, auto_id=True),
        FieldSchema(name="vector", dtype=DataType.FLOAT_VECTOR, dim=dim),
    ]
    schema = CollectionSchema(fields, description="simple vector collection for test")
    Collection(name, schema)


def drop_collection(name: str) -> None:
    """
    删除 collection。
    """
    _connect()
    if utility.has_collection(name):
        utility.drop_collection(name)


def insert_vectors(name: str, vectors: List[List[float]]) -> int:
    """
    向指定 collection 插入向量，返回插入条数。
    Collection 不存在时会自动按默认维度创建（使用 len(vectors[0])）。
    """
    if not vectors:
        return 0

    dim = len(vectors[0])
    create_simple_collection(name, dim=dim)

    _connect()
    coll = Collection(name)
    entities = [
        vectors,  # 只插入向量，由自动主键生成 id
    ]
    # pymilvus 插入格式是按字段列表，这里 vector 是第二个字段，所以需要构造为 [id?, vector]
    # 但我们 schema 中 id 是 auto_id，因此只需传 vector 字段的数据：
    entities = [vectors]
    coll.insert(entities)
    coll.flush()
    return len(vectors)


def search_vectors(
    name: str,
    query_vectors: List[List[float]],
    top_k: int = 5,
) -> list[list[dict[str, Any]]]:
    """
    在指定 collection 上搜索向量。
    返回按查询向量顺序的结果列表。
    """
    if not query_vectors:
        return []

    _connect()
    if not utility.has_collection(name):
        raise ValueError(f"collection 不存在: {name}")

    coll = Collection(name)
    coll.load()
    search_params = {"metric_type": "L2", "params": {"nprobe": 10}}
    results = coll.search(
        data=query_vectors,
        anns_field="vector",
        param=search_params,
        limit=top_k,
        output_fields=["id"],
    )

    output: list[list[dict[str, Any]]] = []
    for hits in results:
        one_query: list[dict[str, Any]] = []
        for hit in hits:
            one_query.append(
                {
                    "id": hit.id,
                    "distance": float(hit.distance),
                }
            )
        output.append(one_query)
    return output

