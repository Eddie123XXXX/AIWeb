from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from typing import Any, Awaitable, Callable, Dict, List, Optional

from .config import get_settings
from .llm_client import ChatMessage, call_llm_with_tools, ToolCallMessage
from .tools_base import ToolContext, ToolExecutionError
from .tools_registry import registry, build_tools_schema


ThoughtCallback = Callable[[str, int], Awaitable[None]]
ActionCallback = Callable[[str, Dict[str, Any], int], Awaitable[None]]
ObservationCallback = Callable[[str, int], Awaitable[None]]
FinalAnswerCallback = Callable[[str], Awaitable[None]]

_loop_logger = logging.getLogger("agentic.loop")
_tool_logger = logging.getLogger("agentic.tools")


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
    """
    最小可用的 ToolContext 实现。

    根据你的项目情况，把数据库连接、当前用户信息等注入进来。
    """

    def __init__(self, user_id: Optional[int] = None) -> None:
        self.user_id = user_id
        self.roles: list[str] | None = None
        self.permissions: set[str] | None = None


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
    on_final_answer: Optional[FinalAnswerCallback] = None,
) -> str:
    """
    核心 Agent Loop：
    - 每轮调用 LLM，让其输出 Thought / Action / Final Answer
    - 遇到 Action 时调用对应 Tool，生成 Observation，再写回对话上下文
    - 直到得到 Final Answer 或达到 MAX_STEPS / 总耗时上限
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

    ctx = SimpleToolContext(user_id=user_id)

    final_answer: Optional[str] = None
    start_ts = time.monotonic()

    _loop_logger.info(
        "[Agentic] 会话开始 | model=%s user_id=%s",
        model_id,
        user_id,
    )

    allowed_tool_set = {name for name in (enabled_tool_names or []) if isinstance(name, str) and name.strip()}
    if enabled_tool_names is None:
        allowed_tool_set = set(registry.tools.keys())
    tools_schema = build_tools_schema(sorted(allowed_tool_set))

    for step in range(settings.llm.max_steps):
        # 总耗时护栏
        elapsed = time.monotonic() - start_ts
        if elapsed > settings.llm.max_total_seconds:
            final_answer = (
                "本次任务已运行较长时间（接近系统设定的上限），为保证整体系统稳定性，"
                "我需要在当前已获取的信息基础上给出阶段性结论。如需更精细的结果，可以在稍后缩小问题范围后重试。"
            )
            _loop_logger.warning(
                "[Agentic] 会话超时熔断 | model=%s user_id=%s elapsed=%.2fs",
                model_id,
                user_id,
                elapsed,
            )
            if on_final_answer:
                await on_final_answer(final_answer)
            break

        # 使用原生 Tool Calls：模型可返回 tool_calls 或直接内容
        model_msg: ToolCallMessage = await call_llm_with_tools(
            messages,
            tools_schema,
            model_id=model_id,
            temperature=temperature,
            max_tokens=max_tokens,
        )

        thought_text = (model_msg.get("content") or "").strip() if model_msg.get("content") else ""
        tool_calls = model_msg.get("tool_calls") or []

        # 若存在工具调用，则将 content 视为 Thought，且需要把带 tool_calls 的 assistant
        # 消息完整写回对话历史（符合 OpenAI Tool Calls 协议要求），再依次执行工具。
        if tool_calls:
            if thought_text:
                _loop_logger.info(
                    "[Agentic] Thought | step=%d model=%s user_id=%s preview=%s",
                    step,
                    model_id,
                    user_id,
                    thought_text[:200] + "..." if len(thought_text) > 200 else thought_text,
                )
                if on_thought:
                    await on_thought(thought_text, step)

            # 记录本轮 assistant 的原始 tool_calls，供后续 tool 消息进行关联
            assistant_msg: dict = {
                "role": "assistant",
                "content": thought_text or "",
                "tool_calls": [],
            }
            for tc in tool_calls:
                assistant_msg["tool_calls"].append(
                    {
                        "id": tc["id"],
                        "type": "function",
                        "function": {
                            "name": tc["name"],
                            "arguments": tc.get("arguments") or "{}",
                        },
                    }
                )
            messages.append(assistant_msg)

            for tc in tool_calls:
                tool_name = tc["name"]
                tool_call_id = tc["id"]
                try:
                    params = json.loads(tc.get("arguments") or "{}")
                except json.JSONDecodeError:
                    params = {}

                _loop_logger.info(
                    "[Agentic] Action | step=%d tool=%s user_id=%s",
                    step,
                    tool_name,
                    user_id,
                )

                if on_action:
                    await on_action(tool_name, params, step)

                # 执行工具，生成 Observation（含错误 Observation 与超时处理）
                try:
                    if tool_name not in allowed_tool_set:
                        raise ToolExecutionError(
                            f"工具 {tool_name} 当前未启用，请选择已启用工具或直接给出无需工具的回答。"
                        )
                    tool = registry.get(tool_name)
                    t0 = time.monotonic()
                    result = await asyncio.wait_for(
                        tool.run(params, ctx),
                        timeout=settings.llm.tool_timeout_seconds,
                    )
                    duration = time.monotonic() - t0
                    obs_content = f"Observation: {result}"
                    _tool_logger.info(
                        "[AgenticTool] Success | tool=%s user_id=%s step=%d duration=%.3fs",
                        tool_name,
                        user_id,
                        step,
                        duration,
                    )
                except asyncio.TimeoutError:
                    obs_content = (
                        "Observation: 工具执行超时，可能是下游服务响应过慢或暂时不可用。"
                        "请考虑稍后重试，或在回答用户时说明当前无法完成该操作。"
                    )
                    _tool_logger.error(
                        "[AgenticTool] Timeout | tool=%s user_id=%s step=%d timeout=%ds",
                        tool_name,
                        user_id,
                        step,
                        settings.llm.tool_timeout_seconds,
                    )
                except ToolExecutionError as exc:
                    obs_content = (
                        f"Observation: 工具执行失败，错误信息：{exc}。"
                        "请尝试调整参数，或在无法修复时向用户解释情况。"
                    )
                    _tool_logger.error(
                        "[AgenticTool] BusinessError | tool=%s user_id=%s step=%d error=%s",
                        tool_name,
                        user_id,
                        step,
                        exc,
                    )
                except Exception as exc:  # noqa: BLE001
                    obs_content = (
                        "Observation: 工具执行遇到未知错误，请在回答用户时明确说明无法完成该操作，"
                        f"错误详情（已记录在系统日志中）：{exc}"
                    )
                    _tool_logger.exception(
                        "[AgenticTool] UnknownError | tool=%s user_id=%s step=%d",
                        tool_name,
                        user_id,
                        step,
                    )

                if on_observation:
                    await on_observation(obs_content, step)

                # 将工具结果作为 tool role 消息追加到对话中，供下一轮调用时参考
                # 注意：原生 Tool Calls 协议要求携带 tool_call_id 用于关联本次输出
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call_id,
                        "name": tool_name,
                        "content": obs_content,
                    }
                )

            # 本轮存在工具调用，不视为终止，继续下一轮
            continue

        # 无工具调用但有 content：优先尝试拆分 Thought / Final Answer
        if thought_text:
            parsed_thought, parsed_final = _split_react_content(thought_text)
            if parsed_thought:
                _loop_logger.info(
                    "[Agentic] Thought(NoTools) | step=%d model=%s user_id=%s preview=%s",
                    step,
                    model_id,
                    user_id,
                    parsed_thought[:200] + "..." if len(parsed_thought) > 200 else parsed_thought,
                )
                if on_thought:
                    await on_thought(parsed_thought, step)

            final_answer = parsed_final or thought_text
            _loop_logger.info(
                "[Agentic] FinalAnswer | step=%d model=%s user_id=%s length=%d",
                step,
                model_id,
                user_id,
                len(final_answer),
            )
            if on_final_answer:
                await on_final_answer(final_answer)
            break

        # 既无 tool_calls 也无 content，视为异常
        obs_text = "Observation: 模型未返回工具调用或回答内容，请根据当前上下文直接给出最终回答。"
        _loop_logger.warning(
            "[Agentic] EmptyResponse | step=%d model=%s user_id=%s",
            step,
            model_id,
            user_id,
        )
        if on_observation:
            await on_observation(obs_text, step)
        messages.append({"role": "assistant", "content": obs_text})

    else:
        # for-else：循环正常结束但未 break，说明触发 MAX_STEPS 熔断
        final_answer = (
            "我已经尝试多次思考并调用工具，但始终未能得到稳定的最终答案。"
            "为了避免死循环，我已主动停止推理。"
            "建议你稍后重新表述问题，或缩小问题范围再试一次。"
        )
        _loop_logger.warning(
            "[Agentic] MaxStepsTriggered | model=%s user_id=%s max_steps=%d",
            model_id,
            user_id,
            settings.llm.max_steps,
        )
        if on_final_answer:
            await on_final_answer(final_answer)

    assert final_answer is not None
    _loop_logger.info(
        "[Agentic] 会话结束 | model=%s user_id=%s total_time=%.2fs",
        model_id,
        user_id,
        time.monotonic() - start_ts,
    )
    return final_answer

