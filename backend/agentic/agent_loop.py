from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from typing import Any, Awaitable, Callable, Dict, List, Optional

from .agent_state import AgentCallbacks, AgentDeps, AgentState
from .config import get_settings
from .llm_client import ChatMessage, ToolCallMessage, call_llm_with_tools, stream_llm_with_tools
from .tools_base import ToolContext, ToolExecutionError
from .tools_registry import build_tools_schema, registry

ThoughtCallback = Callable[[str, int], Awaitable[None]]
ActionCallback = Callable[[str, Dict[str, Any], int], Awaitable[None]]
ObservationCallback = Callable[[str, int], Awaitable[None]]
FinalAnswerCallback = Callable[[str], Awaitable[None]]

_loop_logger = logging.getLogger("agentic.loop")
_tool_logger = logging.getLogger("agentic.tools")

# 工具结果模拟流式：每块最大字符数、块间延迟（秒）
OBS_STREAM_CHUNK_SIZE = 80
OBS_STREAM_DELAY = 0.03


def _chunk_observation(text: str) -> list[str]:
    """将工具返回文本按块拆分，用于模拟流式推送。"""
    if not text:
        return []
    return [
        text[i : i + OBS_STREAM_CHUNK_SIZE]
        for i in range(0, len(text), OBS_STREAM_CHUNK_SIZE)
    ]


# ---------------------------------------------------------------------------
# 辅助函数
# ---------------------------------------------------------------------------

def _split_react_content(text: str) -> tuple[str | None, str | None]:
    """
    从模型 content 中拆分 Thought 与 Final Answer。
    兼容以下形态：
    - Thought: ... Final Answer: ...
    - Final Answer: ...
    - 普通回答文本（无标记）
    """
    raw = (text or "").strip()
    if not raw:
        return None, None

    final_match = re.search(r"(?is)final\s*answer\s*:\s*", raw)
    if final_match:
        before = raw[: final_match.start()].strip()
        after = raw[final_match.end() :].strip()
        thought_part: str | None = None
        if before:
            thought_match = re.search(r"(?is)thought\s*:\s*", before)
            thought_part = before[thought_match.end() :].strip() if thought_match else before
        return thought_part or None, after or None

    thought_match = re.search(r"(?is)^\s*thought\s*:\s*", raw)
    if thought_match:
        return raw[thought_match.end() :].strip() or None, None

    return None, raw


class SimpleToolContext:
    """最小可用的 ToolContext 实现。"""

    def __init__(self, user_id: Optional[int] = None) -> None:
        self.user_id = user_id
        self.roles: list[str] | None = None
        self.permissions: set[str] | None = None


# ---------------------------------------------------------------------------
# 状态机节点 (Nodes)
# ---------------------------------------------------------------------------

