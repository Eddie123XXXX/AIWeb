"""
user_oauths 表 CRUD，第三方授权登录与绑定。
依赖: 已执行 db/schema_user_oauths.sql，且 users 表已存在。
"""
import os
import re
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


def _row_to_oauth(row: asyncpg.Record) -> dict[str, Any]:
    return {
        "id": row["id"],
        "user_id": row["user_id"],
        "provider": row["provider"],
        "provider_uid": row["provider_uid"],
        "provider_data": dict(row["provider_data"]) if row.get("provider_data") else None,
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def _sanitize_uid(uid: str) -> str:
    """用于生成唯一占位邮箱，仅保留安全字符。"""
    return re.sub(r"[^a-zA-Z0-9_-]", "_", uid)[:200]


class OAuthRepository:
    """第三方授权表仓储。"""

    async def get_by_provider_uid(self, provider: str, provider_uid: str) -> dict[str, Any] | None:
        """按 (provider, provider_uid) 查一条绑定记录。"""
        conn = await _get_conn()
        try:
            row = await conn.fetchrow(
                """
                SELECT id, user_id, provider, provider_uid, provider_data, created_at, updated_at
                FROM user_oauths WHERE provider = $1 AND provider_uid = $2
                """,
                provider.strip().lower(),
                provider_uid.strip(),
            )
            return _row_to_oauth(row) if row else None
        finally:
            await conn.close()

    async def list_by_user_id(self, user_id: int) -> list[dict[str, Any]]:
        """查询某用户绑定的所有第三方账号。"""
        conn = await _get_conn()
        try:
            rows = await conn.fetch(
                """
                SELECT id, user_id, provider, provider_uid, provider_data, created_at, updated_at
                FROM user_oauths WHERE user_id = $1 ORDER BY created_at
                """,
                user_id,
            )
            return [_row_to_oauth(r) for r in rows]
        finally:
            await conn.close()

    async def bind(
        self,
        user_id: int,
        provider: str,
        provider_uid: str,
        provider_data: dict | None = None,
    ) -> dict[str, Any]:
        """
        绑定当前用户与第三方账号。若 (provider, provider_uid) 已存在则更新 provider_data。
        若该 provider_uid 已绑定其他 user_id 则冲突，由调用方先查再决定是否允许覆盖。
        """
        conn = await _get_conn()
        try:
            provider = provider.strip().lower()
            provider_uid = provider_uid.strip()
            row = await conn.fetchrow(
                """
                INSERT INTO user_oauths (user_id, provider, provider_uid, provider_data)
                VALUES ($1, $2, $3, $4::jsonb)
                ON CONFLICT (provider, provider_uid) DO UPDATE SET
                    user_id = EXCLUDED.user_id,
                    provider_data = COALESCE(EXCLUDED.provider_data, user_oauths.provider_data),
                    updated_at = CURRENT_TIMESTAMP
                RETURNING id, user_id, provider, provider_uid, provider_data, created_at, updated_at
                """,
                user_id,
                provider,
                provider_uid,
                asyncpg.Json(provider_data) if provider_data is not None else None,
            )
            return _row_to_oauth(row)
        finally:
            await conn.close()

    async def unbind(self, user_id: int, provider: str) -> bool:
        """解除当前用户与某 provider 的绑定（按 user_id + provider 删除一条）。"""
        conn = await _get_conn()
        try:
            result = await conn.execute(
                "DELETE FROM user_oauths WHERE user_id = $1 AND provider = $2",
                user_id,
                provider.strip().lower(),
            )
            return result == "DELETE 1"
        finally:
            await conn.close()

    async def update_provider_data(
        self,
        provider: str,
        provider_uid: str,
        provider_data: dict,
    ) -> dict[str, Any] | None:
        """更新某条绑定的 provider_data。"""
        conn = await _get_conn()
        try:
            row = await conn.fetchrow(
                """
                UPDATE user_oauths SET provider_data = $3::jsonb, updated_at = CURRENT_TIMESTAMP
                WHERE provider = $1 AND provider_uid = $2
                RETURNING id, user_id, provider, provider_uid, provider_data, created_at, updated_at
                """,
                provider.strip().lower(),
                provider_uid.strip(),
                asyncpg.Json(provider_data),
            )
            return _row_to_oauth(row) if row else None
        finally:
            await conn.close()


oauth_repository = OAuthRepository()
