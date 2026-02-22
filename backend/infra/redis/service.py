"""
Redis 服务封装
"""
import os
from typing import Optional

import redis.asyncio as aioredis


def _get_url() -> str:
    host = os.getenv("REDIS_HOST", "localhost")
    port = os.getenv("REDIS_PORT", "6379")
    db = os.getenv("REDIS_DB", "0")
    password = os.getenv("REDIS_PASSWORD") or None
    if password:
        return f"redis://:{password}@{host}:{port}/{db}"
    return f"redis://{host}:{port}/{db}"


async def get_client() -> aioredis.Redis:
    """获取异步 Redis 连接（每次新建，调用方负责 close）。"""
    url = _get_url()
    return aioredis.from_url(url, encoding="utf-8", decode_responses=True)


async def ping() -> bool:
    """检查 Redis 是否可用。"""
    client = await get_client()
    try:
        return await client.ping()
    finally:
        await client.aclose()


async def get_key(key: str) -> Optional[str]:
    """获取字符串 key 的值，不存在返回 None。"""
    client = await get_client()
    try:
        return await client.get(key)
    finally:
        await client.aclose()


async def set_key(key: str, value: str, ttl_seconds: Optional[int] = None) -> None:
    """设置 key=value，可选 TTL（秒）。"""
    client = await get_client()
    try:
        await client.set(key, value, ex=ttl_seconds)
    finally:
        await client.aclose()


async def delete_key(key: str) -> bool:
    """删除 key，返回是否曾存在。"""
    client = await get_client()
    try:
        n = await client.delete(key)
        return n > 0
    finally:
        await client.aclose()


async def keys(pattern: str = "*") -> list[str]:
    """按 pattern 列出 key（如 'user:*'）。"""
    client = await get_client()
    try:
        return await client.keys(pattern)
    finally:
        await client.aclose()


# ---------- List 操作（聊天上下文热记忆）----------

async def lrange(key: str, start: int, end: int) -> list[str]:
    """LRANGE key start end，返回列表内元素（decode_responses 下为 str）。"""
    client = await get_client()
    try:
        return await client.lrange(key, start, end)
    finally:
        await client.aclose()


async def rpush(key: str, *values: str) -> int:
    """RPUSH key v1 v2 ... 返回 push 后列表长度。"""
    client = await get_client()
    try:
        return await client.rpush(key, *values)
    finally:
        await client.aclose()


async def ltrim(key: str, start: int, end: int) -> None:
    """LTRIM key start end，保留 [start, end] 区间。"""
    client = await get_client()
    try:
        await client.ltrim(key, start, end)
    finally:
        await client.aclose()


async def expire(key: str, seconds: int) -> bool:
    """EXPIRE key seconds，设置过期时间。"""
    client = await get_client()
    try:
        return await client.expire(key, seconds)
    finally:
        await client.aclose()
