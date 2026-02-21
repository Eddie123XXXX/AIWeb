"""
messages 表 CRUD，使用 asyncpg 连接 PostgreSQL。
依赖: 已执行 db/schema_messages.sql 建表，且 conversations 表已存在。
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


async def _get_conn() -> asyncpg.Connection:
    return await asyncpg.connect(_get_dsn())


def _row_to_message(row: asyncpg.Record) -> dict[str, Any]:
    """将 messages 一行转为字典。"""
    return {
        "id": row["id"],
        "conversation_id": row["conversation_id"],
        "role": row["role"],
        "content": row["content"],
        "token_count": row["token_count"],
        "metadata": dict(row["metadata"]) if row["metadata"] else None,
        "created_at": row["created_at"],
    }


class MessageRepository:
    """AI 对话消息明细表仓储。"""

    async def create(
        self,
        conversation_id: str,
        role: str,
        content: str,
        token_count: int = 0,
        metadata: dict | None = None,
    ) -> dict[str, Any]:
        """插入一条消息；role 建议为 system / user / assistant / tool。"""
        conn = await _get_conn()
        try:
            row = await conn.fetchrow(
                """
                INSERT INTO messages (conversation_id, role, content, token_count, metadata)
                VALUES ($1, $2, $3, $4, $5::jsonb)
                RETURNING id, conversation_id, role, content, token_count, metadata, created_at
                """,
                conversation_id,
                role,
                content,
                token_count,
                asyncpg.Json(metadata) if metadata is not None else None,
            )
            return _row_to_message(row)
        finally:
            await conn.close()

    async def get_by_id(self, message_id: int) -> dict[str, Any] | None:
        """按消息主键查询。"""
        conn = await _get_conn()
        try:
            row = await conn.fetchrow(
                """
                SELECT id, conversation_id, role, content, token_count, metadata, created_at
                FROM messages WHERE id = $1
                """,
                message_id,
            )
            return _row_to_message(row) if row else None
        finally:
            await conn.close()

    async def list_by_conversation(
        self,
        conversation_id: str,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """按会话 ID 查询消息列表，按 created_at 升序（时间顺序，便于拼上下文）。"""
        conn = await _get_conn()
        try:
            if limit is not None:
                rows = await conn.fetch(
                    """
                    SELECT id, conversation_id, role, content, token_count, metadata, created_at
                    FROM messages
                    WHERE conversation_id = $1
                    ORDER BY created_at ASC, id ASC
                    LIMIT $2 OFFSET $3
                    """,
                    conversation_id,
                    limit,
                    offset,
                )
            else:
                rows = await conn.fetch(
                    """
                    SELECT id, conversation_id, role, content, token_count, metadata, created_at
                    FROM messages
                    WHERE conversation_id = $1
                    ORDER BY created_at ASC, id ASC
                    OFFSET $2
                    """,
                    conversation_id,
                    offset,
                )
            return [_row_to_message(r) for r in rows]
        finally:
            await conn.close()

    async def get_latest_n(
        self,
        conversation_id: str,
        n: int,
    ) -> list[dict[str, Any]]:
        """取某会话最近 n 条消息（按 created_at 升序返回，便于直接作为上下文）。"""
        conn = await _get_conn()
        try:
            rows = await conn.fetch(
                """
                SELECT id, conversation_id, role, content, token_count, metadata, created_at
                FROM (
                    SELECT * FROM messages
                    WHERE conversation_id = $1
                    ORDER BY created_at DESC, id DESC
                    LIMIT $2
                ) sub
                ORDER BY created_at ASC, id ASC
                """,
                conversation_id,
                n,
            )
            return [_row_to_message(r) for r in rows]
        finally:
            await conn.close()

    async def update_token_count(self, message_id: int, token_count: int) -> bool:
        """更新某条消息的 token_count。返回是否实际更新了行。"""
        conn = await _get_conn()
        try:
            result = await conn.execute(
                "UPDATE messages SET token_count = $1 WHERE id = $2",
                token_count,
                message_id,
            )
            return result.split()[-1] == "1"
        finally:
            await conn.close()

    async def update_metadata(self, message_id: int, metadata: dict) -> bool:
        """更新某条消息的 metadata（覆盖写入）。返回是否实际更新了行。"""
        conn = await _get_conn()
        try:
            result = await conn.execute(
                "UPDATE messages SET metadata = $1::jsonb WHERE id = $2",
                asyncpg.Json(metadata),
                message_id,
            )
            return result.split()[-1] == "1"
        finally:
            await conn.close()


message_repository = MessageRepository()
