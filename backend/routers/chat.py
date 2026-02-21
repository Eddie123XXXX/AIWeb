"""
聊天路由：发送消息、OpenAI 兼容接口、WebSocket 对话
"""
from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse
from models import ChatRequest, ChatResponse
from services.llm_service import LLMService, generate_sse_stream
from routers.models import get_model_config_by_id

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("", summary="发送聊天消息")
async def chat(request: ChatRequest):
    """
    发送聊天消息。

    - **流式**：`stream=true` 时使用 SSE (Server-Sent Events) 返回
    - **非流式**：`stream=false` 时一次性返回完整回复
    - **conversation_id**：可选，用于关联历史会话，便于前端展示或调用历史接口保存
    """
    try:
        model_config = get_model_config_by_id(request.model_id)
    except HTTPException:
        raise HTTPException(
            status_code=404,
            detail=f"模型配置 '{request.model_id}' 不存在，请先添加模型配置",
        )

    llm_service = LLMService(model_config)

    if request.stream:
        return StreamingResponse(
            generate_sse_stream(
                llm_service,
                request.messages,
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

    try:
        content = await llm_service.chat(
            request.messages,
            request.temperature,
            request.max_tokens,
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
    """
    OpenAI 兼容的 chat completions 接口，便于前端使用现有 OpenAI SDK。
    请求/响应格式与 POST /api/chat 一致。
    """
    return await chat(request)


@router.websocket("/ws")
async def websocket_chat(websocket: WebSocket):
    """
    WebSocket 聊天接口。

    - 连接：`ws://HOST/api/chat/ws`
    - 发送：JSON，格式同 `ChatRequest`（含 model_id、messages、stream 等）
    - 响应：每条消息 `{"content": "...", "done": false}`，结束为 `{"content": "", "done": true}`，错误为 `{"error": "...", "done": true}`
    """
    await websocket.accept()

    try:
        while True:
            data = await websocket.receive_json()

            # 解析请求体
            try:
                request = ChatRequest(**data)
            except Exception as e:
                await websocket.send_json(
                    {"error": f"请求格式错误: {str(e)}", "done": True}
                )
                continue

            # 获取模型配置
            try:
                model_config = get_model_config_by_id(request.model_id)
            except HTTPException as e:
                await websocket.send_json({"error": e.detail, "done": True})
                continue

            llm_service = LLMService(model_config)

            # 流式 / 非流式返回
            if request.stream:
                try:
                    async for content in llm_service.chat_stream(
                        request.messages,
                        request.temperature,
                        request.max_tokens,
                    ):
                        await websocket.send_json(
                            {"content": content, "done": False}
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
                        request.messages,
                        request.temperature,
                        request.max_tokens,
                    )
                    await websocket.send_json(
                        {"content": content, "done": True, "conversation_id": request.conversation_id}
                    )
                except Exception as e:
                    await websocket.send_json(
                        {"error": f"调用 LLM 失败: {str(e)}", "done": True}
                    )

    except WebSocketDisconnect:
        # 客户端关闭连接时静默退出循环
        return
