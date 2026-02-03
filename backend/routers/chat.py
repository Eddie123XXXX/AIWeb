"""
聊天路由
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
    发送聊天消息
    
    - 支持流式和非流式返回
    - 流式返回使用 SSE (Server-Sent Events)
    """
    # 获取模型配置
    try:
        model_config = get_model_config_by_id(request.model_id)
    except HTTPException:
        raise HTTPException(
            status_code=404, 
            detail=f"模型配置 '{request.model_id}' 不存在，请先添加模型配置"
        )
    
    # 创建 LLM 服务
    llm_service = LLMService(model_config)
    
    if request.stream:
        # 流式返回
        return StreamingResponse(
            generate_sse_stream(
                llm_service,
                request.messages,
                request.temperature,
                request.max_tokens
            ),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no"
            }
        )
    else:
        # 非流式返回
        try:
            content = await llm_service.chat(
                request.messages,
                request.temperature,
                request.max_tokens
            )
            return ChatResponse(
                content=content,
                model=model_config.model_name
            )
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"调用 LLM 失败: {str(e)}")


@router.post("/completions", summary="OpenAI 兼容接口")
async def chat_completions(request: ChatRequest):
    """
    OpenAI 兼容的 chat completions 接口
    方便前端使用现有的 OpenAI SDK
    """
    return await chat(request)


@router.websocket("/ws")
async def websocket_chat(websocket: WebSocket):
    """
    WebSocket 聊天接口
    - 前端通过 ws://HOST/api/chat/ws 连接
    - 发送的数据格式与 ChatRequest 相同（JSON）
    - 支持流式和非流式返回
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
                        {"content": "", "done": True}
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
                        {"content": content, "done": True}
                    )
                except Exception as e:
                    await websocket.send_json(
                        {"error": f"调用 LLM 失败: {str(e)}", "done": True}
                    )

    except WebSocketDisconnect:
        # 客户端关闭连接时静默退出循环
        return
