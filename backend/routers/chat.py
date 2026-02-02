"""
聊天路由
"""
from fastapi import APIRouter, HTTPException
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
