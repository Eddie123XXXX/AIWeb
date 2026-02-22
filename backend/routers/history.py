"""
历史记录路由：会话列表、详情、创建、更新、删除及消息追加（使用 DB + 需登录）
"""
import uuid
from typing import Annotated, List

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from auth.dependencies import get_current_user_id
from db.conversation_repository import conversation_repository
from db.message_repository import message_repository
from models import (
    ConversationCreate,
    ConversationDetailResponse,
    ConversationInfo,
    ConversationUpdate,
    Message,
    Role,
)

router = APIRouter(prefix="/history", tags=["history"])
CurrentUserId = Annotated[int, Depends(get_current_user_id)]


@router.get("/conversations", response_model=List[ConversationInfo], summary="会话列表")
async def list_conversations(
    user_id: CurrentUserId,
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页条数"),
):
    """分页获取当前用户的会话列表，按 updated_at 倒序。"""
    offset = (page - 1) * page_size
    items = await conversation_repository.list_by_user(user_id, limit=page_size, offset=offset)
    return [
        ConversationInfo(
            id=c["id"],
            title=c["title"],
            model_id=c.get("model_provider") or "",
            created_at=c["created_at"],
            updated_at=c["updated_at"],
            message_count=0,
        )
        for c in items
    ]


@router.post("/conversations", response_model=ConversationInfo, summary="创建会话")
async def create_conversation(user_id: CurrentUserId, body: ConversationCreate):
    """创建新会话，返回会话信息；之后发聊天时可带此 id 作为 conversation_id。"""
    conversation_id = str(uuid.uuid4())
    await conversation_repository.create(
        conversation_id=conversation_id,
        user_id=user_id,
        title=body.title,
        model_provider=(body.model_id or "vllm"),
    )
    c = await conversation_repository.get_by_id(conversation_id)
    return ConversationInfo(
        id=c["id"],
        title=c["title"],
        model_id=c.get("model_provider") or "",
        created_at=c["created_at"],
        updated_at=c["updated_at"],
        message_count=0,
    )


def _ensure_own_conversation(conv: dict | None, user_id: int) -> None:
    if not conv:
        raise HTTPException(status_code=404, detail="会话不存在")
    if conv["user_id"] != user_id:
        raise HTTPException(status_code=403, detail="无权访问该会话")


@router.get(
    "/conversations/{conversation_id}",
    response_model=ConversationDetailResponse,
    summary="会话详情",
)
async def get_conversation(conversation_id: str, user_id: CurrentUserId):
    """获取会话详情，包含完整消息列表。"""
    conv = await conversation_repository.get_by_id(conversation_id)
    _ensure_own_conversation(conv, user_id)
    messages = await message_repository.list_by_conversation(conversation_id)
    return ConversationDetailResponse(
        id=conv["id"],
        title=conv["title"],
        model_id=conv.get("model_provider") or "",
        created_at=conv["created_at"],
        updated_at=conv["updated_at"],
        messages=[
            Message(role=Role(m["role"]) if m["role"] in ("system", "user", "assistant", "tool") else Role.USER, content=m["content"])
            for m in messages
        ],
    )


@router.put(
    "/conversations/{conversation_id}",
    response_model=ConversationInfo,
    summary="更新会话",
)
async def update_conversation(conversation_id: str, user_id: CurrentUserId, body: ConversationUpdate):
    """更新会话（如标题）。"""
    conv = await conversation_repository.get_by_id(conversation_id)
    _ensure_own_conversation(conv, user_id)
    if body.title is not None:
        await conversation_repository.update(conversation_id, title=body.title)
    updated = await conversation_repository.get_by_id(conversation_id)
    messages = await message_repository.list_by_conversation(conversation_id)
    return ConversationInfo(
        id=updated["id"],
        title=updated["title"],
        model_id=updated.get("model_provider") or "",
        created_at=updated["created_at"],
        updated_at=updated["updated_at"],
        message_count=len(messages),
    )


@router.delete("/conversations/{conversation_id}", summary="删除会话")
async def delete_conversation(conversation_id: str, user_id: CurrentUserId):
    """软删除会话（不删消息记录，可审计）。"""
    conv = await conversation_repository.get_by_id(conversation_id)
    _ensure_own_conversation(conv, user_id)
    await conversation_repository.soft_delete(conversation_id)
    return {"message": "已删除"}


class AppendMessagesBody(BaseModel):
    """追加消息请求体（聊天已自动落库，此接口主要用于补写或更新标题）"""
    messages: List[Message] = Field(default_factory=list, description="要追加的消息")
    title: str | None = Field(default=None, description="可选，同时更新会话标题")


@router.post(
    "/conversations/{conversation_id}/messages",
    response_model=ConversationDetailResponse,
    summary="追加消息",
)
async def append_messages(conversation_id: str, user_id: CurrentUserId, body: AppendMessagesBody):
    """向会话追加消息（并可选更新标题）；聊天流程已自动双写 DB+Redis，一般无需单独调用。"""
    conv = await conversation_repository.get_by_id(conversation_id)
    _ensure_own_conversation(conv, user_id)
    if body.title is not None:
        await conversation_repository.update(conversation_id, title=body.title)
    for msg in body.messages:
        await message_repository.create(
            conversation_id,
            msg.role.value,
            msg.content,
        )
    if body.messages:
        await conversation_repository.touch(conversation_id)
        from services.chat_context import append_messages_and_trim
        await append_messages_and_trim(
            conversation_id,
            [{"role": m.role.value, "content": m.content} for m in body.messages],
        )
    updated = await conversation_repository.get_by_id(conversation_id)
    messages = await message_repository.list_by_conversation(conversation_id)
    return ConversationDetailResponse(
        id=updated["id"],
        title=updated["title"],
        model_id=updated.get("model_provider") or "",
        created_at=updated["created_at"],
        updated_at=updated["updated_at"],
        messages=[
            Message(role=Role(m["role"]) if m["role"] in ("system", "user", "assistant", "tool") else Role.USER, content=m["content"])
            for m in messages
        ],
    )
