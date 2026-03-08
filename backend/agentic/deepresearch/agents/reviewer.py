"""
DeepResearch - 审核 Agent (Reviewer)
"""
import uuid
from typing import Any, Dict, List

from .base import BaseAgent
from ..state import ResearchState, ResearchPhase


class Reviewer(BaseAgent):
    """Reviewer - 质量审核。"""

    REVIEW_PROMPT = """你是严苛的审稿人。请审核以下研究报告并找出问题。

研究问题：{query}

大纲：{outline}

报告内容：
{draft_content}

引用事实摘要：
{facts}

数据点：
{data_points}

输出 JSON：
{{
  "overall_assessment": {{ "quality_score": 1-10, "verdict": "pass/needs_revision/major_issues", "summary": "摘要" }},
  "issues": [
    {{ "id": "issue_1", "target_section": "章节ID或全局", "issue_type": "missing_source/logic_error/bias/hallucination/outdated/incomplete", "severity": "critical/major/minor", "description": "问题描述", "suggestion": "修改建议", "requires_new_search": true/false, "search_query": "如需补充搜索时的关键词" }}
  ],
  "missing_aspects": ["遗漏的方面"]
}}

quality_score >= 7 时 verdict 才可为 "pass"。"""

    def __init__(self, model_id: str = "default"):
        super().__init__(name="Reviewer", role="reviewer", model_id=model_id)

    async def process(self, state: ResearchState) -> ResearchState:
        if state.get("phase") != ResearchPhase.REVIEWING.value:
            return state

        self.add_message(state, "thought", {"agent": self.name, "content": "开始严格审核研究报告..."})

        outline = state.get("outline", [])
        outline_summary = [f"- {s.get('id')}: {s.get('title')} ({s.get('status','')})" for s in outline]
        draft_content = ""
        for sid, content in state.get("draft_sections", {}).items():
            sec = next((x for x in outline if x.get("id") == sid), {})
            draft_content += f"\n## {sec.get('title', sid)}\n{content}\n"
        if not draft_content:
            draft_content = state.get("final_report", "（暂无）")
        facts_summary = [f"- {f.get('id')} {f.get('content','')[:120]} (来源: {f.get('source_name','')})" for f in state.get("facts", [])[:20]]
        data_summary = [f"- {d.get('name')}: {d.get('value')} {d.get('unit','')}" for d in state.get("data_points", [])[:15]]

        prompt = self.REVIEW_PROMPT.format(
            query=state["query"],
            outline="\n".join(outline_summary),
            draft_content=draft_content[:8000],
            facts="\n".join(facts_summary) if facts_summary else "（暂无）",
            data_points="\n".join(data_summary) if data_summary else "（暂无）",
        )
        response = await self.call_llm(
            system_prompt="你是质量审核专家，专门找出报告中的问题。输出严格 JSON。",
            user_prompt=prompt,
            json_mode=True,
            temperature=0.2,
            max_tokens=4096,
        )
        result = self.parse_json_response(response)
        if not result:
            state["phase"] = ResearchPhase.COMPLETED.value
            return state

        for issue in result.get("issues", []) or []:
            issue["id"] = f"issue_{uuid.uuid4().hex[:8]}"
            issue["resolved"] = False
            state.setdefault("reviewer_feedback", []).append(issue)

        assessment = result.get("overall_assessment", {})
        state["quality_score"] = assessment.get("quality_score", 0.0)
        state["unresolved_issues"] = len([i for i in result.get("issues", []) if i.get("severity") in ("critical", "major")])

        self.add_message(state, "review", {
            "verdict": assessment.get("verdict"),
            "quality_score": state["quality_score"],
            "issues_count": len(result.get("issues", [])),
            "summary": assessment.get("summary", ""),
            "missing_aspects": result.get("missing_aspects", []),
        })

        verdict = assessment.get("verdict", "needs_revision")
        if verdict == "pass":
            state["phase"] = ResearchPhase.COMPLETED.value
            return state
        if state.get("iteration", 0) >= state.get("max_iterations", 3):
            state["phase"] = ResearchPhase.COMPLETED.value
            self.add_message(state, "warning", {"agent": self.name, "content": "已达最大迭代次数"})
            return state

        needs_search = self._analyze_routing(result)
        if needs_search["should_research"]:
            state["phase"] = ResearchPhase.RE_RESEARCHING.value
            state["pending_search_queries"] = needs_search["search_queries"]
            self.add_message(state, "thought", {"agent": self.name, "content": "需要补充搜索后再修订"})
        else:
            state["phase"] = ResearchPhase.REVISING.value
        state["iteration"] = state.get("iteration", 0) + 1
        return state

    def _analyze_routing(self, review_result: Dict[str, Any]) -> Dict[str, Any]:
        issues = review_result.get("issues", []) or []
        research_types = {"missing_source", "incomplete", "outdated"}
        search_queries = []
        for i in issues:
            if i.get("issue_type") in research_types and i.get("severity") in ("critical", "major"):
                if i.get("requires_new_search") and i.get("search_query"):
                    search_queries.append(i["search_query"])
        for a in review_result.get("missing_aspects", [])[:3]:
            search_queries.append(a)
        should = len(search_queries) > 0 and any(
            i.get("issue_type") in research_types and i.get("severity") in ("critical", "major") for i in issues
        )
        return {"should_research": should, "search_queries": list(dict.fromkeys(search_queries))[:5]}
