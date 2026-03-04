from __future__ import annotations

import json
from typing import Any, Awaitable, Callable, Dict, List, Literal, Optional, TypedDict

from routers.models import get_model_config_by_id
from services.llm_service import LLMService

Role = Literal["system", "user", "assistant", "tool"]


class ChatMessage(TypedDict, total=False):
    role: Role
    content: str
    tool_call_id: str
    name: str
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
    """非流式 Tool Calls 调用（向后兼容）。"""
    model_config = get_model_config_by_id(model_id)
    service = LLMService(model_config)
    raw_msg = await service.chat_with_tools(
        messages,
        tools=tools,
        tool_choice="auto",
        temperature=temperature,
        max_tokens=max_tokens,
    )
    return _raw_msg_to_tool_call_message(raw_msg)


async def stream_llm_with_tools(
    messages: List[ChatMessage],
    tools: List[Dict[str, Any]],
    *,
    model_id: str,
    on_content_delta: Optional[Callable[[str], Awaitable[None]]] = None,
    temperature: Optional[float] = None,
    max_tokens: Optional[int] = None,
) -> ToolCallMessage:
    """
    流式 Tool Calls 调用。

    逐 token 通过 on_content_delta 回调推送 content 增量，
    同时在内部累积完整的 content 和 tool_calls，最终返回与
    call_llm_with_tools 相同格式的 ToolCallMessage。
    """
    model_config = get_model_config_by_id(model_id)
    service = LLMService(model_config)

    content_parts: list[str] = []
    # tool_calls 按 index 累积：{index: {"id": ..., "name": ..., "arguments": ...}}
    tc_accum: dict[int, dict[str, str]] = {}

    async for chunk in service.stream_chat_with_tools(
        messages,
        tools=tools,
        tool_choice="auto",
        temperature=temperature,
        max_tokens=max_tokens,
    ):
        if not chunk.choices:
            continue
        delta = chunk.choices[0].delta

        # 文本 token
        if delta.content:
            content_parts.append(delta.content)
            if on_content_delta:
                await on_content_delta(delta.content)

        # 工具调用增量片段
        for tc_delta in delta.tool_calls or []:
            idx = tc_delta.index
            if idx not in tc_accum:
                tc_accum[idx] = {"id": "", "name": "", "arguments": ""}
            entry = tc_accum[idx]
            if tc_delta.id:
                entry["id"] = tc_delta.id
            if tc_delta.function:
                if tc_delta.function.name:
                    entry["name"] += tc_delta.function.name
                if tc_delta.function.arguments:
                    entry["arguments"] += tc_delta.function.arguments

    tool_calls: List[ToolCallInfo] = []
    for idx in sorted(tc_accum):
        e = tc_accum[idx]
        if e["id"] and e["name"]:
            tool_calls.append(
                ToolCallInfo(id=e["id"], name=e["name"], arguments=e["arguments"] or "{}")
            )

    full_content = "".join(content_parts) or None
    return ToolCallMessage(role="assistant", content=full_content, tool_calls=tool_calls)


def _raw_msg_to_tool_call_message(raw_msg: Any) -> ToolCallMessage:
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

