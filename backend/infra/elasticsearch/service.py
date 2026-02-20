"""
Elasticsearch 服务封装（同步客户端，用于简单测试）
"""
import os
from typing import Any, List, Dict

from elasticsearch import Elasticsearch


def _get_client() -> Elasticsearch:
    host = os.getenv("ELASTICSEARCH_HOST", "localhost")
    port = os.getenv("ELASTICSEARCH_PORT", "9200")
    return Elasticsearch([{"host": host, "port": int(port), "scheme": "http"}])


def ping() -> bool:
    client = _get_client()
    return client.ping()


def list_indices() -> List[str]:
    client = _get_client()
    indices = client.indices.get_alias("*")
    return list(indices.keys())


def create_simple_index(name: str) -> None:
    """
    创建一个简单的索引（如已存在则跳过）。
    """
    client = _get_client()
    if client.indices.exists(index=name):
        return
    body: Dict[str, Any] = {
        "mappings": {
            "properties": {
                "title": {"type": "text"},
                "content": {"type": "text"},
            }
        }
    }
    client.indices.create(index=name, body=body)


def index_document(index: str, doc_id: str | None, document: Dict[str, Any]) -> str:
    """
    写入一条文档，返回文档 ID。
    """
    client = _get_client()
    create_simple_index(index)
    resp = client.index(index=index, id=doc_id, document=document)
    return resp.get("_id", "")


def search(index: str, query: str, size: int = 10) -> Dict[str, Any]:
    """
    在指定索引上执行简单全文搜索。
    """
    client = _get_client()
    body = {
        "query": {
            "multi_match": {
                "query": query,
                "fields": ["title", "content"],
            }
        }
    }
    resp = client.search(index=index, body=body, size=size)
    hits = resp.get("hits", {}).get("hits", [])
    return {
        "total": resp.get("hits", {}).get("total", {}),
        "hits": [
            {
                "id": h.get("_id"),
                "score": h.get("_score"),
                "source": h.get("_source"),
            }
            for h in hits
        ],
    }

