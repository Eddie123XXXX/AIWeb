from __future__ import annotations

from typing import Any, Dict

from ..mcp_client import MCPClient
from ..tools_base import ToolContext, ToolExecutionError
from .common import ensure_permissions


class MCPTool:
    """
    MCP 工具包装器：通过 MCPClient 调用远端 MCP Server 上暴露的工具。
    """

    def __init__(self, name: str, description: str, server_name: str, tool_name: str) -> None:
        self.name = name
        self.description = description
        self._server_name = server_name
        self._tool_name = tool_name
        self._client = MCPClient()
        self.required_permissions: set[str] = {"mcp:invoke"}

    async def run(self, params: Dict[str, Any], ctx: ToolContext) -> str:
        ensure_permissions(ctx, self.required_permissions)
        try:
            result = await self._client.invoke(
                server_name=self._server_name,
                tool_name=self._tool_name,
                arguments=params,
            )
            return f"MCP 工具调用结果：{result}"
        except Exception as exc:  # noqa: BLE001
            raise ToolExecutionError(
                f"MCP 工具调用失败：server={self._server_name}, tool={self._tool_name}, 错误={exc}",
            ) from exc

