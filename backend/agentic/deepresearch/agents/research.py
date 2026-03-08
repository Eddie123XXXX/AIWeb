"""
DeepResearch - 检索 Agent (Research)

根据大纲的 search_queries 执行网络与知识库检索，填充 facts 与 references。
"""
import asyncio
import uuid
from typing import Any, Dict, List

from .base import BaseAgent
from ..state import ResearchState, ResearchPhase

# 使用 Agentic 工具
from ...tools.web_search import web_search_structured
from ...tools.knowledge_search import knowledge_search_structured


class Research(BaseAgent):
    """Research - 证据收集。"""

    MAX_CONCURRENT = 3

    def __init__(self, model_id: str = "default"):
        super().__init__(name="Research", role="research", model_id=model_id)

    async def process(self, state: ResearchState) -> ResearchState:
        if state.get("phase") not in (ResearchPhase.PLANNING.value, ResearchPhase.RE_RESEARCHING.value):
            return state

        outline = state.get("outline", [])
        search_web = state.get("search_web", True)
        search_local = state.get("search_local", False)
        user_id = state.get("_user_id")

        # 收集待搜索的 query（来自大纲或补充）
        pending = state.get("pending_search_queries", [])
        queries = []
        if pending:
            for q in pending:
                q_str = q if isinstance(q, str) else str(q)
                if q_str.strip():
                    queries.append((q_str.strip(), "supplement"))
        if not queries:
            for section in outline:
                for q in (section.get("search_queries") or [])[:2]:
                    if q and str(q).strip():
                        queries.append((str(q).strip(), section.get("id", "")))
            if not queries:
                queries = [(state.get("query", "")[:100], "sec_1")]

        # 去重
        seen = set()
        unique_queries: List[tuple] = []
        for q, sec_id in queries:
            if q not in seen:
                seen.add(q)
                unique_queries.append((q, sec_id))

        self.add_message(state, "research_step", {
            "step_type": "researching",
            "title": "检索",
            "subtitle": f"检索 {len(unique_queries)} 个查询",
            "status": "running",
            "stats": {},
        })
        self.add_message(state, "thought", {"agent": self.name, "content": "开始执行网络与知识库检索..."})

        sem = asyncio.Semaphore(self.MAX_CONCURRENT)
        facts = list(state.get("facts", []))
        references = list(state.get("references", []))
        processed_urls = {f.get("source_url") or f.get("url") for f in facts if f.get("source_url") or f.get("url")}

        async def search_one(q: str, section_id: str) -> List[tuple]:
            out: List[tuple] = []
            async with sem:
                if search_web:
                    items = await web_search_structured(q, top_k=5)
                    for it in items or []:
                        out.append((it, "web", section_id))
                if search_local and user_id is not None:
                    items = await knowledge_search_structured(q, user_id=user_id, top_k=5)
                    for it in items or []:
                        out.append((it, "local", section_id))
            return out

        tasks = [search_one(q, sec_id) for q, sec_id in unique_queries[:15]]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for r in results:
            if isinstance(r, Exception):
                self._logger.warning("Search task error: %s", r)
                continue
            for it, source, section_id in r:
                url = it.get("url", "") or it.get("link", "")
                summary = (it.get("summary") or it.get("snippet") or "").strip()
                if not summary:
                    continue
                if url and url in processed_urls:
                    continue
                if url:
                    processed_urls.add(url)
                fid = f"fact_{uuid.uuid4().hex[:8]}"
                fact = {
                    "id": fid,
                    "content": summary[:2000],
                    "source_url": url,
                    "source_name": it.get("name", it.get("title", "N/A")),
                    "related_sections": [section_id] if section_id else [],
                    "credibility_score": 0.8,
                }
                facts.append(fact)
                references.append({
                    "id": len(references) + 1,
                    "marker": fid,
                    "source": it.get("name", it.get("title", "N/A")),
                    "url": url,
                    "source_url": url,
                })
                self.add_message(state, "search_result", {"fact": fact})
                self.add_message(state, "phase_detail", {"content": f"已收录: {it.get('name', 'N/A')[:40]}..."})

        state["facts"] = facts
        state["references"] = references
        state["messages"] = [m for m in state.get("messages", []) if m.get("type") != "phase_detail"][-50:]
        state["pending_search_queries"] = []
        if state.get("phase") == ResearchPhase.RE_RESEARCHING.value:
            state["phase"] = ResearchPhase.WRITING.value
        else:
            state["phase"] = ResearchPhase.WRITING.value

        self.add_message(state, "research_step", {
            "step_type": "researching",
            "title": "检索",
            "subtitle": "检索完成",
            "status": "completed",
            "stats": {"facts": len(facts), "sources": len(references)},
        })
        return state