async def node_call_llm(state: AgentState, deps: AgentDeps) -> AgentState:
    """
    节点：调用大模型。

    检查步数 / 超时护栏，向 LLM 发送当前消息历史和工具 schema，
    根据返回结果路由到 execute_tools / end / force_end。
    """
    elapsed = time.monotonic() - state.start_time
    if elapsed > state.max_total_seconds:
        state.final_answer = (
            "本次任务已运行较长时间（接近系统设定的上限），为保证整体系统稳定性，"
            "我需要在当前已获取的信息基础上给出阶段性结论。如需更精细的结果，可以在稍后缩小问题范围后重试。"
        )
        state.next_node = "force_end"
        _loop_logger.warning(
            "[Agentic] 会话超时熔断 | model=%s user_id=%s elapsed=%.2fs",
            state.model_id, state.user_id, elapsed,
        )
        return state

    if state.steps >= state.max_steps:
        state.final_answer = (
            "我已经尝试多次思考并调用工具，但始终未能得到稳定的最终答案。"
            "为了避免死循环，我已主动停止推理。"
            "建议你稍后重新表述问题，或缩小问题范围再试一次。"
        )
        state.next_node = "force_end"
        _loop_logger.warning(
            "[Agentic] MaxStepsTriggered | model=%s user_id=%s max_steps=%d",
            state.model_id, state.user_id, state.max_steps,
        )
        return state

    tools_schema = deps.registry.get_tools_schema_for(
        state.current_agent, state.enabled_tool_names
    )

    # 判断是否使用流式调用：当 on_stream_delta 回调存在时启用
    use_streaming = deps.callbacks.on_stream_delta is not None

    if use_streaming:
        model_msg: ToolCallMessage = await stream_llm_with_tools(
            state.messages,
            tools_schema,
            model_id=state.model_id,
            on_content_delta=deps.callbacks.on_stream_delta,
            temperature=state.temperature,
            max_tokens=state.max_tokens,
        )
    else:
        model_msg = await call_llm_with_tools(
            state.messages,
            tools_schema,
            model_id=state.model_id,
            temperature=state.temperature,
            max_tokens=state.max_tokens,
        )

    thought_text = (model_msg.get("content") or "").strip() if model_msg.get("content") else ""
    tool_calls = model_msg.get("tool_calls") or []

    if tool_calls:
        if thought_text:
            _loop_logger.info(
                "[Agentic] Thought | step=%d model=%s user_id=%s preview=%s",
                state.steps, state.model_id, state.user_id,
                thought_text[:200] + "..." if len(thought_text) > 200 else thought_text,
            )
            if deps.callbacks.on_thought:
                await deps.callbacks.on_thought(thought_text, state.steps)

        assistant_msg: dict = {
            "role": "assistant",
            "content": thought_text or "",
            "tool_calls": [
                {
                    "id": tc["id"],
                    "type": "function",
                    "function": {
                        "name": tc["name"],
                        "arguments": tc.get("arguments") or "{}",
                    },
                }
                for tc in tool_calls
            ],
        }
        state.messages.append(assistant_msg)
        state.next_node = "execute_tools"
        return state

    if thought_text:
        parsed_thought, parsed_final = _split_react_content(thought_text)
        if parsed_thought:
            _loop_logger.info(
                "[Agentic] Thought(NoTools) | step=%d model=%s user_id=%s preview=%s",
                state.steps, state.model_id, state.user_id,
                parsed_thought[:200] + "..." if len(parsed_thought) > 200 else parsed_thought,
            )
            if deps.callbacks.on_thought:
                await deps.callbacks.on_thought(parsed_thought, state.steps)

        state.final_answer = parsed_final or thought_text
        _loop_logger.info(
            "[Agentic] FinalAnswer | step=%d model=%s user_id=%s length=%d",
            state.steps, state.model_id, state.user_id, len(state.final_answer),
        )
        state.steps += 1
        state.next_node = "end"
        return state

    obs_text = "Observation: 模型未返回工具调用或回答内容，请根据当前上下文直接给出最终回答。"
    _loop_logger.warning(
        "[Agentic] EmptyResponse | step=%d model=%s user_id=%s",
        state.steps, state.model_id, state.user_id,
    )
    if deps.callbacks.on_observation:
        await deps.callbacks.on_observation(obs_text, state.steps)
    state.messages.append({"role": "assistant", "content": obs_text})
    state.steps += 1
    state.next_node = "call_llm"
    return state


