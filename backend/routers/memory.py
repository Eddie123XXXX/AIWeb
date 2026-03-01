"""
记忆管理 API：列表、新增、更新（重算 embedding）、删除。
需登录，仅操作当前用户的记忆。
"""
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from auth.dependencies import get_current_user_id
from memory import service as memory_service

router = APIRouter(prefix="/memory", tags=["memory"])
CurrentUserId = Annotated[int, Depends(get_current_user_id)]


@router.get("/list", summary="列出当前用户记忆")
async def list_memories(
    user_id: CurrentUserId,
    limit: int = 100,
    offset: int = 0,
):
    """分页列出当前用户的记忆（未删除）。"""
    items = await memory_service.list_memories_for_user(user_id=user_id, limit=limit, offset=offset)
    return {"items": items, "total": len(items)}


@router.post("/create", summary="新增一条记忆")
async def create_memory(
    user_id: CurrentUserId,
    body: dict,
):
    """手动新增记忆。body: content (必填), domain?, memory_type?, importance_score?"""
    content = (body.get("content") or "").strip()
    if not content:
        raise HTTPException(status_code=400, detail="content 不能为空")
    domain = body.get("domain") or "general_chat"
    memory_type = body.get("memory_type") or "fact"
    importance_score = float(body.get("importance_score", 0.5))
    row = await memory_service.create_memory_manual(
        user_id=user_id,
        content=content,
        domain=domain,
        memory_type=memory_type,
        importance_score=importance_score,
    )
    return row


@router.put("/{memory_id}", summary="更新记忆（会重新计算 embedding）")
async def update_memory(
    memory_id: str,
    user_id: CurrentUserId,
    body: dict,
):
    """更新记忆内容 / domain / importance_score，后端会重新向量化并写回 Milvus。"""
    content = (body.get("content") or "").strip()
    if not content:
        raise HTTPException(status_code=400, detail="content 不能为空")
    domain = body.get("domain")
    importance_score = body.get("importance_score")
    if importance_score is not None:
        try:
            importance_score = float(importance_score)
        except (TypeError, ValueError):
            importance_score = None
    updated = await memory_service.update_memory_and_reembed(
        user_id=user_id,
        memory_id=memory_id,
        content=content,
        domain=domain,
        importance_score=importance_score,
    )
    if not updated:
        raise HTTPException(status_code=404, detail="记忆不存在或无权修改")
    return updated


@router.delete("/{memory_id}", summary="删除记忆")
async def delete_memory(
    memory_id: str,
    user_id: CurrentUserId,
):
    """软删除一条记忆并同步删除向量。"""
    ok = await memory_service.delete_memory_for_user(user_id=user_id, memory_id=memory_id)
    if not ok:
        raise HTTPException(status_code=404, detail="记忆不存在或无权删除")
    return {"ok": True}
