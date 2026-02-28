"""
MinerU 服务客户端

统一从环境变量中读取 MinerU 的各类服务地址，并提供基础的健康检查能力。
"""
from __future__ import annotations

import os
from typing import Any, Dict
import httpx


def get_api_base_url() -> str:
    """
    MinerU Web API 基础地址。

    默认对应 docker-compose.mineru.yml 中暴露的 9999 端口：
      http://localhost:9999
    """
    return os.getenv("MINERU_API_BASE_URL", "http://localhost:9999").rstrip("/")



async def _get_json(url: str) -> Dict[str, Any]:
    async with httpx.AsyncClient(timeout=5.0) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        try:
            return resp.json()
        except Exception:
            return {"status": "ok", "raw": resp.text}



async def check_api_health() -> Dict[str, Any]:
    """
    检查 MinerU Web API 健康状态。
    """
    base = get_api_base_url()
    url = f"{base}/health"
    return await _get_json(url)

