"""
Elasticsearch 测试 API：ping、索引列表、写入与搜索
"""
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from . import service

router = APIRouter(prefix="/infra/elasticsearch", tags=["infra-elasticsearch"])


@router.get("/ping", summary="健康检查")
def ping():
    """
    检查 Elasticsearch 是否连通。
    """
    try:
        ok = service.ping()
        return {"status": "pong" if ok else "error"}
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Elasticsearch 连接失败: {e}")


@router.get("/indices", summary="列出索引")
def indices():
    """
    列出当前所有索引名称。
    """
    try:
        items = service.list_indices()
        return {"indices": items}
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"查询失败: {e}")


class IndexDocBody(BaseModel):
    index: str = Field(..., description="索引名称")
    id: Optional[str] = Field(None, description="文档 ID，可不传让 ES 自动生成")
    title: str
    content: str


@router.post("/index", summary="写入文档")
def index_doc(body: IndexDocBody):
    """
    向指定索引写入一条文档。
    """
    try:
        doc_id = service.index_document(
            body.index,
            body.id,
            {"title": body.title, "content": body.content},
        )
        return {"index": body.index, "id": doc_id}
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"写入失败: {e}")


class SearchBody(BaseModel):
    index: str = Field(..., description="索引名称")
    query: str = Field(..., description="搜索关键字")
    size: int = Field(10, description="返回条数")


@router.post("/search", summary="全文搜索")
def search(body: SearchBody):
    """
    在指定索引中执行简单全文搜索。
    """
    try:
        result = service.search(body.index, body.query, size=body.size)
        return result
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"搜索失败: {e}")

