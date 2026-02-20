"""
PostgreSQL 服务封装（asyncpg）
"""
import os
from typing import Any

import asyncpg


def _get_dsn() -> str:
    host = os.getenv("POSTGRES_HOST", "localhost")
    port = os.getenv("POSTGRES_PORT", "5432")
    user = os.getenv("POSTGRES_USER", "aiweb")
    password = os.getenv("POSTGRES_PASSWORD", "aiweb")
    database = os.getenv("POSTGRES_DB", "aiweb")
    return f"postgresql://{user}:{password}@{host}:{port}/{database}"


async def ping() -> bool:
    """检查数据库是否可用。"""
    conn = await asyncpg.connect(_get_dsn())
    try:
        return await conn.fetchval("SELECT 1") == 1
    finally:
        await conn.close()


async def execute_readonly(sql: str) -> list[dict[str, Any]]:
    """
    执行只读 SQL（仅允许 SELECT），返回行列表。
    每行为 dict，key 为列名。
    """
    s = sql.strip().upper()
    if not s.startswith("SELECT"):
        raise ValueError("仅允许执行 SELECT 语句")
    conn = await asyncpg.connect(_get_dsn())
    try:
        rows = await conn.fetch(sql)
        return [dict(r) for r in rows]
    finally:
        await conn.close()


async def list_tables(schema: str = "public") -> list[str]:
    """列出指定 schema 下的表名。"""
    sql = """
        SELECT tablename
        FROM pg_tables
        WHERE schemaname = $1
        ORDER BY tablename
    """
    conn = await asyncpg.connect(_get_dsn())
    try:
        rows = await conn.fetch(sql, schema)
        return [r["tablename"] for r in rows]
    finally:
        await conn.close()
