"""
conversations 表 CRUD，使用 asyncpg 连接 PostgreSQL。
对应前端左侧边栏的“历史对话框”。依赖: 已执行 db/schema_conversations.sql 建表，且 users 表已存在。
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


def _row_to_conversation(row: asyncpg.Record) -> dict[str, Any]:
    """将 conversations 一行转为字典。"""
    return {
        "id": row["id"],
        "user_id": row["user_id"],
        "title": row["title"],
        "system_prompt": row["system_prompt"],
        "model_provider": row["model_provider"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "deleted_at": row["deleted_at"],
    }


class ConversationRepository:
    """AI 会话/聊天室表仓储。"""

    async def create(
        self,
        conversation_id: str,
        user_id: int,
        title: str = "新对话",
        system_prompt: str | None = None,
        model_provider: str = "vllm",
    ) -> dict[str, Any]:
        """创建一条会话；conversation_id 建议使用 UUID。"""
        conn = await _get_conn()
        try:
            row = await conn.fetchrow(
                """
                INSERT INTO conversations (id, user_id, title, system_prompt, model_provider)
                VALUES ($1, $2, $3, $4, $5)
                RETURNING id, user_id, title, system_prompt, model_provider, created_at, updated_at, deleted_at
                """,
                conversation_id,
                user_id,
                title,
                system_prompt,
                model_provider,
            )
            return _row_to_conversation(row)
        finally:
            await conn.close()

    async def get_by_id(self, conversation_id: str) -> dict[str, Any] | None:
        """按会话 ID 查询，已软删除的不返回。"""
        conn = await _get_conn()
        try:
            row = await conn.fetchrow(
                """
                SELECT id, user_id, title, system_prompt, model_provider, created_at, updated_at, deleted_at
                FROM conversations WHERE id = $1 AND deleted_at IS NULL
                """,
                conversation_id,
            )
            return _row_to_conversation(row) if row else None
        finally:
            await conn.close()

    async def list_by_user(
        self,
        user_id: int,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """按用户查询会话列表，按 updated_at 倒序（最近活跃在前），排除已软删除。"""
        conn = await _get_conn()
        try:
            rows = await conn.fetch(
                """
                SELECT id, user_id, title, system_prompt, model_provider, created_at, updated_at, deleted_at
                FROM conversations
                WHERE user_id = $1 AND deleted_at IS NULL
                ORDER BY updated_at DESC
                LIMIT $2 OFFSET $3
                """,
                user_id,
                limit,
                offset,
            )
            return [_row_to_conversation(r) for r in rows]
        finally:
            await conn.close()

    async def update(
        self,
        conversation_id: str,
        title: str | None = None,
        system_prompt: str | None = None,
        model_provider: str | None = None,
    ) -> dict[str, Any] | None:
        """更新会话字段（仅更新传入的非 None 字段），并刷新 updated_at。已软删除的不更新。"""
        conn = await _get_conn()
        try:
            updates = ["updated_at = CURRENT_TIMESTAMP"]
            args = []
            i = 1
            if title is not None:
                updates.append(f"title = ${i}")
                args.append(title)
                i += 1
            if system_prompt is not None:
                updates.append(f"system_prompt = ${i}")
                args.append(system_prompt)
                i += 1
            if model_provider is not None:
                updates.append(f"model_provider = ${i}")
                args.append(model_provider)
                i += 1
            if len(args) == 0:
                return await self.get_by_id(conversation_id)
            args.append(conversation_id)
            row = await conn.fetchrow(
                f"""
                UPDATE conversations SET {", ".join(updates)}
                WHERE id = ${i} AND deleted_at IS NULL
                RETURNING id, user_id, title, system_prompt, model_provider, created_at, updated_at, deleted_at
                """,
                *args,
            )
            return _row_to_conversation(row) if row else None
        finally:
            await conn.close()

    async def touch(self, conversation_id: str) -> bool:
        """仅刷新 updated_at（例如新消息写入后用于左侧按活跃度排序）。返回是否更新了行。"""
        conn = await _get_conn()
        try:
            result = await conn.execute(
                "UPDATE conversations SET updated_at = CURRENT_TIMESTAMP WHERE id = $1 AND deleted_at IS NULL",
                conversation_id,
            )
            return result.split()[-1] == "1"
        finally:
            await conn.close()

    async def soft_delete(self, conversation_id: str) -> bool:
        """软删除会话（设置 deleted_at）。返回是否实际更新了行。"""
        conn = await _get_conn()
        try:
            result = await conn.execute(
                """
                UPDATE conversations SET deleted_at = CURRENT_TIMESTAMP
                WHERE id = $1 AND deleted_at IS NULL
                """,
                conversation_id,
            )
            return result.split()[-1] == "1"
        finally:
            await conn.close()


conversation_repository = ConversationRepository()