async def node_execute_tools(state: AgentState, deps: AgentDeps) -> AgentState:
    """
    节点：执行工具调用。

    遍历最后一条 assistant 消息中的 tool_calls，逐一执行，
    将结果作为 tool role 消息追加到对话历史。
    执行完毕后路由回 call_llm 进行下一轮评估。
    """
    last_message = state.messages[-1]
    tool_calls = last_message.get("tool_calls") or []

    allowed_set = state.enabled_tool_names

    for tc in tool_calls:
        tool_name = tc["function"]["name"] if "function" in tc else tc.get("name", "")
        tool_call_id = tc.get("id", "")
        try:
            raw_args = tc["function"]["arguments"] if "function" in tc else tc.get("arguments", "{}")
            params = json.loads(raw_args)
        except (json.JSONDecodeError, KeyError):
            params = {}

        _loop_logger.info(
            "[Agentic] Action | step=%d tool=%s user_id=%s",
            state.steps, tool_name, state.user_id,
        )

        if deps.callbacks.on_action:
            await deps.callbacks.on_action(tool_name, params, state.steps)

        try:
            if allowed_set is not None and tool_name not in allowed_set:
                raise ToolExecutionError(
                    f"工具 {tool_name} 当前未启用，请选择已启用工具或直接给出无需工具的回答。"
                )
            tool = deps.registry.get(tool_name)
            t0 = time.monotonic()
            result = await asyncio.wait_for(
                tool.run(params, deps.tool_ctx),
                timeout=deps.tool_timeout_seconds,
            )
            duration = time.monotonic() - t0
            obs_content = f"Observation: {result}"
            _tool_logger.info(
                "[AgenticTool] Success | tool=%s user_id=%s step=%d duration=%.3fs",
                tool_name, state.user_id, state.steps, duration,
            )
        except asyncio.TimeoutError:
            obs_content = (
                "Observation: 工具执行超时，可能是下游服务响应过慢或暂时不可用。"
                "请考虑稍后重试，或在回答用户时说明当前无法完成该操作。"
            )
            state.errors.append(f"Timeout: {tool_name}")
            _tool_logger.error(
                "[AgenticTool] Timeout | tool=%s user_id=%s step=%d timeout=%ds",
                tool_name, state.user_id, state.steps, deps.tool_timeout_seconds,
            )
        except ToolExecutionError as exc:
            obs_content = (
                f"Observation: 工具执行失败，错误信息：{exc}。"
                "请尝试调整参数，或在无法修复时向用户解释情况。"
            )
            state.errors.append(f"ToolError({tool_name}): {exc}")
            _tool_logger.error(
                "[AgenticTool] BusinessError | tool=%s user_id=%s step=%d error=%s",
                tool_name, state.user_id, state.steps, exc,
            )
        except Exception as exc:  # noqa: BLE001
            obs_content = (
                "Observation: 工具执行遇到未知错误，请在回答用户时明确说明无法完成该操作，"
                f"错误详情（已记录在系统日志中）：{exc}"
            )
            state.errors.append(f"UnknownError({tool_name}): {exc}")
            _tool_logger.exception(
                "[AgenticTool] UnknownError | tool=%s user_id=%s step=%d",
                tool_name, state.user_id, state.steps,
            )

        # 若有 observation_delta 回调，先按块流式推送，再发送完整 observation
        if deps.callbacks.on_observation_delta:
            for chunk in _chunk_observation(obs_content):
                await deps.callbacks.on_observation_delta(chunk, state.steps)
                await asyncio.sleep(OBS_STREAM_DELAY)
        if deps.callbacks.on_observation:
            await deps.callbacks.on_observation(obs_content, state.steps)

        state.messages.append(
            {
                "role": "tool",
                "tool_call_id": tool_call_id,
                "name": tool_name,
                "content": obs_content,
            }
        )

    # 本轮 thought → action → observation 完成，递增步数
    state.steps += 1
    state.next_node = "call_llm"
    return state


# ---------------------------------------------------------------------------
# 节点注册表
# ---------------------------------------------------------------------------

NODE_MAP: Dict[str, Callable[[AgentState, AgentDeps], Any]] = {
    "call_llm": node_call_llm,
    "execute_tools": node_execute_tools,
}


# ---------------------------------------------------------------------------
# 图执行引擎 (Graph Runner)
# ---------------------------------------------------------------------------

