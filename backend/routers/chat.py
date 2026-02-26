"""
聊天路由：发送消息、OpenAI 兼容接口、WebSocket 对话
读取路径：Redis 热记忆 → 未命中回源 DB；写路径：先落库再更新 Redis 并滑动窗口截断。
"""
from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse

from models import ChatRequest, ChatResponse, Message, Role
from db.conversation_repository import conversation_repository
from services.chat_context import get_context, get_memory_context_for_prompt, persist_round
from services.llm_service import (
    LLMService,
    generate_sse_stream,
    generate_sse_stream_with_persist,
)
from routers.models import get_model_config_by_id
from services.quick_parse import build_quick_parse_system_content

router = APIRouter(prefix="/chat", tags=["chat"])

# 仅将上下文里允许的角色加入 prompt，避免 Role 枚举报错
_ALLOWED_ROLES = {r.value for r in Role}


def _build_messages_for_llm(request: ChatRequest, context: list[dict]) -> list[Message]:
    """
    拼装：[System Prompt] + [Redis/DB 取出的历史] + [最新用户输入]。
    context 为 get_context 返回的 list[{"role","content"}]；最新用户输入为 request.messages 的最后一条。
    """
    if not request.messages:
        return []
    messages: list[Message] = []
    # 会话级 system_prompt 在调用方注入，这里只拼历史 + 最后一条
    for m in context:
        if m.get("role") in _ALLOWED_ROLES:
            messages.append(Message(role=Role(m["role"]), content=m.get("content") or ""))
    # 最后一条必须是本轮用户输入
    last = request.messages[-1]
    messages.append(Message(role=Role(last.role.value), content=last.content))
    return messages


async def _resolve_conversation_and_messages(request: ChatRequest) -> tuple[str | None, list[Message]]:
    """
    若带 conversation_id：校验会话存在，取 Redis/DB 上下文，召回长期记忆，拼装成发给 LLM 的 messages。
    返回 (conversation_id 或 None, messages)。
    """
    # 若存在 Quick Parse 临时文件，先构建一条额外的 system 消息，用于注入工作记忆
    quick_parse_message: Message | None = None
    if getattr(request, "quick_parse_files", None):
        qp_content = await build_quick_parse_system_content(request.quick_parse_files or [])
        if qp_content:
            quick_parse_message = Message(role=Role.SYSTEM, content=qp_content)

    if not request.conversation_id:
        base_messages = list(request.messages)
        if not base_messages:
            return None, []
        # 将 Quick Parse 工作记忆插入到最后一条用户消息之前
        if quick_parse_message:
            context_msgs = base_messages[:-1]
            last = base_messages[-1]
            return None, [*context_msgs, quick_parse_message, last]
        return None, base_messages

    conv = await conversation_repository.get_by_id(request.conversation_id)
    if not conv:
        raise HTTPException(status_code=404, detail="会话不存在")

    context = await get_context(request.conversation_id)
    user_content = request.messages[-1].content if request.messages else ""

    # 召回长期记忆并拼入 system
    system_parts: list[str] = []
    if conv.get("user_id") and user_content:
        memory_block = await get_memory_context_for_prompt(
            user_id=int(conv["user_id"]),
            conversation_id=request.conversation_id,
            query=user_content,
        )
        if memory_block:
            system_parts.append("【长期记忆】\n" + memory_block)
    if conv.get("system_prompt"):
        system_parts.append(conv["system_prompt"])

    messages: list[Message] = []
    if system_parts:
        messages.append(Message(role=Role.SYSTEM, content="\n\n".join(system_parts)))

    rest = _build_messages_for_llm(request, context)
    if not rest:
        return request.conversation_id, messages

    # 将 Quick Parse 工作记忆插入到最后一条用户消息之前，使其与本轮问题紧邻
    if quick_parse_message:
        context_msgs = rest[:-1]
        last = rest[-1]
        messages.extend(context_msgs)
        messages.append(quick_parse_message)
        messages.append(last)
    else:
        messages.extend(rest)

    return request.conversation_id, messages


