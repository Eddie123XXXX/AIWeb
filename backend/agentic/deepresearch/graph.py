"""
DeepResearch 

多阶段：Plan -> Research -> Write -> Review -> [Revise|Re-Research|Complete]
通过 asyncio.Queue 将 Agent 消息转为 SSE 流式输出。
"""
import asyncio
import logging
from typing import Any, AsyncGenerator, Dict, Literal, Optional

from .state import ResearchPhase, ResearchState, create_initial_state
from .agents import (
    ResearchArchitect,
    Research,
    Writer,
    MarkdownReport,
    Reviewer,
)

logger = logging.getLogger("agentic.deepresearch.graph")


class DeepResearchGraph:
    """多智能体协作工作流"""

    def __init__(self, model_id: str = "deepseek-v3.2", max_iterations: int = 3):
        self.model_id = model_id
        self.max_iterations = max_iterations
        self.architect = ResearchArchitect(model_id=model_id)
        self.research = Research(model_id=model_id)
        self.writer = Writer(model_id=model_id)
        self.markdown_report = MarkdownReport(model_id=model_id)
        self.reviewer = Reviewer(model_id=model_id)

    async def run(
        self,
        query: str,
        session_id: str,
        resume: bool = False,
        user_id: Optional[int] = None,
        search_web: bool = True,
        search_local: bool = False,
        mode: Literal["planning_only", "continue", "full"] = "planning_only",
        approved_outline: Optional[list[dict[str, Any]]] = None,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """流式运行研究流程，yield 事件字典（由调用方格式化为 SSE）。"""
        if resume:
            # 本项目暂不实现检查点，恢复时直接重新开始
            pass
        state = create_initial_state(query, session_id, search_web=search_web, search_local=search_local)
        state["max_iterations"] = self.max_iterations
        state["_user_id"] = user_id
        if approved_outline is not None:
            state["outline"] = approved_outline

        yield {
            "type": "research_start",
            "query": query,
            "session_id": session_id,
            "search_web": search_web,
            "search_local": search_local,
            "mode": mode,
        }

        async for event in self._run_simplified(state, mode=mode):
            yield event

    async def _run_simplified(
        self,
        state: ResearchState,
        mode: Literal["planning_only", "continue", "full"] = "planning_only",
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """手写状态机：各阶段顺序执行，消息队列转 SSE。"""
        message_queue: asyncio.Queue = asyncio.Queue()
        state["_message_queue"] = message_queue

        async def run_agent_with_streaming(agent):
            task = asyncio.create_task(agent.process(state))
            while not task.done():
                try:
                    msg = await asyncio.wait_for(message_queue.get(), timeout=0.5)
                    yield msg
                except asyncio.TimeoutError:
                    continue
            try:
                await task
            except Exception as e:
                logger.exception("Agent %s failed: %s", agent.name, e)
                yield {"type": "error", "content": f"{agent.name}: {str(e)}"}
            while not message_queue.empty():
                try:
                    yield message_queue.get_nowait()
                except asyncio.QueueEmpty:
                    break

        async def run_planning():
            yield {"type": "phase", "phase": "planning", "content": "规划中"}
            state["phase"] = ResearchPhase.INIT.value
            async for msg in run_agent_with_streaming(self.architect):
                yield msg
            state["messages"] = []

        async def run_post_planning():
            yield {"type": "phase", "phase": "researching", "content": "深度搜索中"}
            async for msg in run_agent_with_streaming(self.research):
                yield msg
            state["messages"] = []

            yield {"type": "phase", "phase": "writing", "content": "撰写报告中"}
            state["phase"] = ResearchPhase.WRITING.value
            async for msg in run_agent_with_streaming(self.writer):
                yield msg
            state["messages"] = []

            yield {"type": "phase", "phase": "writing", "content": "整理为 Markdown 文档"}
            async for msg in run_agent_with_streaming(self.markdown_report):
                yield msg
            state["messages"] = []

            while state.get("iteration", 0) < state.get("max_iterations", self.max_iterations):
                yield {"type": "phase", "phase": "reviewing", "content": f"审核中（第 {state.get('iteration', 0) + 1} 轮）..."}
                state["phase"] = ResearchPhase.REVIEWING.value
                async for msg in run_agent_with_streaming(self.reviewer):
                    yield msg
                state["messages"] = []

                phase = state.get("phase", "")
                if phase == ResearchPhase.COMPLETED.value:
                    break
                if phase == ResearchPhase.RE_RESEARCHING.value:
                    yield {"type": "phase", "phase": "re_researching", "content": "补充搜索中"}
                    state["phase"] = ResearchPhase.RE_RESEARCHING.value
                    async for msg in run_agent_with_streaming(self.research):
                        yield msg
                    state["messages"] = []
                    yield {"type": "phase", "phase": "rewriting", "content": "重新撰写中"}
                    state["phase"] = ResearchPhase.WRITING.value
                    async for msg in run_agent_with_streaming(self.writer):
                        yield msg
                    state["messages"] = []
                elif phase == ResearchPhase.REVISING.value:
                    yield {"type": "phase", "phase": "revising", "content": "修订报告中"}
                    state["phase"] = ResearchPhase.REVISING.value
                    async for msg in run_agent_with_streaming(self.writer):
                        yield msg
                    state["messages"] = []
                else:
                    break

        if mode == "planning_only":
            async for msg in run_planning():
                yield msg
            yield {
                "type": "awaiting_outline_confirmation",
                "content": {
                    "outline": state.get("outline", []) or [],
                    "research_questions": state.get("research_questions", []) or [],
                    "message": "请确认章节框架后继续研究",
                },
            }
            state["phase"] = "waiting_approval"
            state["_message_queue"] = None
            return

        if mode == "continue":
            if not isinstance(state.get("outline"), list) or len(state.get("outline") or []) == 0:
                yield {"type": "error", "content": "No approved outline provided for continue mode"}
                state["_message_queue"] = None
                return
            state["phase"] = ResearchPhase.PLANNING.value
            async for msg in run_post_planning():
                yield msg
        elif mode == "full":
            async for msg in run_planning():
                yield msg
            async for msg in run_post_planning():
                yield msg
        else:
            yield {"type": "error", "content": f"Unsupported run mode: {mode}"}
            state["_message_queue"] = None
            return

        state["phase"] = ResearchPhase.COMPLETED.value
        state["_message_queue"] = None

        # 构建前端可用的 references
        refs = []
        for r in state.get("references", []) or []:
            refs.append({
                "id": r.get("id"),
                "title": r.get("source", r.get("title", "N/A")),
                "link": r.get("url", r.get("source_url", "")),
                "content": "",
                "source": r.get("source", "N/A"),
            })

        outline = state.get("outline", []) or []
        outline_for_ui = [{"id": s.get("id"), "title": s.get("title"), "description": s.get("description")} for s in outline]

        yield {
            "type": "research_complete",
            "final_report": state.get("final_report", ""),
            "quality_score": state.get("quality_score", 0.0),
            "facts_count": len(state.get("facts", [])),
            "iterations": state.get("iteration", 0),
            "references": refs,
            "outline": outline_for_ui,
        }

    async def run_sync(self, query: str, session_id: str) -> ResearchState:
        """同步跑完全流程，返回最终 state（用于测试或非流式调用）。"""
        state = create_initial_state(query, session_id, search_web=True, search_local=False)
        state["max_iterations"] = self.max_iterations
        async for _ in self._run_simplified(state, mode="full"):
            pass
        return state