async def run_agent_graph(state: AgentState, deps: AgentDeps) -> AgentState:
    """
    轻量级状态机流转引擎。

    反复查询 state.next_node 找到对应的节点函数执行，
    直到 next_node 变为 "end" / "force_end" 或 None。
    """
    terminal_nodes = {"end", "force_end"}

    while state.next_node and state.next_node not in terminal_nodes:
        node_fn = NODE_MAP.get(state.next_node)
        if node_fn is None:
            _loop_logger.error(
                "[Agentic] 未知节点: %s，强制终止", state.next_node
            )
            state.next_node = "force_end"
            state.final_answer = "系统内部路由错误，已安全终止。"
            break
        state = await node_fn(state, deps)

    if state.next_node == "force_end":
        if state.final_answer is None:
            state.final_answer = "任务过于复杂，我已停止思考以保护系统资源。"
        if deps.callbacks.on_final_answer:
            await deps.callbacks.on_final_answer(state.final_answer)
    elif state.next_node == "end":
        if deps.callbacks.on_final_answer and state.final_answer:
            await deps.callbacks.on_final_answer(state.final_answer)

    return state


# ---------------------------------------------------------------------------
# 公开 API：兼容旧的 run_agentic_session 签名
# ---------------------------------------------------------------------------

async def run_agentic_session(
    *,
    user_query: str,
    system_prompt: str,
    model_id: str,
    user_id: Optional[int] = None,
    history_messages: Optional[List[ChatMessage]] = None,
    enabled_tool_names: Optional[List[str]] = None,
    temperature: Optional[float] = None,
    max_tokens: Optional[int] = None,
    on_thought: Optional[ThoughtCallback] = None,
    on_action: Optional[ActionCallback] = None,
    on_observation: Optional[ObservationCallback] = None,
    on_observation_delta: Optional[Callable[[str, int], Awaitable[None]]] = None,
    on_final_answer: Optional[FinalAnswerCallback] = None,
    on_stream_delta: Optional[Callable[[str], Awaitable[None]]] = None,
    current_agent: str = "supervisor",
) -> str:
    """
    核心 Agent Loop 的公开入口。

    向后兼容旧调用方签名，内部委托给状态机图引擎 run_agent_graph。
    """
    settings = get_settings()

    messages: List[ChatMessage] = [{"role": "system", "content": system_prompt}]
    if history_messages:
        for msg in history_messages:
            role = msg.get("role")
            content = msg.get("content")
            if role in {"system", "user", "assistant"} and isinstance(content, str) and content.strip():
                messages.append({"role": role, "content": content})
    messages.append({"role": "user", "content": user_query})

    allowed_tool_set: Optional[set[str]] = None
    if enabled_tool_names is None:
        allowed_tool_set = set(registry.tools.keys())
    else:
        allowed_tool_set = {name for name in enabled_tool_names if isinstance(name, str) and name.strip()}

    state = AgentState(
        messages=messages,
        current_agent=current_agent,
        steps=0,
        max_steps=settings.llm.max_steps,
        max_total_seconds=settings.llm.max_total_seconds,
        start_time=time.monotonic(),
        model_id=model_id,
        user_id=user_id,
        temperature=temperature,
        max_tokens=max_tokens,
        enabled_tool_names=allowed_tool_set,
        next_node="call_llm",
    )

    ctx = SimpleToolContext(user_id=user_id)

    callbacks = AgentCallbacks(
        on_thought=on_thought,
        on_action=on_action,
        on_observation=on_observation,
        on_observation_delta=on_observation_delta,
        on_final_answer=on_final_answer,
        on_stream_delta=on_stream_delta,
    )

    deps = AgentDeps(
        registry=registry,
        tool_ctx=ctx,
        callbacks=callbacks,
        tool_timeout_seconds=settings.llm.tool_timeout_seconds,
    )

    _loop_logger.info(
        "[Agentic] 会话开始 | model=%s user_id=%s agent=%s",
        model_id, user_id, current_agent,
    )

    final_state = await run_agent_graph(state, deps)

    assert final_state.final_answer is not None
    _loop_logger.info(
        "[Agentic] 会话结束 | model=%s user_id=%s total_time=%.2fs steps=%d errors=%d",
        model_id, user_id,
        time.monotonic() - final_state.start_time,
        final_state.steps,
        len(final_state.errors),
    )
    return final_state.final_answer
