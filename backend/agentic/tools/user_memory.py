"""
用户记忆检索工具 (user_memory)。

从用户长期记忆中根据 query 检索相关信息，支持按 domain_label 领域过滤。
"""
from __future__ import annotations

from typing import Any, Dict

from pydantic import AliasChoices, BaseModel, Field

from memory.router import MEMORY_DOMAINS
from memory.service import list_memories_for_user, retrieve_relevant_memories

from ..tools_base import ToolContext, ToolExecutionError
from .common import ensure_permissions, validate_params


class UserMemoryParams(BaseModel):
    query: str
    # 统一参数：domain_label。兼容旧入参 domain（validation alias）。
    domain_label: str | None = Field(
        default=None,
        validation_alias=AliasChoices("domain_label", "domain"),
    )


class UserMemoryTool:
    """用户记忆检索工具：从长期记忆中检索与 query 相关的信息。"""

    name = "user_memory"
    description = "从用户长期记忆中根据 query 检索相关信息，可通过 domain_label按领域过滤。支持的 domain_label 枚举值：all（全部记忆）、general_chat（通用闲聊）、user_preferences（用户偏好）、professional_and_academic（职业与学术）、lifestyle_and_interests（生活与兴趣）、social_and_relationships（社交与关系）、tasks_and_schedules（任务与日程）。"
    required_permissions: set[str] = {"memory:read"}
    param_model = UserMemoryParams

    async def run(self, params: Dict[str, Any], ctx: ToolContext) -> str:
        parsed = validate_params(UserMemoryParams, params)
        ensure_permissions(ctx, self.required_permissions)

        query = parsed.query.strip()
        user_id = getattr(ctx, "user_id", None)
        if user_id is None:
            raise ToolExecutionError("当前会话缺少 user_id，无法检索个人长期记忆。")

        raw_domain = (parsed.domain_label or "all").strip().lower()
        if raw_domain in {"", "all"}:
            target_domains = None
            domain_hint = "all"
        elif raw_domain in MEMORY_DOMAINS:
            target_domains = [raw_domain]
            domain_hint = raw_domain
        else:
            allowed = ", ".join(["all", *MEMORY_DOMAINS])
            raise ToolExecutionError(f"domain_label 无效: {raw_domain}。允许值: {allowed}")

        memories = await retrieve_relevant_memories(
            user_id=int(user_id),
            query=query,
            conversation_id=None,
            target_domains=target_domains,
            top_k_final=5,
        )

        # 若按 query 检索为空，则退化为直接列出用户最近的记忆
        if not memories:
            recent = await list_memories_for_user(int(user_id), limit=5, offset=0)
            if target_domains:
                allowed_set = set(target_domains)
                recent = [m for m in recent if (m.get("domain") or "general_chat") in allowed_set]
            if not recent:
                if target_domains:
                    return f"当前长期记忆库中没有 domain={domain_hint} 的可用记忆记录。"
                return "当前长期记忆库中没有可用的记忆记录。"
            memories = recent

        lines: list[str] = []
        for idx, mem in enumerate(memories, start=1):
            content = (mem.get("content") or "").strip()
            domain_label = (mem.get("domain") or "general_chat").strip()
            if len(content) > 200:
                content = content[:200] + "..."
            lines.append(f"{idx}. [{domain_label}] {content}")

        header = (
            f"从用户长期记忆中检索到 {len(memories)} 条候选结果"
            f"（domain={domain_hint}，按相关性与重要性排序）："
        )
        return header + "\n" + "\n".join(lines)
