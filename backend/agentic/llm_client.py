from __future__ import annotations

import json
from typing import Any, Dict, List, Literal, Optional, TypedDict

from routers.models import get_model_config_by_id
from services.llm_service import LLMService

Role = Literal["system", "user", "assistant", "tool"]


class ChatMessage(TypedDict, total=False):
    role: Role
    content: str
    # 对于 tool 消息，需要带上 tool_call_id（以及可选的 name）
    tool_call_id: str
    name: str
    # 对于带 tool_calls 的 assistant 消息，需要携带原始 tool_calls 结构
    tool_calls: List[Dict[str, Any]]


class ToolCallInfo(TypedDict):
    id: str
    name: str
    arguments: str


class ToolCallMessage(TypedDict):
    role: Literal["assistant"]
    content: Optional[str]
    tool_calls: List[ToolCallInfo]


async def call_llm_with_tools(
    messages: List[ChatMessage],
    tools: List[Dict[str, Any]],
    *,
    model_id: str,
    temperature: Optional[float] = None,
    max_tokens: Optional[int] = None,
) -> ToolCallMessage:
    """
    使用 OpenAI/DeepSeek 原生 Tool Calls 能力：
    - tools: 来自 tools_registry.build_tools_schema() 的函数定义列表
    - 返回统一的 dict，包含 content 与 tool_calls（若有）
    """
    model_config = get_model_config_by_id(model_id)
    service = LLMService(model_config)
    # messages 此处已经是符合 OpenAI schema 的原始 dict（包括 tool_call_id 等字段），
    # 直接传递给底层 client，避免通过 Pydantic Message 丢失字段。
    raw_msg = await service.chat_with_tools(
        messages,
        tools=tools,
        tool_choice="auto",
        temperature=temperature,
        max_tokens=max_tokens,
    )

    # 将 OpenAI 返回的 message 转为普通 dict，避免外部依赖 SDK 具体类型
    tool_calls: List[ToolCallInfo] = []
    for tc in getattr(raw_msg, "tool_calls", []) or []:
        try:
            fn = tc.function
            tool_calls.append(
                ToolCallInfo(
                    id=str(tc.id),
                    name=str(fn.name),
                    arguments=str(fn.arguments or "{}"),
                )
            )
        except Exception:
            continue

    return ToolCallMessage(
        role="assistant",
        content=getattr(raw_msg, "content", None),
        tool_calls=tool_calls,
    )

