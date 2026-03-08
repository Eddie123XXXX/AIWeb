"""DeepResearch 工具函数：事件序列化、相似度去重、UI/DB 字段归一化"""
import json
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger("agentic.deepresearch")

CONTENT_SIMILARITY_THRESHOLD = 0.8
PHASE_ORDER = ["planning", "researching", "writing", "reviewing"]


def serialize_event(event_data: Dict[str, Any]) -> str:
    """将事件序列化为 JSON 字符串，供 SSE 使用"""
    def _default(obj: Any) -> Any:
        if isinstance(obj, set):
            return list(obj)
        if isinstance(obj, Exception):
            return str(obj)
        raise TypeError(f"Object of type {type(obj)} is not JSON serializable")

    try:
        return json.dumps(event_data, default=_default, ensure_ascii=False)
    except Exception as e:
        logger.error("Failed to serialize event: %s", e)
        return json.dumps({"type": "error", "content": f"Serialization error: {e}"})


def compute_content_similarity(text1: str, text2: str) -> float:
    """简单 Jaccard 词集合相似度"""
    if not text1 or not text2:
        return 0.0
    w1 = set(text1.lower().split())
    w2 = set(text2.lower().split())
    if not w1 or not w2:
        return 0.0
    inter = len(w1 & w2)
    union = len(w1 | w2)
    return inter / union if union > 0 else 0.0


def is_content_duplicate(
    new_content: str,
    existing_contents: List[str],
    threshold: float = CONTENT_SIMILARITY_THRESHOLD,
) -> bool:
    """判断新内容是否与已有内容重复"""
    for existing in existing_contents:
        if compute_content_similarity(new_content, existing) >= threshold:
            return True
    return False


def build_research_steps(phase_name: str) -> List[Dict[str, str]]:
    """根据当前 phase 生成前端可恢复的步骤状态。"""
    if phase_name == "completed":
        return [{"type": phase, "status": "completed"} for phase in PHASE_ORDER]
    if phase_name == "waiting_approval":
        return [
            {"type": "planning", "status": "completed"},
            {"type": "researching", "status": "pending"},
            {"type": "writing", "status": "pending"},
            {"type": "reviewing", "status": "pending"},
        ]
    if phase_name in PHASE_ORDER:
        idx = PHASE_ORDER.index(phase_name)
        steps = [{"type": phase, "status": "completed"} for phase in PHASE_ORDER[:idx]]
        steps.append({"type": phase_name, "status": "running"})
        return steps

    steps = [{"type": phase, "status": "completed"} for phase in PHASE_ORDER]
    if phase_name:
        steps.append({"type": phase_name, "status": "running"})
    return steps


def normalize_outline_item(item: Dict[str, Any]) -> Dict[str, str]:
    """统一大纲项结构，保证前端恢复稳定。"""
    return {
        "id": str(item.get("id") or ""),
        "title": str(item.get("title") or ""),
        "description": str(item.get("description") or ""),
    }


def normalize_outline_for_ui(outline: Optional[List[Dict[str, Any]]]) -> List[Dict[str, str]]:
    """将完整大纲压缩为前端展示/恢复使用的结构。"""
    return [
        normalize_outline_item(item)
        for item in (outline or [])
        if isinstance(item, dict)
    ]


def ensure_full_outline_item(
    item: Dict[str, Any],
    index: int,
    query: str = "",
) -> Dict[str, Any]:
    """确保章节保留执行期所需字段，供 research 阶段继续使用。"""
    title = str(item.get("title") or f"章节{index + 1}").strip() or f"章节{index + 1}"
    description = str(item.get("description") or "").strip()
    queries = item.get("search_queries")
    if not isinstance(queries, list):
        queries = [queries] if queries else []
    normalized_queries = [str(q).strip() for q in queries if str(q).strip()]
    if not normalized_queries:
        combined = " ".join(part for part in [title, description, query] if part).strip()
        normalized_queries = [combined or title]
    return {
        "id": str(item.get("id") or f"sec_{index + 1}"),
        "title": title,
        "description": description,
        "section_type": str(item.get("section_type") or "mixed"),
        "requires_data": bool(item.get("requires_data", False)),
        "requires_chart": bool(item.get("requires_chart", False)),
        "priority": int(item.get("priority") or index + 1),
        "search_queries": normalized_queries,
        "status": str(item.get("status") or "pending"),
    }


def normalize_editable_outline(
    outline: Optional[List[Dict[str, Any]]],
    query: str = "",
) -> List[Dict[str, Any]]:
    """统一用户可编辑的大纲结构，同时保留后续 research 所需字段。"""
    normalized: List[Dict[str, Any]] = []
    for index, item in enumerate(outline or []):
        if not isinstance(item, dict):
            continue
        normalized.append(ensure_full_outline_item(item, index, query=query))
    return normalized


def normalize_reference(
    raw: Optional[Dict[str, Any]] = None,
    *,
    fact: Optional[Dict[str, Any]] = None,
    fallback_id: Optional[int] = None,
) -> Optional[Dict[str, Any]]:
    """统一引用/来源对象结构为 id/title/link/content/source。"""
    source = raw if isinstance(raw, dict) else {}
    if fact is not None:
        source = fact

    title = (
        source.get("title")
        or source.get("source")
        or source.get("source_name")
        or source.get("name")
        or source.get("url")
        or source.get("source_url")
        or "N/A"
    )
    link = source.get("link") or source.get("url") or source.get("source_url") or ""
    content = source.get("content") or source.get("snippet") or source.get("summary") or ""
    canonical_source = (
        source.get("source")
        or source.get("source_name")
        or source.get("source_type")
        or source.get("title")
        or title
    )
    ref_id = source.get("id")
    if ref_id is None and fallback_id is not None:
        ref_id = fallback_id

    normalized = {
        "id": ref_id,
        "title": str(title or "N/A"),
        "link": str(link or ""),
        "content": str(content or "")[:500],
        "source": str(canonical_source or "N/A"),
    }
    if not any([normalized["title"], normalized["link"], normalized["content"]]):
        return None
    return normalized


def merge_unique_references(
    existing: Optional[List[Dict[str, Any]]],
    incoming: Optional[List[Dict[str, Any]]],
) -> List[Dict[str, Any]]:
    """按链接+标题去重合并来源列表，并重排 id。"""
    merged: List[Dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()

    for item in (existing or []) + (incoming or []):
        normalized = normalize_reference(item)
        if normalized is None:
            continue
        key = (
            (normalized.get("link") or "").strip().lower(),
            (normalized.get("title") or "").strip().lower(),
        )
        if key in seen:
            continue
        seen.add(key)
        merged.append(normalized)

    for idx, item in enumerate(merged, start=1):
        item["id"] = idx
    return merged


def append_section_markdown(
    existing_report: str,
    section_title: str,
    section_content: str,
) -> str:
    """把章节正文拼成可恢复的流式 Markdown。"""
    if not section_content:
        return existing_report or ""

    title = (section_title or "").strip()
    section_markdown = f"## {title}\n\n{section_content}" if title else section_content
    if not existing_report:
        return section_markdown
    if section_markdown in existing_report:
        return existing_report
    return f"{existing_report}\n\n{section_markdown}"
