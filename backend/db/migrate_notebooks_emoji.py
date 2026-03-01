"""
一次性迁移：为 notebooks 表增加 emoji 列。
PostgreSQL 9.6+ 支持 ADD COLUMN IF NOT EXISTS。
运行（在 backend 目录下）: python -m db.migrate_notebooks_emoji
"""
from __future__ import annotations

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv

load_dotenv()

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
            "ALTER TABLE notebooks ADD COLUMN IF NOT EXISTS emoji VARCHAR(32) NULL"
        )
        print("notebooks.emoji column: OK (added if missing)")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
