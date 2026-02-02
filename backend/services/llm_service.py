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
    
    async def chat(
        self,
        messages: List[Message],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None
    ) -> str:
        """非流式对话"""
        response = await self.client.chat.completions.create(
            model=self.config.model_name,
            messages=[{"role": m.role.value, "content": m.content} for m in messages],
            temperature=temperature or self.config.temperature,
            max_tokens=max_tokens or self.config.max_tokens,
            stream=False
        )
        return response.choices[0].message.content
    
    async def chat_stream(
        self,
        messages: List[Message],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None
    ) -> AsyncGenerator[str, None]:
        """流式对话"""
        response = await self.client.chat.completions.create(
            model=self.config.model_name,
            messages=[{"role": m.role.value, "content": m.content} for m in messages],
            temperature=temperature or self.config.temperature,
            max_tokens=max_tokens or self.config.max_tokens,
            stream=True
        )
        
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
