"""
DeepResearch - 报告撰写 Agent (Writer)

将大纲、事实、数据点整合为完整报告。
"""
import uuid
from typing import Any, Dict, List

from .base import BaseAgent
from ..state import ResearchState, ResearchPhase


class Writer(BaseAgent):
    """Writer - 报告撰写。"""

    SECTION_PROMPT = """你是一位行业研究分析师。请根据以下素材撰写报告的一节。

研究主题：{query}
本节标题：{section_title}
本节描述：{section_description}

相关事实：
{facts}

数据点：
{data_points}

要求：本节 300-600 字，使用 Markdown，关键数据需注明来源。只输出本节正文，不要重复标题。
输出格式 JSON：{{"content": "正文内容", "key_points": ["要点1","要点2"], "citations": [{{"source":"来源名","url":"URL"}}]}}"""

    SYNTHESIS_PROMPT = """你是报告主编。请将各节整合为完整研究报告（Markdown）。

研究主题：{query}

各节内容：
{sections_content}

引用来源：
{all_sources}

要求：
1. 含执行摘要、各节内容、结论与展望、参考文献。
2. 一级标题用 ##，二级用 ###。
3. 数据与结论需有来源标注。
输出 JSON：{{"full_report": "完整报告正文", "executive_summary": "摘要", "conclusions": ["结论1","结论2"], "references": []}}"""

    REVISION_PROMPT = """根据审核反馈修订报告。

原始报告（节选）：
{original_content}

审核反馈：
{feedback}

补充信息：
{new_info}

只修改有问题部分，保持风格一致。输出 JSON：{{"revised_content": "修订后全文", "changes_made": ["修改1"], "addressed_issues": [], "unable_to_address": []}}"""

    def __init__(self, model_id: str = "default"):
        super().__init__(name="Writer", role="writer", model_id=model_id)

    async def process(self, state: ResearchState) -> ResearchState:
        if state.get("phase") == ResearchPhase.WRITING.value:
            return await self._write_report(state)
        if state.get("phase") == ResearchPhase.REVISING.value:
            return await self._revise_report(state)
        return state

    async def _write_report(self, state: ResearchState) -> ResearchState:
        self.add_message(state, "research_step", {
            "step_type": "writing",
            "title": "内容生成",
            "subtitle": "撰写研究报告",
            "status": "running",
            "stats": {"sections_count": len(state.get("outline", []))},
        })
        self.add_message(state, "thought", {"agent": self.name, "content": "开始撰写深度研究报告..."})

        outline = state.get("outline", [])
        draft_sections = state.get("draft_sections", {})
        facts = state.get("facts", [])
        data_points = state.get("data_points", [])
        references = state.get("references", [])

        for section in outline:
            if section.get("status") in ("final", "drafted"):
                continue
            sid = section.get("id", "")
            related = [f for f in facts if sid in f.get("related_sections", [])][:10]
            if not related:
                related = facts[:10]
            facts_text = "\n".join(f"- {f.get('content','')[:300]} (来源: {f.get('source_name','')})" for f in related)
            data_text = "\n".join(f"- {d.get('name','')}: {d.get('value','')} {d.get('unit','')}" for d in data_points[:10])

            prompt = self.SECTION_PROMPT.format(
                query=state["query"],
                section_title=section.get("title", ""),
                section_description=section.get("description", ""),
                facts=facts_text or "（暂无）",
                data_points=data_text or "（暂无）",
            )
            resp = await self.call_llm(
                system_prompt="你是行业研究分析师，输出严格 JSON。",
                user_prompt=prompt,
                json_mode=True,
                temperature=0.4,
                max_tokens=4096,
            )
            result = self.parse_json_response(resp)
            if result and result.get("content"):
                draft_sections[sid] = result["content"]
                section["status"] = "drafted"
                self.add_message(state, "section_content", {
                    "section_id": sid,
                    "section_title": section.get("title"),
                    "content": result["content"],
                    "key_points": result.get("key_points", []),
                })
                for c in result.get("citations", []) or []:
                    references.append({"id": len(references) + 1, "source": c.get("source"), "url": c.get("url", "")})

        state["draft_sections"] = draft_sections
        state["references"] = references

        sections_content = []
        for sec in outline:
            sid = sec.get("id", "")
            content = draft_sections.get(sid, "")
            if content:
                sections_content.append(f"## {sec.get('title','')}\n{content}")
        all_sources = [f"- {r.get('source','')} ({r.get('url','')})" for r in references[:30]]

        syn_prompt = self.SYNTHESIS_PROMPT.format(
            query=state["query"],
            sections_content="\n\n".join(sections_content) if sections_content else "（暂无）",
            all_sources="\n".join(all_sources) if all_sources else "（暂无）",
        )
        syn_resp = await self.call_llm(
            system_prompt="你是报告主编，输出严格 JSON。",
            user_prompt=syn_prompt,
            json_mode=True,
            temperature=0.3,
            max_tokens=8192,
        )
        syn_result = self.parse_json_response(syn_resp)
        if syn_result and syn_result.get("full_report"):
            state["final_report"] = syn_result["full_report"]
        else:
            state["final_report"] = "\n\n".join(sections_content) or "（未能生成报告）"

        self.add_message(state, "report_draft", {
            "content": state["final_report"],
            "executive_summary": syn_result.get("executive_summary", "") if syn_result else "",
            "conclusions": syn_result.get("conclusions", []) if syn_result else [],
            "word_count": len(state["final_report"]),
            "references_count": len(references),
        })
        state["phase"] = ResearchPhase.REVIEWING.value
        self.add_message(state, "research_step", {
            "step_type": "writing",
            "title": "内容生成",
            "subtitle": "撰写完成",
            "status": "completed",
            "stats": {"word_count": len(state["final_report"]), "references_count": len(references)},
        })
        return state

    async def _revise_report(self, state: ResearchState) -> ResearchState:
        self.add_message(state, "thought", {"agent": self.name, "content": "根据审核反馈修订报告..."})
        feedback_list = state.get("reviewer_feedback", [])
        unresolved = [f for f in feedback_list if not f.get("resolved")]
        feedback_text = "\n".join(
            f"- [{f.get('severity')}] {f.get('description','')}\n  建议: {f.get('suggestion','')}" for f in unresolved[:10]
        )
        new_facts = state.get("facts", [])[-5:]
        new_info = "\n".join(f"- {f.get('content','')[:200]}" for f in new_facts)

        prompt = self.REVISION_PROMPT.format(
            original_content=(state.get("final_report") or "")[:6000],
            feedback=feedback_text or "无",
            new_info=new_info or "无",
        )
        resp = await self.call_llm(
            system_prompt="你是负责修订的编辑，输出严格 JSON。",
            user_prompt=prompt,
            json_mode=True,
            temperature=0.3,
            max_tokens=8192,
        )
        result = self.parse_json_response(resp)
        if result and result.get("revised_content"):
            state["final_report"] = result["revised_content"]
            for issue_id in result.get("addressed_issues", []) or []:
                for f in state.get("reviewer_feedback", []):
                    if f.get("id") == issue_id:
                        f["resolved"] = True
            self.add_message(state, "revision_complete", {
                "changes_count": len(result.get("changes_made", [])),
                "addressed_issues": result.get("addressed_issues", []),
            })
        state["phase"] = ResearchPhase.REVIEWING.value
        return state
