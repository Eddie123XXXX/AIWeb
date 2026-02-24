"""
LLM 服务层
统一封装不同提供商的 API 调用
"""
import json
from typing import AsyncGenerator, List, Optional
from openai import AsyncOpenAI
from config import ModelConfig, PROVIDER_CONFIGS
from models import Message


class LLMService:
    """LLM 服务封装"""
    
    def __init__(self, model_config: ModelConfig):
        self.config = model_config
        self.client = self._create_client()
    
    def _create_client(self) -> AsyncOpenAI:
        """创建 OpenAI 兼容客户端"""
        api_base = self.config.api_base
        
        # 如果没有自定义 api_base，使用预定义的
        if not api_base and self.config.provider in PROVIDER_CONFIGS:
            api_base = PROVIDER_CONFIGS[self.config.provider]["api_base"]
        
        # 默认使用 OpenAI 的地址
        if not api_base:
            api_base = "https://api.openai.com/v1"
        
        return AsyncOpenAI(
            api_key=self.config.api_key,
            base_url=api_base
        )
    
    def _completion_kwargs(
        self,
        temperature: Optional[float],
        max_tokens: Optional[int],
    ) -> dict:
        """构建 chat.completions.create 的公共参数。OpenAI 新模型要求用 max_completion_tokens，旧版 SDK 仅支持 max_tokens。"""
        n = max_tokens or self.config.max_tokens
        t = temperature if temperature is not None else self.config.temperature
        kwargs = {"temperature": t}
        if self.config.provider == "openai":
            # 新 API 要求 max_completion_tokens；旧版 openai SDK 只认 max_tokens，用 extra_body 透传
            kwargs["max_completion_tokens"] = n
        else:
            kwargs["max_tokens"] = n
        return kwargs

    async def _create_completion(self, messages: list, stream: bool, extra: dict):
        """发起 create 调用。OpenAI 新模型需 max_completion_tokens；旧版 SDK 用 extra_body 透传。"""
        base = {
            "model": self.config.model_name,
            "messages": messages,
            "stream": stream,
        }
        if self.config.provider == "openai" and "max_completion_tokens" in extra:
            n = extra.pop("max_completion_tokens")
            base["max_completion_tokens"] = n
            try:
                return await self.client.chat.completions.create(**base, **extra)
            except TypeError:
                # 旧版 openai SDK 不支持 max_completion_tokens 参数，用 extra_body 传给 API
                base.pop("max_completion_tokens", None)
                return await self.client.chat.completions.create(
                    **base, **extra, extra_body={"max_completion_tokens": n}
                )
        return await self.client.chat.completions.create(**base, **extra)

    async def chat(
        self,
        messages: List[Message],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None
    ) -> str:
        """非流式对话"""
        extra = self._completion_kwargs(temperature, max_tokens)
        msg = [{"role": m.role.value, "content": m.content} for m in messages]
        response = await self._create_completion(msg, stream=False, extra=extra)
        return response.choices[0].message.content

    async def chat_stream(
        self,
        messages: List[Message],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None
    ) -> AsyncGenerator[str, None]:
        """流式对话"""
        extra = self._completion_kwargs(temperature, max_tokens)
        msg = [{"role": m.role.value, "content": m.content} for m in messages]
        response = await self._create_completion(msg, stream=True, extra=extra)
        
        async for chunk in response:
            if chunk.choices and chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content


async def generate_sse_stream(
    llm_service: LLMService,
    messages: List[Message],
    temperature: Optional[float] = None,
    max_tokens: Optional[int] = None
) -> AsyncGenerator[str, None]:
    """生成 SSE 格式的流式响应"""
    try:
        async for content in llm_service.chat_stream(messages, temperature, max_tokens):
            # SSE 格式
            data = json.dumps({"content": content, "done": False}, ensure_ascii=False)
            yield f"data: {data}\n\n"
        
        # 发送完成标记
        yield f"data: {json.dumps({'content': '', 'done': True})}\n\n"
    except Exception as e:
        error_data = json.dumps({"error": str(e), "done": True}, ensure_ascii=False)
        yield f"data: {error_data}\n\n"


async def generate_sse_stream_with_persist(
    llm_service: LLMService,
    messages: List[Message],
    conversation_id: str,
    user_content: str,
    temperature: Optional[float] = None,
    max_tokens: Optional[int] = None,
    model_id: str = "default",
) -> AsyncGenerator[str, None]:
    """
    流式响应 + 结束后写路径：先落库再更新 Redis，不打断数据流。
    user_content 为本轮用户输入，用于 persist_round；model_id 用于首轮对话后生成标题。
    """
    from services.chat_context import persist_round

    accumulated = []
    try:
        async for content in llm_service.chat_stream(messages, temperature, max_tokens):
            accumulated.append(content)
            data = json.dumps({"content": content, "done": False}, ensure_ascii=False)
            yield f"data: {data}\n\n"

        full_reply = "".join(accumulated)
        await persist_round(conversation_id, user_content, full_reply, model_id=model_id)
        yield f"data: {json.dumps({'content': '', 'done': True})}\n\n"
    except Exception as e:
        error_data = json.dumps({"error": str(e), "done": True}, ensure_ascii=False)
        yield f"data: {error_data}\n\n"
