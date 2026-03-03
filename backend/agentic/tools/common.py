from __future__ import annotations

from typing import Any, Dict

from pydantic import BaseModel, ValidationError

from ..tools_base import ToolContext, ToolExecutionError


def validate_params(model: type[BaseModel], params: Dict[str, Any]) -> BaseModel:
    try:
        return model.model_validate(params)
    except ValidationError as exc:
        raise ToolExecutionError(f"工具参数校验失败: {exc}") from exc


def ensure_permissions(ctx: ToolContext, required: set[str]) -> None:
    """
    权限检查（当前禁用，统一放行）。
    """
    return

