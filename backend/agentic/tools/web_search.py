from __future__ import annotations

import os
from typing import Any, Dict, List

import httpx
from pydantic import BaseModel, Field

from ..tools_base import ToolContext, ToolExecutionError
from .common import ensure_permissions, validate_params


class WebSearchParams(BaseModel):
    query: str
    top_k: int = Field(default=5, ge=1, le=10)
    gl: str = Field(default="cn", min_length=2, max_length=8)
    hl: str = Field(default="zh-cn", min_length=2, max_length=16)
    autocorrect: bool = True
    page: int = Field(default=1, ge=1, le=20)
    search_type: str = Field(default="search")


class WebSearchTool:
    name = "web_search"
    description = "从互联网公开信息中根据 query 检索相关信息。"
    required_permissions: set[str] = set()
    param_model = WebSearchParams

    def _extract_serper_results(self, search_results: Dict[str, Any], top_k: int) -> List[Dict[str, Any]]:
        """
        对齐 WebSearchService.extract_search_results 结构。
        """
        results: List[Dict[str, Any]] = []
        if "knowledgeGraph" in search_results:
            kg = search_results["knowledgeGraph"] or {}
            results.append(
                {
                    "type": "knowledgeGraph",
                    "title": kg.get("title", ""),
                    "description": kg.get("description", ""),
                    "source": kg.get("descriptionSource", ""),
                    "link": kg.get("descriptionLink", ""),
                    "attributes": kg.get("attributes", {}) or {},
                }
            )

        for item in (search_results.get("organic") or [])[:top_k]:
            results.append(
                {
                    "type": "organic",
                    "title": item.get("title", ""),
                    "link": item.get("link", ""),
                    "snippet": item.get("snippet", ""),
                    "position": item.get("position", 0),
                }
            )

        for item in (search_results.get("peopleAlsoAsk") or []):
            results.append(
                {
                    "type": "peopleAlsoAsk",
                    "question": item.get("question", ""),
                    "snippet": item.get("snippet", ""),
                    "title": item.get("title", ""),
                    "link": item.get("link", ""),
                }
            )

        related = [
            item.get("query", "")
            for item in (search_results.get("relatedSearches") or [])
            if isinstance(item, dict) and item.get("query")
        ]
        if related:
            results.append({"type": "relatedSearches", "queries": related})
        return results

    async def _search_with_serper(self, parsed: WebSearchParams) -> list[dict[str, Any]]:
        api_key = (os.getenv("SERPER_API_KEY") or "").strip()
        if not api_key:
            return []
        url = os.getenv("SERPER_SEARCH_URL", "https://google.serper.dev/search")
        payload = {
            "q": parsed.query,
            "gl": parsed.gl,
            "hl": parsed.hl,
            "autocorrect": parsed.autocorrect,
            "page": parsed.page,
            "type": parsed.search_type,
            "num": parsed.top_k,
        }
        headers = {"X-API-KEY": api_key, "Content-Type": "application/json"}
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()
        return self._extract_serper_results(data, parsed.top_k)

    async def _search_with_bocha(self, parsed: WebSearchParams) -> list[dict[str, Any]]:
        api_key = (os.getenv("BOCHA_API_KEY") or "").strip()
        if not api_key:
            return []

        url = os.getenv("BOCHA_APISEARCH_URL", "https://api.bochaai.com/v1/web-search")
        payload = {"query": parsed.query, "count": parsed.top_k, "page": parsed.page}
        headers = {
            "Authorization": f"Bearer {api_key}",
            "X-API-KEY": api_key,
            "Content-Type": "application/json",
        }
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()

        candidates = (
            data.get("items")
            or data.get("data")
            or ((data.get("webPages") or {}).get("value") if isinstance(data.get("webPages"), dict) else [])
            or []
        )
        items: list[dict[str, Any]] = []
        for it in candidates[: parsed.top_k]:
            if not isinstance(it, dict):
                continue
            title = str(it.get("title") or it.get("name") or "").strip()
            link = str(it.get("url") or it.get("link") or "").strip()
            snippet = str(it.get("snippet") or it.get("summary") or it.get("description") or "").strip()
            if not (title or link or snippet):
                continue
            items.append(
                {
                    "type": "organic",
                    "title": title,
                    "link": link,
                    "snippet": snippet,
                    "position": int(it.get("position") or 0),
                }
            )
        return items

    async def run(self, params: Dict[str, Any], ctx: ToolContext) -> str:
        parsed = validate_params(WebSearchParams, params)
        ensure_permissions(ctx, self.required_permissions)

        query = parsed.query.strip()
        if not query:
            raise ToolExecutionError("query 不能为空")

        has_serper = bool((os.getenv("SERPER_API_KEY") or "").strip())
        has_bocha = bool((os.getenv("BOCHA_API_KEY") or "").strip())
        if not has_serper and not has_bocha:
            raise ToolExecutionError("未配置 SERPER_API_KEY 或 BOCHA_API_KEY，无法执行联网搜索。")

        provider = "serper" if has_serper else "bocha"
        try:
            if provider == "serper":
                items = await self._search_with_serper(parsed)
            else:
                items = await self._search_with_bocha(parsed)
        except Exception as exc:  # noqa: BLE001
            raise ToolExecutionError(f"web_search 调用失败(provider={provider}): {exc}") from exc

        if not items:
            return f"联网搜索未返回有效结果（provider={provider}）。"

        lines: list[str] = []
        idx = 1
        for it in items:
            typ = (it.get("type") or "").strip()
            if typ == "knowledgeGraph":
                title = str(it.get("title") or "Knowledge Graph").strip()
                desc = str(it.get("description") or "").strip()
                source = str(it.get("source") or "").strip()
                link = str(it.get("link") or "").strip()
                attrs = it.get("attributes") or {}
                attr_text = ""
                if isinstance(attrs, dict) and attrs:
                    attr_pairs = [f"{k}:{v}" for k, v in list(attrs.items())[:5]]
                    attr_text = "；属性=" + "，".join(attr_pairs)
                lines.append(f"{idx}. [知识图谱] {title}\nURL: {link}\n摘要: {desc}\n来源: {source}{attr_text}")
                idx += 1
                continue

            if typ == "peopleAlsoAsk":
                q = str(it.get("question") or "").strip()
                title = str(it.get("title") or "").strip()
                link = str(it.get("link") or "").strip()
                snippet = str(it.get("snippet") or "").strip()
                if len(snippet) > 200:
                    snippet = snippet[:200] + "..."
                lines.append(f"{idx}. [相关问题] {q or title}\nURL: {link}\n摘要: {snippet}")
                idx += 1
                continue

            if typ == "relatedSearches":
                queries = it.get("queries") or []
                if isinstance(queries, list) and queries:
                    lines.append(f"{idx}. [相关搜索] " + "；".join(str(x) for x in queries[:8]))
                    idx += 1
                continue

            title = str(it.get("title") or "无标题").strip()
            url = str(it.get("link") or it.get("url") or "").strip()
            snippet = str(it.get("snippet") or "").strip()
            if len(snippet) > 200:
                snippet = snippet[:200] + "..."
            lines.append(f"{idx}. {title}\nURL: {url}\n摘要: {snippet}")
            idx += 1
        return f"联网搜索结果（provider={provider}，query={query}）：\n" + "\n\n".join(lines)

