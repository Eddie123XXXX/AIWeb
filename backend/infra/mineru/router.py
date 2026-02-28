"""
MinerU 基础设施接口

用于在后端中暴露 MinerU 相关的配置与健康检查信息，方便前端或调试查看。
"""
from fastapi import APIRouter, HTTPException

from . import service

router = APIRouter(prefix="/infra/mineru", tags=["infra-mineru"])


@router.get("/config", summary="获取 MinerU 配置")
async def get_config():
    """
    返回当前后端视角下 MinerU 各服务的基础地址。
    """
    return {
        "api_base_url": service.get_api_base_url()
    }



@router.get("/health/api", summary="检查 MinerU API 服务健康状态")
async def health_api():
    try:
        data = await service.check_api_health()
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"MinerU api 不可用: {e}")
    return data

