"""
MCP Manager — 在 FastAPI 启动时自动发现所有已配置的 MCP Server 工具，
并将它们包装成 RemoteMCPTool 注册到 ToolRegistry。

调用方式（在 main.py lifespan 中）：
    from agentic.mcp_manager import discover_and_register_mcp_tools
    await discover_and_register_mcp_tools()
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict

from .config import MCPServerConfig, get_settings
from .mcp_client import MCPClient, MCPToolInfo
from .tools_base import ToolContext, ToolExecutionError

logger = logging.getLogger("agentic.mcp")

_mcp_client = MCPClient()


class RemoteMCPTool:
    """
    把 MCP Server 上的单个工具包装为 ToolRegistry 兼容的 Tool 对象。
    param_model=None 时 build_tools_schema 会用 input_schema 直接构造 JSON Schema。
    """

    def __init__(
        self,
        name: str,
        description: str,
        server: MCPServerConfig,
        remote_tool_name: str,
        input_schema: Dict[str, Any],
    ) -> None:
        self.name = name
        self.description = description
        self._server = server
        self._remote_tool_name = remote_tool_name
        self._input_schema = input_schema
        self.param_model = None
        self.required_permissions: set[str] = {"mcp:invoke"}

    def get_json_schema(self) -> Dict[str, Any]:
        """供 build_tools_schema 调用，返回 OpenAI-compatible JSON Schema。"""
        schema = dict(self._input_schema)
        schema.setdefault("type", "object")
        schema.setdefault("properties", {})
        return schema

    async def run(self, params: Dict[str, Any], ctx: ToolContext) -> str:
        try:
            result = await _mcp_client.call_tool(
                self._server,
                self._remote_tool_name,
                params,
            )
            return result
        except Exception as exc:  # noqa: BLE001
            raise ToolExecutionError(
                f"MCP 工具调用失败 [{self._server.name}/{self._remote_tool_name}]: {exc}"
            ) from exc


async def _discover_server(server: MCPServerConfig) -> list[RemoteMCPTool]:
    """发现单个 MCP Server 的全部工具，返回包装后的 RemoteMCPTool 列表。"""
    if not server.enabled:
        logger.info("[MCP] %s 已禁用，跳过发现", server.name)
        return []

    tools: list[MCPToolInfo] = await _mcp_client.list_tools(server)
    wrapped: list[RemoteMCPTool] = []
    for t in tools:
        tool_name = f"{server.tool_prefix}{t.name}" if server.tool_prefix else t.name
        wrapped.append(
            RemoteMCPTool(
                name=tool_name,
                description=t.description or f"MCP 工具：{t.name}（来源：{server.name}）",
                server=server,
                remote_tool_name=t.name,
                input_schema=t.input_schema,
            )
        )
    return wrapped


async def discover_and_register_mcp_tools() -> None:
    """
    并发发现所有已启用的 MCP Server 工具，注册到 ToolRegistry。
    已存在同名工具时跳过（不覆盖内置工具）。
    在 FastAPI lifespan 启动阶段调用一次即可。
    """
    from .tools_registry import registry

    settings = get_settings()
    servers = [s for s in settings.mcp_servers if s.enabled]
    if not servers:
        logger.info("[MCP] 未配置任何 MCP Server，跳过发现")
        return

    logger.info("[MCP] 开始发现 %d 个 MCP Server 的工具...", len(servers))
    tasks = [_discover_server(s) for s in servers]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    registered_count = 0
    for server, result in zip(servers, results):
        if isinstance(result, Exception):
            logger.error("[MCP] %s 工具发现失败: %s", server.name, result)
            continue
        for tool in result:
            try:
                registry.register(tool)
                registered_count += 1
                logger.info("[MCP] 已注册工具: %s (来自 %s)", tool.name, server.name)
            except ValueError:
                logger.warning("[MCP] 工具 %s 已存在，跳过注册", tool.name)

    logger.info("[MCP] MCP 工具发现完成，共注册 %d 个工具", registered_count)


def get_registered_mcp_tools() -> list[dict]:
    """返回当前已注册的 MCP 工具信息列表（供 API 接口使用）。"""
    from .tools_registry import registry

    return [
        {
            "name": tool.name,
            "description": getattr(tool, "description", ""),
            "server": tool._server.name,
            "remote_tool_name": tool._remote_tool_name,
        }
        for tool in registry.tools.values()
        if isinstance(tool, RemoteMCPTool)
    ]
