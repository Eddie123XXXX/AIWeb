"""
DeepResearch 研究服务

多智能体协作：Plan → Research → Analyze → Write → Review/Revise。

"""
import json
import logging
import uuid
from typing import Any, Dict, List, Literal, Optional

from models import Message, Role
from routers.models import get_model_config_by_id
from services.llm_service import LLMService

from .utils import serialize_event
from .graph import DeepResearchGraph
from .agents.architect import ResearchArchitect

logger = logging.getLogger("agentic.deepresearch")


class ResearchService:
    """深度研究服务（多智能体协作）。"""

    def __init__(self, model_id: str = "deepseek-v3.2"):
        self.model_id = model_id
        self._graph: Optional[DeepResearchGraph] = None
        self._architect: Optional[ResearchArchitect] = None

    def _get_graph(self) -> DeepResearchGraph:
        if self._graph is None:
            self._graph = DeepResearchGraph(model_id=self.model_id, max_iterations=3)
        return self._graph

    def _get_architect(self) -> ResearchArchitect:
        if self._architect is None:
            self._architect = ResearchArchitect(model_id=self.model_id)
        return self._architect

    def _get_llm_service(self) -> LLMService:
        model_config = get_model_config_by_id(self.model_id)
        return LLMService(model_config)

    async def research_stream(
        self,
        query: str,
        session_id: Optional[str] = None,
        user_id: Optional[int] = None,
        search_web: bool = True,
        search_local: bool = False,
        mode: Literal["planning_only", "continue"] = "planning_only",
        approved_outline: Optional[List[Dict[str, Any]]] = None,
    ):
        """流式执行深度研究，yield SSE 事件字符串（JSON 每行）。"""
        if not session_id:
            session_id = str(uuid.uuid4())
        graph = self._get_graph()
        try:
            async for event in graph.run(
                query=query,
                session_id=session_id,
                resume=False,
                user_id=user_id,
                search_web=search_web,
                search_local=search_local,
                mode=mode,
                approved_outline=approved_outline,
            ):
                yield serialize_event(event)
        except Exception as e:
            logger.exception("DeepResearch stream error: %s", e)
            yield serialize_event({"type": "error", "content": str(e)})
        yield serialize_event({"type": "done"})

    async def rewrite_outline(
        self,
        query: str,
        outline: List[Dict[str, Any]],
        instruction: str,
    ) -> List[Dict[str, Any]]:
        """根据用户自然语言重写章节框架。"""
        architect = self._get_architect()
        return await architect.rewrite_outline(query=query, outline=outline, instruction=instruction)

    async def rewrite_selection(
        self,
        *,
        query: str,
        full_report: str,
        selected_text: str,
        instruction: str,
        start_offset: int,
        end_offset: int,
    ) -> Dict[str, str]:
        """对报告中的选中片段生成候选改写，不直接落库。"""
        llm_service = self._get_llm_service()
        context_window = 1500
        left_context = full_report[max(0, start_offset - context_window):start_offset]
        right_context = full_report[end_offset:min(len(full_report), end_offset + context_window)]
        system_prompt = (
            "你是 DeepResearch 的报告编辑助手。\n"
            "你的任务是只改写用户选中的那一段文本，不要改动选区外内容。\n"
            "请严格返回 JSON，格式为："
            '{"rewritten_text":"...", "summary":"..."}。\n'
            "其中 rewritten_text 只能包含替换选中片段后的新文本，不能包含解释、代码块或额外字段。"
        )
        user_prompt = (
            f"研究主题：{query or '未提供'}\n\n"
            f"修改要求：{instruction.strip()}\n\n"
            "选区前文：\n"
            f"{left_context or '[无]'}\n\n"
            "当前选中文本：\n"
            f"{selected_text}\n\n"
            "选区后文：\n"
            f"{right_context or '[无]'}\n\n"
            "请输出 JSON。"
        )
        response = await llm_service.chat(
            [
                Message(role=Role.SYSTEM, content=system_prompt),
                Message(role=Role.USER, content=user_prompt),
            ],
            temperature=0.2,
            max_tokens=1200,
        )
        cleaned = (response or "").strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.strip("`")
            if cleaned.startswith("json"):
                cleaned = cleaned[4:].strip()
        try:
            payload = json.loads(cleaned)
        except json.JSONDecodeError:
            payload = {"rewritten_text": cleaned, "summary": instruction.strip()}
        rewritten_text = str(payload.get("rewritten_text") or "")
        if not rewritten_text.strip():
            rewritten_text = selected_text
        return {
            "rewritten_text": rewritten_text,
            "summary": str(payload.get("summary") or instruction.strip()),
        }
