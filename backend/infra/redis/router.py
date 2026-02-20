"""
Redis 测试 API：ping、get/set/delete、keys
"""
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from . import service

router = APIRouter(prefix="/infra/redis", tags=["infra-redis"])


class SetKeyBody(BaseModel):
    key: str
    value: str
    ttl_seconds: Optional[int] = None


@router.get("/ping", summary="健康检查")
async def ping():
    """检查 Redis 是否连通。"""
    try:
        ok = await service.ping()
        return {"status": "pong" if ok else "error"}
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Redis 连接失败: {e}")


@router.get("/keys", summary="按 pattern 列出 key")
async def list_keys(pattern: str = "*"):
    """列出匹配的 key，默认全部。"""
    try:
        keys = await service.keys(pattern=pattern)
        return {"keys": keys, "pattern": pattern}
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Redis 请求失败: {e}")


@router.get("/{key:path}", summary="获取 key 的值")
async def get_key(key: str):
    """获取字符串 key 的值。"""
    try:
        value = await service.get_key(key)
        if value is None:
            raise HTTPException(status_code=404, detail=f"key 不存在: {key}")
        return {"key": key, "value": value}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Redis 请求失败: {e}")


@router.post("", summary="设置 key")
async def set_key(body: SetKeyBody):
    """
    设置 key=value，请求体 JSON：`{"key": "k", "value": "v", "ttl_seconds": 60}`。
    """
    try:
        await service.set_key(
            body.key, body.value, ttl_seconds=body.ttl_seconds
        )
        return {
            "key": body.key,
            "value": body.value,
            "ttl_seconds": body.ttl_seconds,
        }
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Redis 写入失败: {e}")


@router.delete("/{key:path}", summary="删除 key")
async def delete_key(key: str):
    """删除指定 key。"""
    try:
        existed = await service.delete_key(key)
        return {"key": key, "deleted": existed}
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Redis 删除失败: {e}")
