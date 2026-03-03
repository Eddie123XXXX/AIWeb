from __future__ import annotations

from typing import Any, Dict

from pydantic import BaseModel

from rag.models import SearchRequest
from rag.notebook_repository import notebook_repository
from rag.service import search as rag_search

from ..tools_base import ToolContext, ToolExecutionError
from .common import ensure_permissions, validate_params


class QueryRAGKnowledgeParams(BaseModel):
    # notebook_id 字段保留以兼容旧 Prompt，但当前实现会忽略该字段，统一检索当前用户下的所有笔记本
    notebook_id: str | None = None
    query: str


class QueryRAGKnowledgeTool:
    name = "query_rag_knowledge"
    description = "从当前用户知识库中根据 query 检索相关信息。"
    required_permissions: set[str] = {"rag:search"}
    param_model = QueryRAGKnowledgeParams

    async def run(self, params: Dict[str, Any], ctx: ToolContext) -> str:
        parsed = validate_params(QueryRAGKnowledgeParams, params)
        ensure_permissions(ctx, self.required_permissions)

        query = parsed.query.strip()

        user_id = getattr(ctx, "user_id", None)
        if user_id is None:
            raise ToolExecutionError("当前会话缺少 user_id，无法确定需要检索哪些知识库。")

        notebooks: list[dict[str, Any]] = []
        page_size = 100
        offset = 0
        while True:
            page = await notebook_repository.list_by_user(int(user_id), limit=page_size, offset=offset)
            if not page:
                break
            notebooks.extend(page)
            if len(page) < page_size:
                break
            offset += page_size

        if not notebooks:
            return "当前用户尚未创建任何知识库笔记本，因此无法从 RAG 中检索到相关内容。"

        all_hits: list[dict[str, Any]] = []
        for nb in notebooks:
            nb_id = str(nb.get("id"))
            try:
                request = SearchRequest(
                    notebook_id=nb_id,
                    query=query,
                )
            except Exception:
                continue

            try:
                result = await rag_search(request)
            except Exception:
                continue

            for hit in list(result.hits or []):
                all_hits.append({"notebook_id": nb_id, "hit": hit})

        if not all_hits:
            return "知识库中未检索到与该问题明显相关的内容。"

        # 对齐 RAG 展示评分语义：优先 rerank_score，否则 score；仅做跨笔记本合并排序
        def _global_score(item: dict[str, Any]) -> float:
            hit = item["hit"]
            rerank_score = getattr(hit, "rerank_score", None)
            if rerank_score is not None:
                return float(rerank_score)
            return float(getattr(hit, "score", 0.0) or 0.0)

        all_hits.sort(key=_global_score, reverse=True)
        top_k = min(len(all_hits), 5)
        lines: list[str] = []
        for idx, item in enumerate(all_hits[:top_k], start=1):
            hit = item["hit"]
            text = (hit.parent_content or hit.content or "").strip()
            if len(text) > 200:
                text = text[:200] + "..."
            lines.append(f"{idx}. [笔记本 {item['notebook_id']} | 文档 {hit.document_id}] {text}")

        header = f"从当前用户的所有知识库中检索到 {len(all_hits)} 条候选结果，前 {top_k} 条摘要如下："
        return header + "\n" + "\n".join(lines)

