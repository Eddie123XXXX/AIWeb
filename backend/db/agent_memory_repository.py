"""
agent_memories 表 CRUD，使用 asyncpg 连接 PostgreSQL。
依赖: 已执行 db/schema_agent_memories.sql 建表，且 users / conversations 表已存在。
"""
import json
import os
from datetime import datetime
from typing import Any, Iterable, Sequence

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


def _parse_metadata(val: Any) -> dict[str, Any] | None:
    """解析 metadata 字段（asyncpg 可能返回 dict 或 str）。"""
    if val is None:
        return None
    if isinstance(val, dict):
        return dict(val)
    if isinstance(val, str):
        try:
            return json.loads(val)
        except json.JSONDecodeError:
            return None
    return None


def _row_to_memory(row: asyncpg.Record | None) -> dict[str, Any]:
    """将 agent_memories 一行转为字典。"""
    if row is None:
        return {}
    importance = row["importance_score"]
    return {
        "id": row["id"],
        "user_id": row["user_id"],
        "conversation_id": row["conversation_id"],
        "memory_type": row["memory_type"],
        "domain": row.get("domain", "general_chat"),
        "source_role": row["source_role"],
        "source_message_id": row["source_message_id"],
        "content": row["content"],
        "metadata": _parse_metadata(row["metadata"]),
        "vector_collection": row["vector_collection"],
        "importance_score": float(importance) if importance is not None else 0.0,
        "access_count": row["access_count"],
        "last_accessed_at": row["last_accessed_at"],
        "expires_at": row["expires_at"],
        "is_deleted": row["is_deleted"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


class AgentMemoryRepository:
    """Agent 长期记忆与反思表仓储。"""

    async def create(
        self,
        *,
        id: str,
        user_id: int,
        content: str,
        memory_type: str,
        domain: str = "general_chat",
        conversation_id: str | None = None,
        source_role: str | None = None,
        source_message_id: str | None = None,
        metadata: dict | None = None,
        vector_collection: str = "agent_memories",
        importance_score: float = 0.0,
        expires_at: datetime | None = None,
    ) -> dict[str, Any]:
        """
        写入一条新的记忆。
        """
        conn = await _get_conn()
        try:
            row = await conn.fetchrow(
                """
                INSERT INTO agent_memories (
                    id,
                    user_id,
                    conversation_id,
                    memory_type,
                    domain,
                    source_role,
                    source_message_id,
                    content,
                    metadata,
                    vector_collection,
                    importance_score,
                    expires_at
                )
                VALUES (
                    $1, $2, $3, $4, $5, $6, $7, $8,
                    $9::jsonb, $10, $11, $12
                )
                RETURNING
                    id,
                    user_id,
                    conversation_id,
                    memory_type,
                    source_role,
                    source_message_id,
                    content,
                    metadata,
                    vector_collection,
                    importance_score,
                    access_count,
                    last_accessed_at,
                    expires_at,
                    is_deleted,
                    created_at,
                    updated_at
                """,
                id,
                user_id,
                conversation_id,
                memory_type,
                domain,
                source_role,
                source_message_id,
                content,
                json.dumps(metadata, ensure_ascii=False) if metadata is not None else None,
                vector_collection,
                importance_score,
                expires_at,
            )
            return _row_to_memory(row)
        finally:
            await conn.close()

    async def get_by_ids(self, ids: Sequence[str]) -> list[dict[str, Any]]:
        """
        按 ID 批量查询记忆。
        """
        if not ids:
            return []
        conn = await _get_conn()
        try:
            rows = await conn.fetch(
                """
                SELECT
                    id,
                    user_id,
                    conversation_id,
                    memory_type,
                    domain,
                    source_role,
                    source_message_id,
                    content,
                    metadata,
                    vector_collection,
                    importance_score,
                    access_count,
                    last_accessed_at,
                    expires_at,
                    is_deleted,
                    created_at,
                    updated_at
                FROM agent_memories
                WHERE id = ANY($1::varchar[])
                  AND is_deleted = FALSE
                """,
                list(ids),
            )
            return [_row_to_memory(r) for r in rows]
        finally:
            await conn.close()

    async def touch_many(self, ids: Iterable[str]) -> None:
        """
        批量更新 last_accessed_at 与 access_count。
        """
        ids_list = list(ids)
        if not ids_list:
            return
        conn = await _get_conn()
        try:
            await conn.execute(
                """
                UPDATE agent_memories
                SET
                    last_accessed_at = CURRENT_TIMESTAMP,
                    access_count = access_count + 1
                WHERE id = ANY($1::varchar[])
                """,
                ids_list,
            )
        finally:
            await conn.close()

    async def list_by_user(
        self,
        user_id: int,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """
        按用户分页列出未删除的记忆（完整字段），用于记忆管理界面。
        """
        conn = await _get_conn()
        try:
            rows = await conn.fetch(
                """
                SELECT
                    id,
                    user_id,
                    conversation_id,
                    memory_type,
                    domain,
                    source_role,
                    source_message_id,
                    content,
                    metadata,
                    vector_collection,
                    importance_score,
                    access_count,
                    last_accessed_at,
                    expires_at,
                    is_deleted,
                    created_at,
                    updated_at
                FROM agent_memories
                WHERE user_id = $1 AND is_deleted = FALSE
                ORDER BY created_at DESC
                LIMIT $2 OFFSET $3
                """,
                user_id,
                limit,
                offset,
            )
            return [_row_to_memory(r) for r in rows]
        finally:
            await conn.close()

    async def update_content(
        self,
        id: str,
        user_id: int,
        content: str,
        domain: str | None = None,
        importance_score: float | None = None,
    ) -> dict[str, Any] | None:
        """
        更新记忆内容（及可选的 domain、importance_score）。仅当该条属于当前用户时更新。
        返回更新后的行，不存在或非本人则返回 None。
        """
        conn = await _get_conn()
        try:
            row = await conn.fetchrow(
                "SELECT id FROM agent_memories WHERE id = $1 AND user_id = $2 AND is_deleted = FALSE",
                id,
                user_id,
            )
            if row is None:
                return None
            if domain is not None and importance_score is not None:
                score = max(0.0, min(1.0, float(importance_score)))
                out = await conn.fetchrow(
                    """
                    UPDATE agent_memories
                    SET content = $3, domain = $4, importance_score = $5, updated_at = CURRENT_TIMESTAMP
                    WHERE id = $1 AND user_id = $2
                    RETURNING id, user_id, conversation_id, memory_type, domain, source_role,
                      source_message_id, content, metadata, vector_collection, importance_score,
                      access_count, last_accessed_at, expires_at, is_deleted, created_at, updated_at
                    """,
                    id,
                    user_id,
                    content,
                    domain,
                    score,
                )
            elif domain is not None:
                out = await conn.fetchrow(
                    """
                    UPDATE agent_memories
                    SET content = $3, domain = $4, updated_at = CURRENT_TIMESTAMP
                    WHERE id = $1 AND user_id = $2
                    RETURNING id, user_id, conversation_id, memory_type, domain, source_role,
                      source_message_id, content, metadata, vector_collection, importance_score,
                      access_count, last_accessed_at, expires_at, is_deleted, created_at, updated_at
                    """,
                    id,
                    user_id,
                    content,
                    domain,
                )
            elif importance_score is not None:
                score = max(0.0, min(1.0, float(importance_score)))
                out = await conn.fetchrow(
                    """
                    UPDATE agent_memories
                    SET content = $3, importance_score = $4, updated_at = CURRENT_TIMESTAMP
                    WHERE id = $1 AND user_id = $2
                    RETURNING id, user_id, conversation_id, memory_type, domain, source_role,
                      source_message_id, content, metadata, vector_collection, importance_score,
                      access_count, last_accessed_at, expires_at, is_deleted, created_at, updated_at
                    """,
                    id,
                    user_id,
                    content,
                    score,
                )
            else:
                out = await conn.fetchrow(
                    """
                    UPDATE agent_memories
                    SET content = $3, updated_at = CURRENT_TIMESTAMP
                    WHERE id = $1 AND user_id = $2
                    RETURNING id, user_id, conversation_id, memory_type, domain, source_role,
                      source_message_id, content, metadata, vector_collection, importance_score,
                      access_count, last_accessed_at, expires_at, is_deleted, created_at, updated_at
                    """,
                    id,
                    user_id,
                    content,
                )
            return _row_to_memory(out) if out else None
        finally:
            await conn.close()

    async def list_by_user_for_retention(self, user_id: int) -> list[dict[str, Any]]:
        """
        按用户列出未删除的记忆，用于 retention 计算。
        返回 id, memory_type, created_at, last_accessed_at, access_count, importance_score。
        """
        conn = await _get_conn()
        try:
            rows = await conn.fetch(
                """
                SELECT id, memory_type, created_at, last_accessed_at, access_count, importance_score
                FROM agent_memories
                WHERE user_id = $1 AND is_deleted = FALSE
                """,
                user_id,
            )
            return [
                {
                    "id": r["id"],
                    "memory_type": r["memory_type"],
                    "created_at": r["created_at"],
                    "last_accessed_at": r["last_accessed_at"],
                    "access_count": r["access_count"] or 0,
                    "importance_score": float(r["importance_score"] or 0.0),
                }
                for r in rows
            ]
        finally:
            await conn.close()

    async def list_recent_facts_for_reflection(
        self,
        user_id: int,
        conversation_id: str,
        limit: int = 15,
    ) -> list[dict[str, Any]]:
        """
        按用户+会话列出近期 fact 记忆，用于反思触发判断。
        按 created_at 降序，仅包含 memory_type='fact' 且未删除。
        """
        conn = await _get_conn()
        try:
            rows = await conn.fetch(
                """
                SELECT id, content, importance_score, created_at
                FROM agent_memories
                WHERE user_id = $1 AND conversation_id = $2
                  AND memory_type = 'fact' AND is_deleted = FALSE
                ORDER BY created_at DESC
                LIMIT $3
                """,
                user_id,
                conversation_id,
                limit,
            )
            return [
                {
                    "id": r["id"],
                    "content": r["content"],
                    "importance_score": float(r["importance_score"] or 0.0),
                    "created_at": r["created_at"],
                }
                for r in rows
            ]
        finally:
            await conn.close()

    async def get_last_reflection(
        self,
        user_id: int,
        conversation_id: str,
    ) -> dict[str, Any] | None:
        """
        获取该会话最近一条反思记忆，用于冷却判断。
        """
        conn = await _get_conn()
        try:
            row = await conn.fetchrow(
                """
                SELECT id, content, created_at
                FROM agent_memories
                WHERE user_id = $1 AND conversation_id = $2
                  AND memory_type = 'reflection' AND is_deleted = FALSE
                ORDER BY created_at DESC
                LIMIT 1
                """,
                user_id,
                conversation_id,
            )
            if row is None:
                return None
            return {
                "id": row["id"],
                "content": row["content"],
                "created_at": row["created_at"],
            }
        finally:
            await conn.close()

    async def soft_delete_many(self, ids: Iterable[str]) -> int:
        """
        批量软删除记忆（设置 is_deleted = TRUE）。
        返回实际更新的行数。
        """
        ids_list = list(ids)
        if not ids_list:
            return 0
        conn = await _get_conn()
        try:
            result = await conn.execute(
                """
                UPDATE agent_memories
                SET is_deleted = TRUE
                WHERE id = ANY($1::varchar[]) AND is_deleted = FALSE
                """,
                ids_list,
            )
            # "UPDATE N" -> N
            parts = result.split()
            return int(parts[-1]) if parts else 0
        finally:
            await conn.close()


agent_memory_repository = AgentMemoryRepository()

