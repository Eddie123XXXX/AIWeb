"""
MCP Client — 使用 httpx 直接实现 MCP JSON-RPC 2.0 协议。

支持两种传输方式（无需安装 mcp SDK，与现有 pydantic 版本完全兼容）：
- SSE（Server-Sent Events）：GET /sse 建立长连接，POST /messages 发送调用
- Streamable HTTP：POST /mcp 单次请求/响应（高德推荐方式）

使用示例：
    client = MCPClient()
    tools = await client.list_tools(server_config)
    result = await client.call_tool(server_config, "maps_weather", {"city": "北京"})
"""
from __future__ import annotations

import json
import logging
import uuid
from typing import Any, Dict, List, Optional

import httpx

from .config import MCPServerConfig

logger = logging.getLogger("agentic.mcp")

_DEFAULT_TIMEOUT = 90.0


class MCPToolInfo:
    """轻量工具描述，用于注册到 ToolRegistry。"""

    def __init__(self, name: str, description: str, input_schema: Dict[str, Any]) -> None:
        self.name = name
        self.description = description
        self.input_schema = input_schema  # JSON Schema object

    def __repr__(self) -> str:
        return f"MCPToolInfo(name={self.name!r})"


def _build_headers(server: MCPServerConfig) -> Dict[str, str]:
    headers: Dict[str, str] = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
    }
    if server.api_key:
        headers["X-API-Key"] = server.api_key
    headers.update(server.headers)
    return headers


def _jsonrpc(method: str, params: Any = None, req_id: Optional[str] = None) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "jsonrpc": "2.0",
        "id": req_id or str(uuid.uuid4()),
        "method": method,
    }
    if params is not None:
        payload["params"] = params
    return payload


# ---------- Streamable HTTP（高德推荐）----------

async def _streamable_http_request(
    url: str,
    payload: Dict[str, Any],
    headers: Dict[str, str],
    timeout: float = _DEFAULT_TIMEOUT,
) -> Dict[str, Any]:
    """
    向 Streamable HTTP MCP Server 发起单次 JSON-RPC 请求，解析响应。
    响应可能是纯 JSON，也可能是包含 JSON 的 SSE 流（data: {...}\\n\\n）。
    使用流式读取，拿到第一个有效 JSON-RPC 结果就立即返回，避免 SSE 长连接超时。
    """
    async with httpx.AsyncClient(
        timeout=httpx.Timeout(timeout, connect=30.0),
        follow_redirects=True,
    ) as client:
        async with client.stream("POST", url, json=payload, headers=headers) as resp:
            if resp.status_code >= 400:
                body = (await resp.aread()).decode(errors="replace")[:500]
                raise RuntimeError(f"MCP HTTP {resp.status_code} from {url}: {body}")

            content_type = resp.headers.get("content-type", "")

            if "text/event-stream" in content_type:
                async for line in resp.aiter_lines():
                    line = line.strip()
                    if not line or line.startswith(":"):
                        continue
                    if line.startswith("data:"):
                        data_str = line[5:].strip()
                        if not data_str or data_str == "[DONE]":
                            continue
                        try:
                            obj = json.loads(data_str)
                            if isinstance(obj, dict) and ("result" in obj or "error" in obj):
                                return obj
                        except json.JSONDecodeError:
                            continue
                return {}
            else:
                body = (await resp.aread()).decode(errors="replace").strip()
                if not body:
                    return {}
                try:
                    return json.loads(body)
                except Exception:
                    raise RuntimeError(
                        f"MCP 非 JSON 响应 ({content_type}): {body[:300]}"
                    )


async def _list_tools_streamable_http(server: MCPServerConfig) -> List[MCPToolInfo]:
    headers = _build_headers(server)

    # 1. initialize
    init_payload = _jsonrpc(
        "initialize",
        params={
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "AIWeb", "version": "1.0"},
        },
    )
    try:
        await _streamable_http_request(server.url, init_payload, headers)
    except Exception as exc:
        logger.debug("[MCP] %s initialize 失败（忽略，继续 list_tools）: %s", server.name, exc)

    # 2. tools/list
    list_payload = _jsonrpc("tools/list")
    resp = await _streamable_http_request(server.url, list_payload, headers)
    return _parse_tools_response(resp)


async def _call_tool_streamable_http(
    server: MCPServerConfig,
    tool_name: str,
    arguments: Dict[str, Any],
) -> Any:
    headers = _build_headers(server)
    payload = _jsonrpc("tools/call", params={"name": tool_name, "arguments": arguments})
    resp = await _streamable_http_request(server.url, payload, headers)
    return _parse_call_response(resp)


# ---------- SSE ----------

