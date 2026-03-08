"""
DeepResearch 状态定义（多阶段工作流）

由 graph._run_simplified 状态机驱动。仅保留实际使用的状态字段。
"""
from enum import Enum
from typing import Any, Dict


class ResearchPhase(str, Enum):
    """研究阶段枚举"""
    INIT = "init"
    PLANNING = "planning"
    WAITING_APPROVAL = "waiting_approval"
    RESEARCHING = "researching"
    ANALYZING = "analyzing"
    WRITING = "writing"
    REVIEWING = "reviewing"
    REVISING = "revising"
    RE_RESEARCHING = "re_researching"
    COMPLETED = "completed"


ResearchState = Dict[str, Any]


def create_initial_state(
    query: str,
    session_id: str,
    search_web: bool = True,
    search_local: bool = False,
) -> ResearchState:
    """创建初始研究状态"""
    return {
        "query": query,
        "session_id": session_id,
        "phase": ResearchPhase.INIT.value,
        "iteration": 0,
        "max_iterations": 3,
        "search_web": search_web,
        "search_local": search_local,
        "outline": [],
        "research_questions": [],
        "facts": [],
        "data_points": [],
        "charts": [],
        "draft_sections": {},
        "final_report": "",
        "references": [],
        "insights": [],
        "quality_score": 0.0,
        "reviewer_feedback": [],
        "unresolved_issues": 0,
        "pending_search_queries": [],
        "messages": [],
    }