@router.post("", summary="发送聊天消息")
async def chat(request: ChatRequest):
    """
    发送聊天消息。

    - **流式**：`stream=true` 时使用 SSE 返回；带 conversation_id 时结束后自动落库并更新 Redis。
    - **非流式**：`stream=false` 时一次性返回；带 conversation_id 时落库并更新 Redis。
    - **conversation_id**：可选；有则先读 Redis/DB 上下文再拼 prompt，回复后双写 DB + Redis。
    """
    try:
        model_config = get_model_config_by_id(request.model_id)
    except HTTPException:
        raise HTTPException(
            status_code=404,
            detail=f"模型配置 '{request.model_id}' 不存在，请先添加模型配置",
        )

    conversation_id, messages_for_llm = await _resolve_conversation_and_messages(request)
    if not messages_for_llm:
        raise HTTPException(status_code=400, detail="消息不能为空")

    llm_service = LLMService(model_config)
    user_content = request.messages[-1].content if request.messages else ""

    if request.stream:
        if conversation_id:
            return StreamingResponse(
                generate_sse_stream_with_persist(
                    llm_service,
                    messages_for_llm,
                    conversation_id=conversation_id,
                    user_content=user_content,
                    temperature=request.temperature,
                    max_tokens=request.max_tokens,
                    model_id=request.model_id or "default",
                ),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    "X-Accel-Buffering": "no",
                },
            )
        return StreamingResponse(
            generate_sse_stream(
                llm_service,
                messages_for_llm,
                request.temperature,
                request.max_tokens,
            ),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    # 非流式
    try:
        content = await llm_service.chat(
            messages_for_llm,
            request.temperature,
            request.max_tokens,
        )
        if conversation_id:
            await persist_round(
                conversation_id, user_content, content,
                model_id=request.model_id or "default",
            )
        return ChatResponse(
            content=content,
            model=model_config.model_name,
            conversation_id=request.conversation_id,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"调用 LLM 失败: {str(e)}")


@router.post("/completions", summary="OpenAI 兼容接口")
async def chat_completions(request: ChatRequest):
    """OpenAI 兼容的 chat completions，逻辑同 POST /api/chat。"""
    return await chat(request)


@router.websocket("/ws")
async def websocket_chat(websocket: WebSocket):
    """
    WebSocket 聊天接口。带 conversation_id 时：读 Redis/DB 上下文拼 prompt，结束后双写 DB + Redis。
    """
    await websocket.accept()

    try:
        while True:
            data = await websocket.receive_json()
            try:
                request = ChatRequest(**data)
            except Exception as e:
                await websocket.send_json(
                    {"error": f"请求格式错误: {str(e)}", "done": True}
                )
                continue

            try:
                model_config = get_model_config_by_id(request.model_id)
            except HTTPException as e:
                await websocket.send_json({"error": e.detail, "done": True})
                continue

            try:
                conversation_id, messages_for_llm = await _resolve_conversation_and_messages(request)
            except HTTPException as e:
                await websocket.send_json({"error": e.detail, "done": True})
                continue

            if not messages_for_llm:
                await websocket.send_json({"error": "消息不能为空", "done": True})
                continue

            user_content = request.messages[-1].content if request.messages else ""
            llm_service = LLMService(model_config)

            if request.stream:
                accumulated = []
                try:
                    async for content in llm_service.chat_stream(
                        messages_for_llm,
                        request.temperature,
                        request.max_tokens,
                    ):
                        accumulated.append(content)
                        await websocket.send_json({"content": content, "done": False})
                    full_reply = "".join(accumulated)
                    if conversation_id:
                        await persist_round(
                            conversation_id, user_content, full_reply,
                            model_id=request.model_id or "default",
                        )
                    await websocket.send_json(
                        {"content": "", "done": True, "conversation_id": request.conversation_id}
                    )
                except Exception as e:
                    await websocket.send_json(
                        {"error": f"调用 LLM 失败: {str(e)}", "done": True}
                    )
            else:
                try:
                    content = await llm_service.chat(
                        messages_for_llm,
                        request.temperature,
                        request.max_tokens,
                    )
                    if conversation_id:
                        await persist_round(
                            conversation_id, user_content, content,
                            model_id=request.model_id or "default",
                        )
                    await websocket.send_json(
                        {"content": content, "done": True, "conversation_id": request.conversation_id}
                    )
                except Exception as e:
                    await websocket.send_json(
                        {"error": f"调用 LLM 失败: {str(e)}", "done": True}
                    )

    except WebSocketDisconnect:
        return
