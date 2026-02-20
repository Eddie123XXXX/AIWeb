"""
RabbitMQ 测试 API：ping、发送消息、取消息
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from . import service

router = APIRouter(prefix="/infra/rabbitmq", tags=["infra-rabbitmq"])


class PublishBody(BaseModel):
    queue: str = Field(..., description="队列名称")
    message: str = Field(..., description="要发送的消息内容")


@router.get("/ping", summary="健康检查")
async def ping():
    """
    检查是否能连接到 RabbitMQ。
    """
    try:
        ok = await service.ping()
        return {"status": "ok" if ok else "error"}
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"RabbitMQ 连接失败: {e}")


@router.post("/publish", summary="发送消息")
async def publish(body: PublishBody):
    """
    向指定队列发送一条消息。
    """
    try:
        await service.publish(body.queue, body.message)
        return {"queue": body.queue, "message": body.message}
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"发送失败: {e}")


@router.get("/get", summary="取出一条消息")
async def get(queue: str):
    """
    从队列中取出一条消息（若队列为空则返回 null）。
    """
    try:
        msg = await service.get_one(queue)
        return {"queue": queue, "message": msg}
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"获取失败: {e}")

