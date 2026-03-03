from __future__ import annotations

from typing import Any, Awaitable, Callable, Dict, Optional

from ..tools_base import ToolContext, ToolExecutionError
from .common import ensure_permissions


HandlerFunc = Callable[..., Awaitable[str]]


class SkillTool:
    """
    将系统中配置的技能封装成 Tool。

    - 既支持通过 AgenticSettings.skills 静态注册（仅 name/description）
    - 也支持通过 SKILLS/*.md + *.py 动态注册（带参数 schema 和 handler_func）
    """

    def __init__(
        self,
        name: str,
        description: str,
        parameters_schema: Optional[Dict[str, Any]] = None,
        handler_func: Optional[HandlerFunc] = None,
    ) -> None:
        self.name = name
        self.description = description
        self._parameters_schema: Dict[str, Any] = parameters_schema or {
            "type": "object",
            "properties": {},
            "additionalProperties": True,
        }
        self._handler_func: Optional[HandlerFunc] = handler_func
        self.required_permissions: set[str] = set()

    def get_json_schema(self) -> Dict[str, Any]:
        """
        提供给 build_tools_schema 使用的参数 JSON Schema。
        静态 SkillConfig 无 schema 时，回退为空 object。
        """
        return self._parameters_schema

    async def run(self, params: Dict[str, Any], ctx: ToolContext) -> str:
        ensure_permissions(ctx, getattr(self, "required_permissions", set()))
        if self._handler_func is None:
            # 兼容旧行为：尚未对接具体执行逻辑时给出明确错误提示
            raise ToolExecutionError(
                f"SkillTool {self.name} 尚未实现，请在 SKILLS/ 中为其提供执行逻辑或在 SkillTool 中接入实现。",
            )
        try:
            result = await self._handler_func(**params)
            return str(result)
        except Exception as exc:  # noqa: BLE001
            raise ToolExecutionError(f"SkillTool {self.name} 执行失败: {exc}") from exc

