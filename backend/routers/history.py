"""
历史记录路由：会话列表、详情、创建、更新、删除及消息追加
"""
import uuid
from datetime import datetime
from typing import List

from fastapi import APIRouter, HTTPException, Query

from pydantic import BaseModel, Field

from models import (
    ConversationCreate,
    ConversationDetailResponse,
    ConversationInfo,
    ConversationUpdate,
    Message,
    Role,
)

router = APIRouter(prefix="/history", tags=["history"])

# 内存存储（生产环境建议使用数据库）
_conversations: dict[str, dict] = {}


def _now() -> datetime:
    return datetime.utcnow()


@router.get("/conversations", response_model=List[ConversationInfo], summary="会话列表")
async def list_conversations(
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页条数"),
):
    """
    分页获取会话列表，按更新时间倒序。
    """
    items = list(_conversations.values())
    items.sort(key=lambda x: x["updated_at"], reverse=True)
    start = (page - 1) * page_size
    end = start + page_size
    page_items = items[start:end]
    return [
        ConversationInfo(
            id=c["id"],
            title=c["title"],
            model_id=c["model_id"],
            created_at=c["created_at"],
            updated_at=c["updated_at"],
            message_count=len(c["messages"]),
        )
        for c in page_items
    ]


@router.post("/conversations", response_model=ConversationInfo, summary="创建会话")
async def create_conversation(body: ConversationCreate):
    """创建新会话，返回会话信息。"""
    conversation_id = str(uuid.uuid4())
    now = _now()
    _conversations[conversation_id] = {
        "id": conversation_id,
        "title": body.title,
        "model_id": body.model_id or "",
        "created_at": now,
        "updated_at": now,
        "messages": [],
    }
    c = _conversations[conversation_id]
    return ConversationInfo(
        id=c["id"],
        title=c["title"],
        model_id=c["model_id"],
        created_at=c["created_at"],
        updated_at=c["updated_at"],
        message_count=0,
    )


@router.get(
    "/conversations/{conversation_id}",
    response_model=ConversationDetailResponse,
    summary="会话详情",
)
async def get_conversation(conversation_id: str):
    """获取会话详情，包含完整消息列表。"""
    if conversation_id not in _conversations:
        raise HTTPException(status_code=404, detail="会话不存在")
    c = _conversations[conversation_id]
    return ConversationDetailResponse(
        id=c["id"],
        title=c["title"],
        model_id=c["model_id"],
        created_at=c["created_at"],
        updated_at=c["updated_at"],
        messages=[Message(role=Role(m["role"]), content=m["content"]) for m in c["messages"]],
    )


@router.put(
    "/conversations/{conversation_id}",
    response_model=ConversationInfo,
    summary="更新会话",
)
async def update_conversation(conversation_id: str, body: ConversationUpdate):
    """更新会话（如标题）。"""
    if conversation_id not in _conversations:
        raise HTTPException(status_code=404, detail="会话不存在")
    c = _conversations[conversation_id]
    if body.title is not None:
        c["title"] = body.title
    c["updated_at"] = _now()
    return ConversationInfo(
        id=c["id"],
        title=c["title"],
        model_id=c["model_id"],
        created_at=c["created_at"],
        updated_at=c["updated_at"],
        message_count=len(c["messages"]),
    )


@router.delete("/conversations/{conversation_id}", summary="删除会话")
async def delete_conversation(conversation_id: str):
    """删除会话及其全部消息。"""
    if conversation_id not in _conversations:
        raise HTTPException(status_code=404, detail="会话不存在")
    del _conversations[conversation_id]
    return {"message": "已删除"}


class AppendMessagesBody(BaseModel):
    """追加消息请求体"""
    messages: List[Message] = Field(default_factory=list, description="要追加的消息")
    title: str | None = Field(default=None, description="可选，同时更新会话标题")


@router.post(
    "/conversations/{conversation_id}/messages",
    response_model=ConversationDetailResponse,
    summary="追加消息",
)
async def append_messages(conversation_id: str, body: AppendMessagesBody):
    """
    向会话追加消息。可用于在调用 /api/chat 后，将用户与助手回复写入历史。
    可选同时更新会话标题（传 title）。
    """
    if conversation_id not in _conversations:
        raise HTTPException(status_code=404, detail="会话不存在")
    c = _conversations[conversation_id]
    if body.title is not None:
        c["title"] = body.title
    for msg in body.messages:
        c["messages"].append({"role": msg.role.value, "content": msg.content})
    c["updated_at"] = _now()
    return ConversationDetailResponse(
        id=c["id"],
        title=c["title"],
        model_id=c["model_id"],
        created_at=c["created_at"],
        updated_at=c["updated_at"],
        messages=[Message(role=Role(m["role"]), content=m["content"]) for m in c["messages"]],
    )
