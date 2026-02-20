"""
Milvus 测试 API：健康检查、集合管理、简单向量插入/搜索
"""
from typing import List

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from . import service

router = APIRouter(prefix="/infra/milvus", tags=["infra-milvus"])


class InsertBody(BaseModel):
    collection: str = Field(..., description="集合名称")
    vectors: List[List[float]] = Field(
        ..., description="向量列表，例如 [[0.1, 0.2], [0.3, 0.4]]"
    )


class SearchBody(BaseModel):
    collection: str = Field(..., description="集合名称")
    query_vectors: List[List[float]] = Field(
        ..., description="待搜索的向量列表"
    )
    top_k: int = Field(5, description="返回前 K 条结果")


@router.get("/ping", summary="健康检查")
def ping():
    """
    简单检查：尝试列出 collections。
    """
    try:
        cols = service.list_collections()
        return {"status": "ok", "collections": cols}
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Milvus 连接失败: {e}")


@router.get("/collections", summary="列出集合")
def collections():
    """
    列出所有 collection 名称。
    """
    try:
        cols = service.list_collections()
        return {"collections": cols}
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"查询失败: {e}")


@router.post("/collections/{name}", summary="创建简单集合")
def create_collection(name: str, dim: int = 128):
    """
    创建一个最简单的向量集合（id + 向量）。
    """
    try:
        service.create_simple_collection(name, dim=dim)
        return {"collection": name, "dim": dim}
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"创建失败: {e}")


@router.delete("/collections/{name}", summary="删除集合")
def drop_collection(name: str):
    """
    删除集合。
    """
    try:
        service.drop_collection(name)
        return {"collection": name, "dropped": True}
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"删除失败: {e}")


@router.post("/insert", summary="插入向量")
def insert(body: InsertBody):
    """
    向指定集合插入向量。
    - 若集合不存在，则按向量维度自动创建。
    """
    try:
        count = service.insert_vectors(body.collection, body.vectors)
        return {"collection": body.collection, "inserted": count}
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"插入失败: {e}")


@router.post("/search", summary="搜索向量")
def search(body: SearchBody):
    """
    在指定集合中搜索向量。
    """
    try:
        results = service.search_vectors(
            body.collection, body.query_vectors, top_k=body.top_k
        )
        return {"collection": body.collection, "results": results}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"搜索失败: {e}")

