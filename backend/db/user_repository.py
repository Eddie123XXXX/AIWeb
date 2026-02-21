"""
用户表 CRUD，使用 asyncpg 连接 PostgreSQL。
依赖: 已执行 db/schema_users.sql 建表。
"""
import os
from datetime import datetime
from typing import Any

import asyncpg

import bcrypt


def _get_dsn() -> str:
    host = os.getenv("POSTGRES_HOST", "localhost")
    port = os.getenv("POSTGRES_PORT", "5432")
    user = os.getenv("POSTGRES_USER", "aiweb")
    password = os.getenv("POSTGRES_PASSWORD", "aiweb")
    database = os.getenv("POSTGRES_DB", "aiweb")
    return f"postgresql://{user}:{password}@{host}:{port}/{database}"


def hash_password(plain: str) -> str:
    """明文密码哈希（bcrypt），存入 password_hash 列。bcrypt 限制 72 字节，超出部分截断。"""
    raw = plain.encode("utf-8")
    if len(raw) > 72:
        raw = raw[:72]
    return bcrypt.hashpw(raw, bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    """验证密码与哈希是否匹配。"""
    raw = plain.encode("utf-8")
    if len(raw) > 72:
        raw = raw[:72]
    try:
        return bcrypt.checkpw(raw, hashed.encode("utf-8"))
    except Exception:
        return False


async def _get_conn() -> asyncpg.Connection:
    return await asyncpg.connect(_get_dsn())


def _row_to_user(row: asyncpg.Record) -> dict[str, Any]:
    """将表的一行转为字典，不含 password_hash。"""
    return {
        "id": row["id"],
        "email": row["email"],
        "username": row["username"],
        "phone_code": row["phone_code"],
        "phone_number": row["phone_number"],
        "status": row["status"],
        "last_login_ip": row["last_login_ip"],
        "last_login_at": row["last_login_at"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "deleted_at": row["deleted_at"],
    }


class UserRepository:
    """用户表仓储。"""

    async def get_by_id(self, user_id: int) -> dict[str, Any] | None:
        """按主键查询，已软删除的不返回。"""
        conn = await _get_conn()
        try:
            row = await conn.fetchrow(
                """
                SELECT id, email, username, phone_code, phone_number, password_hash,
                       status, last_login_ip, last_login_at, created_at, updated_at, deleted_at
                FROM users WHERE id = $1 AND deleted_at IS NULL
                """,
                user_id,
            )
            if row is None:
                return None
            return _row_to_user(row)
        finally:
            await conn.close()

    async def get_by_email(self, email: str) -> dict[str, Any] | None:
        """按邮箱查询，已软删除的不返回。"""
        conn = await _get_conn()
        try:
            row = await conn.fetchrow(
                """
                SELECT id, email, username, phone_code, phone_number, password_hash,
                       status, last_login_ip, last_login_at, created_at, updated_at, deleted_at
                FROM users WHERE email = $1 AND deleted_at IS NULL
                """,
                email.strip().lower(),
            )
            if row is None:
                return None
            return _row_to_user(row)
        finally:
            await conn.close()

    async def get_password_hash_by_email(self, email: str) -> str | None:
        """仅取该邮箱用户的 password_hash，用于登录校验。"""
        conn = await _get_conn()
        try:
            return await conn.fetchval(
                "SELECT password_hash FROM users WHERE email = $1 AND deleted_at IS NULL",
                email.strip().lower(),
            )
        finally:
            await conn.close()

    async def create(
        self,
        email: str,
        password_hash: str,
        username: str | None = None,
        phone_code: str | None = None,
        phone_number: str | None = None,
        status: int = 1,
    ) -> dict[str, Any]:
        """创建用户，返回不含 password_hash 的字典。"""
        email = email.strip().lower()
        conn = await _get_conn()
        try:
            row = await conn.fetchrow(
                """
                INSERT INTO users (email, username, phone_code, phone_number, password_hash, status)
                VALUES ($1, $2, $3, $4, $5, $6)
                RETURNING id, email, username, phone_code, phone_number, status,
                          last_login_ip, last_login_at, created_at, updated_at, deleted_at
                """,
                email,
                username.strip() if username else None,
                phone_code.strip() if phone_code else None,
                phone_number.strip() if phone_number else None,
                password_hash,
                status,
            )
            return _row_to_user(row)
        finally:
            await conn.close()

    async def update_profile(
        self,
        user_id: int,
        username: str | None = None,
        phone_code: str | None = None,
        phone_number: str | None = None,
    ) -> dict[str, Any] | None:
        """更新昵称/手机，返回更新后的用户信息。"""
        conn = await _get_conn()
        try:
            updates = ["updated_at = CURRENT_TIMESTAMP"]
            args = [user_id]
            i = 2
            if username is not None:
                updates.append(f"username = ${i}")
                args.append(username.strip() or None)
                i += 1
            if phone_code is not None:
                updates.append(f"phone_code = ${i}")
                args.append(phone_code.strip() or None)
                i += 1
            if phone_number is not None:
                updates.append(f"phone_number = ${i}")
                args.append(phone_number.strip() or None)
                i += 1
            if len(args) == 1:
                return await self.get_by_id(user_id)
            sql = f"""
                UPDATE users SET {", ".join(updates)}
                WHERE id = $1 AND deleted_at IS NULL
                RETURNING id, email, username, phone_code, phone_number, status,
                          last_login_ip, last_login_at, created_at, updated_at, deleted_at
            """
            row = await conn.fetchrow(sql, *args)
            return _row_to_user(row) if row else None
        finally:
            await conn.close()

    async def update_last_login(self, user_id: int, ip: str | None = None) -> None:
        """更新最后登录时间和 IP。"""
        conn = await _get_conn()
        try:
            await conn.execute(
                """
                UPDATE users SET last_login_at = CURRENT_TIMESTAMP, last_login_ip = $2
                WHERE id = $1 AND deleted_at IS NULL
                """,
                user_id,
                ip,
            )
        finally:
            await conn.close()


user_repository = UserRepository()