async def _list_tools_sse(server: MCPServerConfig) -> List[MCPToolInfo]:
    """
    SSE 传输：先 GET /sse 建立连接（拿到 session endpoint），
    再 POST 到 session endpoint 发 JSON-RPC。
    一些简单的 SSE Server 也接受直接 POST 到 /sse（如 modelscope 托管版）。
    """
    headers = _build_headers(server)
    session_url: Optional[str] = None

    # 尝试通过 GET SSE 拿 session URL（标准 MCP-over-SSE 握手）
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            async with client.stream("GET", server.url, headers=headers) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    line = line.strip()
                    if line.startswith("data:"):
                        data_str = line[5:].strip()
                        try:
                            event_data = json.loads(data_str)
                            # 标准握手：endpoint 事件包含 session POST URL
                            if isinstance(event_data, dict) and "endpoint" in event_data:
                                session_url = str(event_data["endpoint"])
                                break
                        except json.JSONDecodeError:
                            # 兼容 "data: /messages?session=..." 非 JSON 格式
                            if data_str.startswith("/") or data_str.startswith("http"):
                                session_url = data_str
                                break
                    # 拿到 session URL 就退出
                    if session_url:
                        break
    except Exception as exc:
        logger.debug("[MCP] %s SSE 握手失败，降级到直接 POST: %s", server.name, exc)

    # 确定实际 POST 地址
    if session_url:
        if session_url.startswith("/"):
            # 相对路径：拼接 server.url 的 origin
            from urllib.parse import urlparse, urlunparse
            parsed = urlparse(server.url)
            base = urlunparse((parsed.scheme, parsed.netloc, "", "", "", ""))
            post_url = base + session_url
        else:
            post_url = session_url
    else:
        # 降级：直接向 server.url（/sse）POST，部分托管服务支持
        post_url = server.url

    # initialize
    init_payload = _jsonrpc(
        "initialize",
        params={
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "AIWeb", "version": "1.0"},
        },
    )
    try:
        await _streamable_http_request(post_url, init_payload, headers)
    except Exception as exc:
        logger.debug("[MCP] %s SSE initialize 失败（忽略）: %s", server.name, exc)

    # tools/list
    list_payload = _jsonrpc("tools/list")
    resp = await _streamable_http_request(post_url, list_payload, headers)
    return _parse_tools_response(resp)


async def _call_tool_sse(
    server: MCPServerConfig,
    tool_name: str,
    arguments: Dict[str, Any],
) -> Any:
    headers = _build_headers(server)
    payload = _jsonrpc("tools/call", params={"name": tool_name, "arguments": arguments})
    resp = await _streamable_http_request(server.url, payload, headers)
    return _parse_call_response(resp)


# ---------- 解析辅助 ----------

def _parse_tools_response(resp: Dict[str, Any]) -> List[MCPToolInfo]:
    result = resp.get("result") or {}
    tools_raw = result.get("tools") or []
    tools: List[MCPToolInfo] = []
    for t in tools_raw:
        if not isinstance(t, dict):
            continue
        name = str(t.get("name") or "").strip()
        if not name:
            continue
        description = str(t.get("description") or "").strip()
        input_schema = t.get("inputSchema") or {"type": "object", "properties": {}}
        tools.append(MCPToolInfo(name=name, description=description, input_schema=input_schema))
    return tools


def _parse_call_response(resp: Dict[str, Any]) -> Any:
    if "error" in resp:
        err = resp["error"]
        raise RuntimeError(f"MCP 工具调用返回错误: {err}")
    result = resp.get("result") or {}
    content = result.get("content") or []
    # 把所有 text 类型内容合并成字符串返回
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict):
                if item.get("type") == "text":
                    parts.append(str(item.get("text") or ""))
                else:
                    parts.append(json.dumps(item, ensure_ascii=False))
            else:
                parts.append(str(item))
        return "\n".join(parts) if parts else json.dumps(result, ensure_ascii=False)
    return json.dumps(result, ensure_ascii=False)


# ---------- 公共接口 ----------

class MCPClient:
    """
    轻量 MCP 客户端，用 httpx 直接实现 MCP JSON-RPC 2.0 协议。
    支持 SSE 和 Streamable HTTP 两种传输方式，零额外依赖。
    """

    async def list_tools(self, server: MCPServerConfig) -> List[MCPToolInfo]:
        """发现指定 MCP Server 上的所有工具。"""
        try:
            if server.transport == "streamable_http":
                tools = await _list_tools_streamable_http(server)
            else:
                tools = await _list_tools_sse(server)
            logger.info("[MCP] %s 发现 %d 个工具: %s", server.name, len(tools), [t.name for t in tools])
            return tools
        except Exception as exc:
            logger.error(
                "[MCP] %s list_tools 失败 (%s): %s",
                server.name,
                type(exc).__name__,
                exc or repr(exc),
                exc_info=True,
            )
            return []

    async def call_tool(
        self,
        server: MCPServerConfig,
        tool_name: str,
        arguments: Dict[str, Any],
    ) -> str:
        """调用指定工具，返回文本结果（供 Observation 使用）。"""
        logger.info("[MCP] 调用工具 %s/%s, args=%s", server.name, tool_name, arguments)
        if server.transport == "streamable_http":
            result = await _call_tool_streamable_http(server, tool_name, arguments)
        else:
            result = await _call_tool_sse(server, tool_name, arguments)
        return str(result)

    async def invoke(
        self,
        *,
        server_name: str,
        tool_name: str,
        arguments: Dict[str, Any],
    ) -> Dict[str, Any]:
        """向后兼容旧接口（MCPTool 使用）。需从 settings 找到对应 server。"""
        from .config import get_settings
        settings = get_settings()
        server = self._find_server(settings, server_name)
        result = await self.call_tool(server, tool_name, arguments)
        return {"server": server_name, "tool": tool_name, "result": result}

    def _find_server(self, settings: Any, server_name: str) -> MCPServerConfig:
        for s in settings.mcp_servers:
            if s.name == server_name:
                return s
        raise ValueError(f"未找到名为 {server_name!r} 的 MCP Server 配置，请检查 MCP_SERVERS_JSON。")
