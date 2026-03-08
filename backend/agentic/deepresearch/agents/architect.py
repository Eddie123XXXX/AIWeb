"""
DeepResearch - 架构设计 Agent (ResearchArchitect)

问题理解与研究大纲规划。
"""
import json
import uuid
from typing import Any, Dict, List

from .base import BaseAgent
from ..state import ResearchState, ResearchPhase
from ..utils import normalize_editable_outline


class ResearchArchitect(BaseAgent):
    """架构设计 Agent - 研究规划。"""

    PLANNING_PROMPT = """研究课题：{query}

请为该课题生成研究大纲，输出 JSON 格式如下（不要 markdown 代码块）：

{{
  "outline": [
    {{"id": "sec_1", "title": "章节标题", "description": "描述", "section_type": "mixed", "requires_data": true, "requires_chart": false, "search_queries": ["关键词1", "关键词2"]}},
    ...共 5-8 个章节...
  ],
  "research_questions": ["核心问题1", "核心问题2", "核心问题3"],
  "key_entities": []
}}

要求：outline 必须包含 5-8 个章节，覆盖市场概况、竞争格局、技术趋势、政策环境、未来展望等。"""

    REWRITE_PROMPT = """研究课题：{query}

当前章节框架：
{outline_json}

用户希望这样调整章节框架：
{instruction}

请在保留研究完整性的前提下，重构章节框架，并只输出 JSON：
{{
  "outline": [
    {{"id": "sec_1", "title": "章节标题", "description": "描述", "section_type": "mixed", "requires_data": false, "requires_chart": false, "search_queries": ["关键词1", "关键词2"]}}
  ]
}}

要求：
1. 输出 4-8 个章节
2. 章节标题与说明要呼应用户重构意图
3. 每个章节都要带 search_queries，便于后续继续研究
4. 不要输出 markdown 代码块"""

    def __init__(self, model_id: str = "default"):
        super().__init__(name="ResearchArchitect", role="架构设计agent", model_id=model_id)

    def _ensure_outline_format(self, outline: List[Dict], query: str) -> List[Dict]:
        """确保每个章节有必备字段。"""
        return normalize_editable_outline(outline, query=query)

    async def process(self, state: ResearchState) -> ResearchState:
        if state.get("phase") != ResearchPhase.INIT.value:
            return state
        self.add_message(state, "research_step", {
            "step_id": f"step_planning_{uuid.uuid4().hex[:8]}",
            "step_type": "planning",
            "title": "研究计划",
            "subtitle": "分析问题，制定大纲",
            "status": "running",
            "stats": {},
        })
        self.add_message(state, "thought", {"agent": self.name, "content": "正在分析研究问题，构建研究大纲..."})

        prompt = self.PLANNING_PROMPT.format(query=state["query"])
        response = await self.call_llm(
            system_prompt="你是一位专业的行业研究规划师。请严格按照 JSON 格式输出。",
            user_prompt=prompt,
            json_mode=True,
            temperature=0.3,
            max_tokens=8192,
        )
        result = self.parse_json_response(response)
        outline = result.get("outline") or []
        if len(outline) < 3:
            outline = [
                {"id": "sec_1", "title": "概述", "description": "", "search_queries": [state["query"][:50]]},
                {"id": "sec_2", "title": "现状分析", "description": "", "search_queries": [state["query"][:50]]},
                {"id": "sec_3", "title": "趋势与展望", "description": "", "search_queries": [state["query"][:50]]},
            ]
        processed = self._ensure_outline_format(outline, state["query"])
        state["outline"] = processed
        state["research_questions"] = result.get("research_questions", [])
        state["phase"] = ResearchPhase.PLANNING.value

        self.add_message(state, "outline", {
            "outline": processed,
            "research_questions": state["research_questions"],
        })
        self.add_message(state, "research_step", {
            "step_type": "planning",
            "title": "研究计划",
            "subtitle": "分析问题，制定大纲",
            "status": "completed",
            "stats": {"sections_count": len(processed), "questions_count": len(state["research_questions"])},
        })
        return state

    async def rewrite_outline(self, query: str, outline: List[Dict[str, Any]], instruction: str) -> List[Dict[str, Any]]:
        """根据用户自然语言指令重构章节框架。"""
        prompt = self.REWRITE_PROMPT.format(
            query=query,
            outline_json=json.dumps(outline, ensure_ascii=False),
            instruction=instruction,
        )
        response = await self.call_llm(
            system_prompt="你是一位专业研究规划师。请根据用户的重构意图调整章节框架，并严格输出 JSON。",
            user_prompt=prompt,
            json_mode=True,
            temperature=0.4,
            max_tokens=8192,
        )
        result = self.parse_json_response(response)
        rewritten_outline = result.get("outline") or []
        if not isinstance(rewritten_outline, list) or len(rewritten_outline) == 0:
            return self._ensure_outline_format(outline, query)
        return self._ensure_outline_format(rewritten_outline, query)
