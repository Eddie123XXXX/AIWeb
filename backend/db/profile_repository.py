"""
user_profiles 表 CRUD，使用 asyncpg 连接 PostgreSQL。
依赖: 已执行 db/schema_user_profiles.sql 建表，且 users 表已存在。
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


def _row_to_profile(row: asyncpg.Record) -> dict[str, Any]:
    """将 user_profiles 一行转为字典。"""
    return {
        "user_id": row["user_id"],
        "nickname": row["nickname"],
        "avatar_url": row["avatar_url"],
        "bio": row["bio"],
        "gender": row["gender"],
        "birthday": row["birthday"],
        "location": row["location"],
        "website": row["website"],
        "preferences": dict(row["preferences"]) if row["preferences"] else None,
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


class ProfileRepository:
    """用户资料扩展表仓储。"""

    async def ensure_row(self, user_id: int) -> None:
        """若该 user_id 尚无资料行则插入一行（仅 user_id），用于首次更新资料前。"""
        conn = await _get_conn()
        try:
            await conn.execute(
                "INSERT INTO user_profiles (user_id) VALUES ($1) ON CONFLICT (user_id) DO NOTHING",
                user_id,
            )
        finally:
            await conn.close()

    async def get_by_user_id(self, user_id: int) -> dict[str, Any] | None:
        """按 user_id 查询资料，不存在返回 None。"""
        conn = await _get_conn()
        try:
            row = await conn.fetchrow(
                """
                SELECT user_id, nickname, avatar_url, bio, gender, birthday,
                       location, website, preferences, created_at, updated_at
                FROM user_profiles WHERE user_id = $1
                """,
                user_id,
            )
            return _row_to_profile(row) if row else None
        finally:
            await conn.close()

    async def upsert(
        self,
        user_id: int,
        nickname: str | None = None,
        avatar_url: str | None = None,
        bio: str | None = None,
        gender: int | None = None,
        birthday: str | None = None,
        location: str | None = None,
        website: str | None = None,
        preferences: dict | None = None,
    ) -> dict[str, Any]:
        """
        存在则更新，不存在则插入。只更新传入的非 None 字段。
        preferences 为 dict，会以 JSONB 存储。
        """
        conn = await _get_conn()
        try:
            row = await conn.fetchrow(
                """
                INSERT INTO user_profiles (user_id, nickname, avatar_url, bio, gender, birthday, location, website, preferences)
                VALUES ($1, $2, $3, $4, $5, $6::date, $7, $8, $9::jsonb)
                ON CONFLICT (user_id) DO UPDATE SET
                    nickname = COALESCE(EXCLUDED.nickname, user_profiles.nickname),
                    avatar_url = COALESCE(EXCLUDED.avatar_url, user_profiles.avatar_url),
                    bio = COALESCE(EXCLUDED.bio, user_profiles.bio),
                    gender = COALESCE(EXCLUDED.gender, user_profiles.gender),
                    birthday = COALESCE(EXCLUDED.birthday, user_profiles.birthday),
                    location = COALESCE(EXCLUDED.location, user_profiles.location),
                    website = COALESCE(EXCLUDED.website, user_profiles.website),
                    preferences = COALESCE(EXCLUDED.preferences, user_profiles.preferences),
                    updated_at = CURRENT_TIMESTAMP
                RETURNING user_id, nickname, avatar_url, bio, gender, birthday, location, website, preferences, created_at, updated_at
                """,
                user_id,
                nickname,
                avatar_url,
                bio,
                gender,
                birthday if birthday else None,
                location,
                website,
                asyncpg.Json(preferences) if preferences is not None else None,
            )
            return _row_to_profile(row)
        finally:
            await conn.close()

    async def update(
        self,
        user_id: int,
        nickname: str | None = None,
        avatar_url: str | None = None,
        bio: str | None = None,
        gender: int | None = None,
        birthday: str | None = None,
        location: str | None = None,
        website: str | None = None,
        preferences: dict | None = None,
    ) -> dict[str, Any] | None:
        """
        仅更新传入的非 None 字段；若该 user_id 无资料行则不插入，返回 None。
        """
        conn = await _get_conn()
        try:
            # 先查是否存在
            row = await conn.fetchrow(
                "SELECT user_id FROM user_profiles WHERE user_id = $1",
                user_id,
            )
            if not row:
                return None
            # 构建动态 UPDATE
            updates = ["updated_at = CURRENT_TIMESTAMP"]
            args = []
            i = 1
            if nickname is not None:
                updates.append(f"nickname = ${i}")
                args.append(nickname)
                i += 1
            if avatar_url is not None:
                updates.append(f"avatar_url = ${i}")
                args.append(avatar_url)
                i += 1
            if bio is not None:
                updates.append(f"bio = ${i}")
                args.append(bio)
                i += 1
            if gender is not None:
                updates.append(f"gender = ${i}")
                args.append(gender)
                i += 1
            if birthday is not None:
                updates.append(f"birthday = ${i}::date")
                args.append(birthday)
                i += 1
            if location is not None:
                updates.append(f"location = ${i}")
                args.append(location)
                i += 1
            if website is not None:
                updates.append(f"website = ${i}")
                args.append(website)
                i += 1
            if preferences is not None:
                updates.append(f"preferences = ${i}::jsonb")
                args.append(asyncpg.Json(preferences))
                i += 1
            if len(args) == 0:
                return await self.get_by_user_id(user_id)
            args.append(user_id)
            sql = f"""
                UPDATE user_profiles SET {", ".join(updates)}
                WHERE user_id = ${i}
                RETURNING user_id, nickname, avatar_url, bio, gender, birthday, location, website, preferences, created_at, updated_at
            """
            row = await conn.fetchrow(sql, *args)
            return _row_to_profile(row) if row else None
        finally:
            await conn.close()


profile_repository = ProfileRepository()
