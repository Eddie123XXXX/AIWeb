"""
一次性迁移：为 documents 表增加 summary 列（来源指南）。
PostgreSQL 9.6+ 支持 ADD COLUMN IF NOT EXISTS。
运行: python -m rag.migrate_add_summary
"""
from __future__ import annotations

import asyncio
import os

import asyncpg


def _get_dsn() -> str:
    host = os.getenv("POSTGRES_HOST", "localhost")
    port = os.getenv("POSTGRES_PORT", "5432")
    user = os.getenv("POSTGRES_USER", "aiweb")
    password = os.getenv("POSTGRES_PASSWORD", "aiweb")
    database = os.getenv("POSTGRES_DB", "aiweb")
    return f"postgresql://{user}:{password}@{host}:{port}/{database}"


async def main() -> None:
    conn = await asyncpg.connect(_get_dsn())
    try:
        await conn.execute(
            "ALTER TABLE documents ADD COLUMN IF NOT EXISTS summary TEXT"
        )
        print("documents.summary column: OK (added if missing)")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
