from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Awaitable, Callable, Dict, List, Optional, Set

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from .tools_base import ToolContext
    from .tools_registry import ToolRegistry


class AgentState(BaseModel):
    """
    贯穿整个 Agent 对话生命周期的全局状态。

    状态机中每个节点接收 AgentState、修改后返回，驱动图引擎流转。
    """

    messages: List[Dict[str, Any]] = Field(default_factory=list)
    current_agent: str = Field(
        default="supervisor",
        description="当前接管的 Agent 名称，用于路由到对应的工具集",
    )
    steps: int = 0
    max_steps: int = 15
    max_total_seconds: int = 600
    start_time: float = Field(default_factory=time.monotonic)

    errors: List[str] = Field(
        default_factory=list,
        description="收集运行时错误，用于最终降级回答或调试",
    )
    next_node: Optional[str] = Field(
        default="call_llm",
        description="状态路由指针，指向下一个要执行的节点名称",
    )
    final_answer: Optional[str] = None

    model_id: str = "default"
    user_id: Optional[int] = None
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    enabled_tool_names: Optional[Set[str]] = None
    tools_schema: List[Dict[str, Any]] = Field(default_factory=list)

    model_config = {"arbitrary_types_allowed": True, "protected_namespaces": ()}


ThoughtCallback = Callable[[str, int], Awaitable[None]]
ActionCallback = Callable[[str, Dict[str, Any], int], Awaitable[None]]
ObservationCallback = Callable[[str, int], Awaitable[None]]
ObservationDeltaCallback = Callable[[str, int], Awaitable[None]]
FinalAnswerCallback = Callable[[str], Awaitable[None]]
StreamDeltaCallback = Callable[[str], Awaitable[None]]


@dataclass
class AgentCallbacks:
    """将所有回调函数打包在一起，简化节点函数签名。"""

    on_thought: Optional[ThoughtCallback] = None
    on_action: Optional[ActionCallback] = None
    on_observation: Optional[ObservationCallback] = None
    on_observation_delta: Optional[ObservationDeltaCallback] = None
    on_final_answer: Optional[FinalAnswerCallback] = None
    on_stream_delta: Optional[StreamDeltaCallback] = None


@dataclass
class AgentDeps:
    """
    节点运行所需的外部依赖容器。

    将 registry / tool context / callbacks 集中在一处，
    节点函数签名统一为 (state, deps) -> state。
    """

    registry: ToolRegistry
    tool_ctx: ToolContext
    callbacks: AgentCallbacks = field(default_factory=AgentCallbacks)
    tool_timeout_seconds: int = 100
