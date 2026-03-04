from __future__ import annotations

import logging
import time
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field

from ..tools_base import ToolContext, ToolExecutionError

logger = logging.getLogger("agentic.worker")


class WorkerToolParams(BaseModel):
    """Worker Tool 的标准入参：由 Supervisor 发起调用时传递。"""

    query: str = Field(description="需要 Worker 处理的具体问题或指令")
    context: str = Field(default="", description="可选的附加上下文信息（如文件路径、数据源等）")


class WorkerTool:
    """
    将一个专业领域的子 Agent 封装为标准 Tool。

    Supervisor 的 tools 列表中注册的不是普通 Python 函数，
    而是由 WorkerTool 包装的、拥有独立 System Prompt 和工具集的子 Agent。

    数据流：
    1. Supervisor 输出 tool_calls: [{"name": "rag_worker", "arguments": {...}}]
    2. 后端触发 WorkerTool.run()，内部启动子状态机 run_agent_graph()
    3. Worker 独立完成所有 Thought/Action 循环
    4. Worker 的最终回答作为 Observation 返回给 Supervisor
    """

    param_model = WorkerToolParams

    def __init__(
        self,
        *,
        name: str,
        description: str,
        system_prompt: str,
        worker_agent_name: str,
        model_id: Optional[str] = None,
        max_steps: int = 10,
        max_total_seconds: int = 300,
    ) -> None:
        self.name = name
        self.description = description
        self._system_prompt = system_prompt
        self._worker_agent_name = worker_agent_name
        self._model_id = model_id
        self._max_steps = max_steps
        self._max_total_seconds = max_total_seconds

    async def run(self, params: Dict[str, Any], ctx: ToolContext) -> str:
        from ..agent_loop import SimpleToolContext, run_agent_graph
        from ..agent_state import AgentCallbacks, AgentDeps, AgentState
        from ..tools_registry import registry

        query = params.get("query", "")
        context = params.get("context", "")
        if not query:
            raise ToolExecutionError(f"WorkerTool {self.name}: 缺少 query 参数")

        user_content = query
        if context:
            user_content = f"{query}\n\n附加上下文：{context}"

        messages = [
            {"role": "system", "content": self._system_prompt},
            {"role": "user", "content": user_content},
        ]

        parent_model_id = getattr(ctx, "_model_id", None)
        effective_model_id = self._model_id or parent_model_id or "default"

        child_state = AgentState(
            messages=messages,
            current_agent=self._worker_agent_name,
            steps=0,
            max_steps=self._max_steps,
            max_total_seconds=self._max_total_seconds,
            start_time=time.monotonic(),
            model_id=effective_model_id,
            user_id=ctx.user_id,
            next_node="call_llm",
        )

        child_ctx = SimpleToolContext(user_id=ctx.user_id)

        child_deps = AgentDeps(
            registry=registry,
            tool_ctx=child_ctx,
            callbacks=AgentCallbacks(),
            tool_timeout_seconds=60,
        )

        logger.info(
            "[Worker] 子 Agent 启动 | worker=%s agent=%s model=%s",
            self.name, self._worker_agent_name, effective_model_id,
        )

        try:
            final_state = await run_agent_graph(child_state, child_deps)
        except Exception as exc:
            logger.exception("[Worker] 子 Agent 执行失败 | worker=%s", self.name)
            raise ToolExecutionError(
                f"WorkerTool {self.name} 的子 Agent 执行失败: {exc}"
            ) from exc

        result = final_state.final_answer or "Worker 未能产生有效结果。"
        logger.info(
            "[Worker] 子 Agent 完成 | worker=%s steps=%d errors=%d result_len=%d",
            self.name, final_state.steps, len(final_state.errors), len(result),
        )
        return result
