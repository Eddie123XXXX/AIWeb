from __future__ import annotations

from functools import lru_cache
from typing import Dict, Literal, Optional

from pydantic import BaseModel
from pydantic import Field


class LLMConfig(BaseModel):
    provider: str = Field(
        default="openai",
        description="LLM 提供方标识，自行在 llm_client 中适配（如 openai / deepseek / qwen 等）",
    )
    model: str = Field(
        default="gpt-4.1-mini",
        description="默认使用的模型名称，可在 .env 或启动参数中覆盖",
    )
    max_steps: int = Field(
        default=10,
        description="Agent Loop 的最大思考 / 工具调用步数（防死循环护栏）",
        ge=1,
        le=30,
    )
    enable_stream_thought: bool = Field(
        default=True,
        description="是否通过 WebSocket 将 Thought 逐 token 流式透传给前端（stream_delta）",
    )
    max_total_seconds: int = Field(
        default=600,
        description="单次 Agentic 会话的最大总耗时（秒），防止长时间占用资源",
        ge=5,
        le=300,
    )
    tool_timeout_seconds: int = Field(
        default=100,
        description="单个工具调用的最大执行时间（秒），超时将视为失败并返回错误 Observation",
        ge=1,
        le=120,
    )


class MCPServerConfig(BaseModel):
    """
    外部 MCP Server 配置。

    - name:       逻辑名，用于日志与工具名前缀（如 "amap"）
    - url:        MCP Server 完整地址（含 API Key 参数或放在 headers 里均可）
                  SSE 示例：  https://mcp.amap.com/sse?key=xxx
                  HTTP 示例：https://mcp.amap.com/mcp?key=xxx
    - transport:  "sse" 或 "streamable_http"（默认 sse）
    - api_key:    若服务要求在 header 传 key，填在这里（X-API-Key）；
                  若 key 已包含在 url 里可留空
    - enabled:    false 时跳过该 server，不注册其工具
    - headers:    额外 HTTP 请求头（键值对）
    - tool_prefix: 注册到 registry 时的工具名前缀（防止不同 server 工具名冲突）
                  若为空则不加前缀
    """

    name: str
    url: str = Field(description="MCP Server 完整接入地址（SSE 或 Streamable HTTP）")
    transport: Literal["sse", "streamable_http"] = Field(
        default="sse",
        description="传输协议：sse（Server-Sent Events）或 streamable_http",
    )
    api_key: Optional[str] = Field(
        default=None,
        description="若服务要求 X-API-Key 请求头，填在这里；key 在 url 里时可留空",
    )
    enabled: bool = Field(default=True, description="是否在启动时自动发现并注册该 server 的工具")
    headers: Dict[str, str] = Field(default_factory=dict, description="额外的 HTTP 请求头")
    tool_prefix: str = Field(
        default="",
        description="工具名前缀（如 'amap_'），防止不同 server 的工具名冲突；空字符串表示不加前缀",
    )


class SkillConfig(BaseModel):
    """
    Skill 工具的静态配置。

    - name: 暴露给大模型的工具名（Action.tool）
    - description: 在 Prompt 中展示给模型看的说明文字

    具体的执行逻辑需要在 SkillTool.run 中根据 name 去你自己的技能系统里查找。
    """

    name: str
    description: str = "自定义 Skill 工具"


class MCPToolConfig(BaseModel):
    """
    MCP Tool 的静态配置，用于动态注册 MCPTool。

    - name: 暴露给大模型的工具名（Action.tool）
    - description: 在 Prompt 中展示给模型看的说明文字
    - server_name: 使用哪一个 MCPServerConfig（如 infra-mcp）
    - tool_name: MCP Server 侧真正的工具名
    """

    name: str
    description: str = "MCP 远程工具"
    server_name: str
    tool_name: str


class AgenticSettings(BaseModel):
    llm: LLMConfig = LLMConfig()
    mcp_servers: list[MCPServerConfig] = Field(
        default_factory=list,
        description="可用的 MCP Server 列表；可按需在这里预配置",
    )
    skills: list[SkillConfig] = Field(
        default_factory=list,
        description="需要在 Agentic 工具系统中动态注册的 Skill 列表",
    )
    mcp_tools: list[MCPToolConfig] = Field(
        default_factory=list,
        description="需要在 Agentic 工具系统中动态注册的 MCPTool 列表",
    )


def _load_mcp_servers_from_env() -> list[MCPServerConfig]:
    """
    从环境变量 MCP_SERVERS_JSON 中加载 MCP Server 配置列表（JSON 数组格式）。

    示例 .env：
    MCP_SERVERS_JSON=[{"name":"amap","url":"https://mcp.amap.com/sse?key=xxx","transport":"sse","tool_prefix":"amap_"}]
    """
    import json
    import os

    raw = (os.getenv("MCP_SERVERS_JSON") or "").strip()
    if not raw:
        return []
    try:
        data = json.loads(raw)
        if not isinstance(data, list):
            return []
        return [MCPServerConfig.model_validate(item) for item in data]
    except Exception:
        return []


@lru_cache
def get_settings() -> AgenticSettings:
    """
    从 .env 或主项目配置中加载 Agentic 配置。
    MCP Server 列表优先从环境变量 MCP_SERVERS_JSON 中读取。
    """
    servers = _load_mcp_servers_from_env()
    return AgenticSettings(mcp_servers=servers)

