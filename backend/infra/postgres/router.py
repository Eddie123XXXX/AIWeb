"""
PostgreSQL 测试 API：ping、表列表、只读查询
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from . import service

router = APIRouter(prefix="/infra/postgres", tags=["infra-postgres"])


@router.get("/ping", summary="健康检查")
async def ping():
    """检查 PostgreSQL 是否连通。"""
    try:
        ok = await service.ping()
        return {"status": "pong" if ok else "error"}
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"PostgreSQL 连接失败: {e}")


@router.get("/tables", summary="列出表")
async def list_tables(schema: str = "public"):
    """列出指定 schema 下的表名。"""
    try:
        tables = await service.list_tables(schema=schema)
        return {"schema": schema, "tables": tables}
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"查询失败: {e}")


class QueryBody(BaseModel):
    sql: str


@router.post("/query", summary="执行只读 SQL")
async def query(body: QueryBody):
    """
    执行只读 SQL（仅允许 SELECT），返回行列表。
    示例：`{"sql": "SELECT 1 AS one"}` 或 `{"sql": "SELECT * FROM pg_tables LIMIT 5"}`
    """
    try:
        rows = await service.execute_readonly(body.sql)
        return {"rows": rows, "count": len(rows)}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"执行失败: {e}")
