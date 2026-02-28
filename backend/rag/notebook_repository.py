"""
notebooks 表 CRUD (asyncpg)

提供笔记本的创建、列表、更新、删除。
"""
from __future__ import annotations

import os
from typing import Any, Optional

import asyncpg


def _get_dsn() -> str:
    host = os.getenv("POSTGRES_HOST", "localhost")
    port = os.getenv("POSTGRES_PORT", "5432")
    user = os.getenv("POSTGRES_USER", "aiweb")
    password = os.getenv("POSTGRES_PASSWORD", "aiweb")
    database = os.getenv("POSTGRES_DB", "aiweb")
    return f"postgresql://{user}:{password}@{host}:{port}/{database}"


async def _conn() -> asyncpg.Connection:
    return await asyncpg.connect(_get_dsn())


def _row_to_dict(row: asyncpg.Record | None) -> dict[str, Any]:
    if row is None:
        return {}
    return dict(row)


class NotebookRepository:
    async def create(self, *, id: str, title: str, user_id: int) -> dict[str, Any]:
        conn = await _conn()
        try:
            row = await conn.fetchrow(
                """
                INSERT INTO notebooks (id, title, user_id)
                VALUES ($1, $2, $3)
                RETURNING id, title, user_id, created_at, updated_at
                """,
                id, title or "未命名笔记本", user_id,
            )
            return _row_to_dict(row)
        finally:
            await conn.close()

    async def get_by_id(self, notebook_id: str) -> Optional[dict[str, Any]]:
        conn = await _conn()
        try:
            row = await conn.fetchrow(
                "SELECT id, title, user_id, created_at, updated_at FROM notebooks WHERE id = $1",
                notebook_id,
            )
            return _row_to_dict(row) if row else None
        finally:
            await conn.close()

    async def get_by_id_with_stats(self, notebook_id: str) -> Optional[dict[str, Any]]:
        """获取笔记本详情，含知识源数量与最后更新时间"""
        conn = await _conn()
        try:
            row = await conn.fetchrow(
                """
                SELECT n.id, n.title, n.user_id, n.created_at, n.updated_at,
                       COALESCE(d.doc_count, 0)::int AS source_count,
                       d.last_updated
                FROM notebooks n
                LEFT JOIN (
                    SELECT notebook_id,
                           COUNT(*) AS doc_count,
                           MAX(updated_at) AS last_updated
                    FROM documents
                    GROUP BY notebook_id
                ) d ON n.id = d.notebook_id
                WHERE n.id = $1
                """,
                notebook_id,
            )
            if not row:
                return None
            d = _row_to_dict(row)
            d["source_count"] = d.get("source_count") or 0
            return d
        finally:
            await conn.close()

    async def list_by_user(
        self, user_id: int, limit: int = 50, offset: int = 0
    ) -> list[dict[str, Any]]:
        conn = await _conn()
        try:
            rows = await conn.fetch(
                """
                SELECT n.id, n.title, n.user_id, n.created_at, n.updated_at,
                       COALESCE(d.doc_count, 0)::int AS source_count,
                       d.last_updated
                FROM notebooks n
                LEFT JOIN (
                    SELECT notebook_id,
                           COUNT(*) AS doc_count,
                           MAX(updated_at) AS last_updated
                    FROM documents
                    GROUP BY notebook_id
                ) d ON n.id = d.notebook_id
                WHERE n.user_id = $1
                ORDER BY n.updated_at DESC
                LIMIT $2 OFFSET $3
                """,
                user_id, limit, offset,
            )
            result = []
            for r in rows:
                d = _row_to_dict(r)
                d["source_count"] = d.get("source_count") or 0
                d["last_updated"] = d.get("last_updated")
                result.append(d)
            return result
        finally:
            await conn.close()

    async def update(self, notebook_id: str, title: str) -> Optional[dict[str, Any]]:
        conn = await _conn()
        try:
            row = await conn.fetchrow(
                """
                UPDATE notebooks
                SET title = $1, updated_at = CURRENT_TIMESTAMP
                WHERE id = $2
                RETURNING id, title, user_id, created_at, updated_at
                """,
                title, notebook_id,
            )
            return _row_to_dict(row) if row else None
        finally:
            await conn.close()

    async def delete(self, notebook_id: str) -> bool:
        conn = await _conn()
        try:
            result = await conn.execute(
                "DELETE FROM notebooks WHERE id = $1",
                notebook_id,
            )
            return result == "DELETE 1"
        finally:
            await conn.close()


notebook_repository = NotebookRepository()
