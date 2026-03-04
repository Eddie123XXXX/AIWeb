from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from contextlib import asynccontextmanager

from fastapi import APIRouter
from fastapi import FastAPI
from fastapi import WebSocket
from fastapi import WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict
from uuid import uuid4

from db.conversation_repository import conversation_repository
from routers.models import get_model_config_by_id
from services.chat_context import get_context, get_memory_context_for_prompt, persist_round

from .agent_loop import run_agentic_session
from .config import get_settings
from .mcp_manager import discover_and_register_mcp_tools, get_registered_mcp_tools
from .tools_registry import registry

logger = logging.getLogger(__name__)


class AgenticChatRequest(BaseModel):
    # 解决 pydantic 对 model_id 命名与 protected_namespaces 冲突的告警
    model_config = ConfigDict(protected_namespaces=())

    user_query: str
    system_prompt: Optional[str] = None
    # 与主项目保持一致，user_id 使用 int；前端传字符串时 Pydantic 会自动尝试转换
    user_id: Optional[int] = None
    # 复用主项目的模型配置体系：model_id 必填或从环境变量默认推断
    model_id: Optional[str] = None
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    # 可选：与主项目共用 conversations/messages 表与 Redis 热上下文
    conversation_id: Optional[str] = None
    # 可选：仅向模型暴露的工具名列表；不传表示全部可用，传空数组表示禁用全部工具
    enabled_tools: Optional[list[str]] = None


@asynccontextmanager
async def _lifespan(app: FastAPI):
    # 启动时自动发现并注册所有 MCP Server 的工具
    await discover_and_register_mcp_tools()
    yield


app = FastAPI(title="AIWeb Agentic Backend", lifespan=_lifespan)
router = APIRouter(prefix="/api/agentic", tags=["agentic"])

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def build_system_prompt(
    custom_prompt: Optional[str],
    enabled_tools: Optional[list[str]] = None,
    agent_name: str = "supervisor",
) -> str:
    """
    构建 Agentic 模式下的基础 System Prompt。

    - 若用户传入自定义 system_prompt，则直接使用；
    - 否则根据当前 agent 的工具集自动生成：
      - 若存在 WorkerTool 类型的工具，生成 Supervisor 路由型 Prompt
      - 否则生成标准执行型 Prompt
    """
    if custom_prompt and custom_prompt.strip():
        return custom_prompt

    from .tools import WorkerTool

    available_tools = registry.get_tools_for(agent_name)
    enabled_set = {str(x) for x in enabled_tools} if enabled_tools is not None else None
    filtered_tools = [
        t for t in available_tools
        if enabled_set is None or t.name in enabled_set
    ]

    has_workers = any(isinstance(t, WorkerTool) for t in filtered_tools)
    worker_tools = [t for t in filtered_tools if isinstance(t, WorkerTool)]
    direct_tools = [t for t in filtered_tools if not isinstance(t, WorkerTool)]

    if has_workers:
        header = (
            "You are a Supervisor AI — a task dispatcher that coordinates specialized expert agents.\n\n"
            "Core principles:\n"
            "1. Do NOT answer domain-specific questions yourself. Delegate to the appropriate Worker agent.\n"
            "2. If a question spans multiple domains, call multiple Workers sequentially and synthesize their results.\n"
            "3. After receiving all Worker reports, produce a coherent Final Answer for the user.\n"
        )

        tool_lines: list[str] = []
        if worker_tools:
            tool_lines.append("\n**Expert Workers (delegate domain tasks to them):**")
            for t in worker_tools:
                desc = getattr(t, "description", "") or ""
                tool_lines.append(f'- "{t.name}": {desc}')
        if direct_tools:
            tool_lines.append("\n**Direct Tools (you can call these yourself):**")
            for t in direct_tools:
                desc = getattr(t, "description", "") or ""
                tool_lines.append(f'- "{t.name}": {desc}')

        tools_block = "\n".join(tool_lines) if tool_lines else "- (no tools registered)"
    else:
        header = (
            "You are an enterprise AI assistant with tools.\n"
            "You have access to the following tools. Use them when needed to answer the user's question.\n\n"
            "Available tools:\n"
        )
        tool_lines = []
        for t in filtered_tools:
            desc = getattr(t, "description", "") or ""
            tool_lines.append(f'- "{t.name}": {desc}')
        tools_block = "\n".join(tool_lines) if tool_lines else "- (no tools registered)"

    tail = (
        "\nImportant rules:\n"
        "- Think step by step before acting.\n"
        "- When you are ready to respond to the user, provide your Final Answer directly.\n"
        "- Reply in Chinese when the user speaks Chinese.\n"
    )

    return f"{header}{tools_block}\n{tail}"


async def _get_agentic_history_messages(conversation_id: Optional[str]) -> list[dict[str, str]]:
    """
    获取 Agentic 会话历史消息（最近窗口），用于跨轮次上下文。
    """
    if not conversation_id:
        return []
    try:
        context = await get_context(conversation_id)
    except Exception:
        return []

    out: list[dict[str, str]] = []
    for item in context:
        role = item.get("role")
        content = item.get("content")
        if role in {"user", "assistant", "system"} and isinstance(content, str) and content.strip():
            out.append({"role": role, "content": content})
    return out


@router.get("/tools")
async def list_agentic_tools() -> Dict[str, Any]:
    """
    返回当前后端已注册的 Agentic 工具列表（含 MCP 动态工具与 Worker），供前端做动态勾选。
    """
    from .tools import WorkerTool

    items = []
    for tool in registry.tools.values():
        is_mcp = hasattr(tool, "_server")
        is_worker = isinstance(tool, WorkerTool)
        if is_mcp:
            source = "mcp"
        elif is_worker:
            source = "worker"
        else:
            source = "builtin"
        items.append(
            {
                "name": tool.name,
                "description": getattr(tool, "description", "") or "",
                "source": source,
                "server": tool._server.name if is_mcp else None,
            }
        )
    items.sort(key=lambda x: (x["source"], x["server"] or "", x["name"]))
    return {"items": items}


@router.get("/mcp-servers")
async def list_mcp_servers() -> Dict[str, Any]:
    """
    返回当前配置的 MCP Server 列表及其已注册工具情况，供管理查看。
    """
    settings = get_settings()
    mcp_tools = get_registered_mcp_tools()
    tool_by_server: Dict[str, list] = {}
    for t in mcp_tools:
        tool_by_server.setdefault(t["server"], []).append(t["name"])

    servers = []
    for s in settings.mcp_servers:
        servers.append(
            {
                "name": s.name,
                "url": s.url,
                "transport": s.transport,
                "enabled": s.enabled,
                "tool_prefix": s.tool_prefix,
                "registered_tools": tool_by_server.get(s.name, []),
            }
        )
    return {"servers": servers, "total_mcp_tools": len(mcp_tools)}


@router.post("/mcp-servers/refresh")
async def refresh_mcp_tools() -> Dict[str, Any]:
    """
    重新发现并注册所有 MCP Server 的工具（热重载，无需重启后端）。
    已注册工具不会重复添加。
    """
    await discover_and_register_mcp_tools()
    mcp_tools = get_registered_mcp_tools()
    return {"message": "MCP 工具已刷新", "registered_count": len(mcp_tools)}


class AddMCPServerRequest(BaseModel):
    name: str
    url: str
    transport: str = "sse"
    api_key: Optional[str] = None
    tool_prefix: str = ""
    headers: Dict[str, str] = {}


@router.post("/mcp-servers/add")
async def add_mcp_server(req: AddMCPServerRequest) -> Dict[str, Any]:
    """
    动态添加一个 MCP Server，发现其工具并注册到当前会话。
    重启后失效；如需持久化，请将配置加入 .env 的 MCP_SERVERS_JSON。
    """
    from .config import MCPServerConfig
    from .mcp_manager import _discover_server

    transport = req.transport if req.transport in ("sse", "streamable_http") else "sse"
    server = MCPServerConfig(
        name=req.name,
        url=req.url,
        transport=transport,
        api_key=req.api_key or None,
        tool_prefix=req.tool_prefix,
        headers=req.headers,
        enabled=True,
    )

    try:
        tools = await _discover_server(server)
    except Exception as exc:
        logger.error("[MCP] add_mcp_server 发现工具失败: %s", exc, exc_info=True)
        from fastapi.responses import JSONResponse
        return JSONResponse(
            status_code=502,
            content={"detail": f"无法连接到 MCP Server 或发现工具失败: {type(exc).__name__}: {exc or repr(exc)}"},
        )

    registered: list[str] = []
    skipped: list[str] = []
    for tool in tools:
        try:
            registry.register(tool)
            registered.append(tool.name)
        except ValueError:
            skipped.append(tool.name)

    return {
        "server": req.name,
        "registered": registered,
        "skipped": skipped,
        "total_discovered": len(tools),
        "env_hint": (
            f'要在重启后保留此 Server，请将以下内容加入 .env：\n'
            f'MCP_SERVERS_JSON=[{{"name":"{req.name}","url":"{req.url}",'
            f'"transport":"{transport}","tool_prefix":"{req.tool_prefix}","enabled":true}}]'
        ),
    }


@router.websocket("/ws")
async def agentic_ws(websocket: WebSocket) -> None:
    """
    Agentic 模式主入口（WebSocket 流式）。

    请求：连接后发送 JSON，含 user_query、system_prompt（可选）、model_id、conversation_id、enabled_tools 等。

    响应事件（按序推送）：
    - stream_delta: 逐 token 流式输出（thought 或最终回答）
    - thought: 完整思考内容（流结束后）
    - action: 工具调用（tool、parameters）
    - observation_delta: 工具结果流式块
    - observation: 工具结果完整内容
    - final_answer: 最终回答
    - error: 异常信息
    """
    await websocket.accept()
    try:
        init_msg = await websocket.receive_json()
        req = AgenticChatRequest(**init_msg)
    except Exception:
        await websocket.close(code=1003)
        return

    settings = get_settings()

    # 解析模型配置（用于 conversations.model_provider 与 LLM 调用）
    model_id = req.model_id or "default"
    model_config = get_model_config_by_id(model_id)

    # 确定/创建 conversation_id
    conv_id: Optional[str] = req.conversation_id
    conv_row: Optional[dict[str, Any]] = None
    if conv_id:
        conv_row = await conversation_repository.get_by_id(conv_id)
    elif req.user_id is not None:
        conv_id = str(uuid4())
        conv_row = await conversation_repository.create(
            conversation_id=conv_id,
            user_id=int(req.user_id),
            title="Agentic 对话",
            system_prompt=None,
            model_provider=model_config.provider,
        )

    # 确定用于工具 & 记忆检索的 user_id：优先请求体中的 user_id，其次会话中的 user_id
    effective_user_id: Optional[int] = None
    if req.user_id is not None:
        effective_user_id = int(req.user_id)
    elif conv_row and conv_row.get("user_id"):
        effective_user_id = int(conv_row["user_id"])

    # 基础 Agentic System Prompt：ReAct 协议 + 动态工具列表
    base_system_prompt = build_system_prompt(req.system_prompt, req.enabled_tools)

    # 若存在会话与用户信息，则召回长期记忆并拼入 system
    system_prompt = base_system_prompt
    if conv_row and conv_row.get("user_id"):
        try:
            memory_block = await get_memory_context_for_prompt(
                user_id=int(conv_row["user_id"]),
                conversation_id=conv_id or "",
                query=req.user_query,
            )
            parts = [base_system_prompt]
            if conv_row.get("system_prompt"):
                parts.append(str(conv_row["system_prompt"]))
            if memory_block:
                parts.append("【长期记忆】\n" + memory_block)
            system_prompt = "\n\n".join(parts)
        except Exception:
            # 记忆召回失败不影响主流程，回退到基础 system prompt
            system_prompt = base_system_prompt
    history_messages = await _get_agentic_history_messages(conv_id)

    async def send_json(payload: Dict[str, Any]) -> None:
        await websocket.send_json(payload)

    trace_events: list[dict[str, Any]] = []

    async def on_stream_delta(token: str) -> None:
        """LLM 逐 token 推送——真正的流式体验。"""
        await send_json({"event": "stream_delta", "content": token})

    async def on_thought(thought: str, step: int) -> None:
        trace_events.append({"type": "thought", "step": step, "content": thought})
        await send_json({"event": "thought", "step": step, "content": thought})

    async def on_action(tool: str, parameters: Dict[str, Any], step: int) -> None:
        trace_events.append(
            {
                "type": "action",
                "step": step,
                "tool": tool,
                "parameters": parameters,
                "content": "",
            }
        )
        await send_json(
            {
                "event": "action",
                "step": step,
                "tool": tool,
                "parameters": parameters,
            },
        )

    async def on_observation_delta(chunk: str, step: int) -> None:
        """工具结果流式推送——逐块发送，前端可实时显示。"""
        await send_json({"event": "observation_delta", "step": step, "content": chunk})

    async def on_observation(content: str, step: int) -> None:
        trace_events.append({"type": "observation", "step": step, "content": content})
        await send_json({"event": "observation", "step": step, "content": content})

    async def on_final_answer(content: str) -> None:
        # 将最终答案发给前端
        await send_json(
            {
                "event": "final_answer",
                "content": content,
                "conversation_id": conv_id,
            },
        )
        # 将本轮 Agentic 对话写入 conversations/messages，并触发长期记忆写入
        if conv_id is not None:
            try:
                await persist_round(
                    conv_id,
                    req.user_query,
                    content,
                    assistant_metadata={
                        "agentic_trace": {
                            "version": 1,
                            "status": "done",
                            "events": trace_events,
                        }
                    },
                    model_id=model_id,
                )
            except Exception as exc:
                logger.exception("Agentic WS 持久化（含 trace）失败，降级为仅保存最终答案: %s", exc)
                try:
                    await persist_round(
                        conv_id,
                        req.user_query,
                        content,
                        model_id=model_id,
                    )
                except Exception as exc2:
                    logger.exception("Agentic WS 持久化（降级）仍失败: %s", exc2)

    try:
        await run_agentic_session(
            user_query=req.user_query,
            system_prompt=system_prompt,
            model_id=model_id,
            user_id=effective_user_id,
            history_messages=history_messages,
            enabled_tool_names=req.enabled_tools,
            temperature=req.temperature,
            max_tokens=req.max_tokens,
            on_thought=on_thought,
            on_action=on_action,
            on_observation=on_observation,
            on_observation_delta=on_observation_delta,
            on_final_answer=on_final_answer,
            on_stream_delta=on_stream_delta,
        )
    except WebSocketDisconnect:
        # 前端断开时静默退出
        return
    except Exception as exc:  # noqa: BLE001
        # 出现未捕获异常时，也通过 WebSocket 告诉前端
        await send_json(
            {
                "event": "error",
                "message": f"Agentic 会话内部错误：{exc}",
            },
        )
        await websocket.close(code=1011)


@router.post("/chat")
async def agentic_http_chat(req: AgenticChatRequest) -> Dict[str, Any]:
    """
    Agentic 模式 HTTP 入口（非流式）。

    执行完整 ReAct 循环后返回 final_answer，不推送 thought/action/observation 事件。
    适用于不需要推理面板的前端场景。
    """
    settings = get_settings()
    model_id = req.model_id or "default"
    model_config = get_model_config_by_id(model_id)

    # 确定/创建 conversation_id
    conv_id: Optional[str] = req.conversation_id
    conv_row: Optional[dict[str, Any]] = None
    if conv_id:
        conv_row = await conversation_repository.get_by_id(conv_id)
    elif req.user_id is not None:
        conv_id = str(uuid4())
        conv_row = await conversation_repository.create(
            conversation_id=conv_id,
            user_id=int(req.user_id),
            title="Agentic 对话",
            system_prompt=None,
            model_provider=model_config.provider,
        )

    # 与 WebSocket 路径一致，推导有效 user_id
    effective_user_id: Optional[int] = None
    if req.user_id is not None:
        effective_user_id = int(req.user_id)
    elif conv_row and conv_row.get("user_id"):
        effective_user_id = int(conv_row["user_id"])

    base_system_prompt = build_system_prompt(req.system_prompt, req.enabled_tools)

    system_prompt = base_system_prompt
    if conv_row and conv_row.get("user_id"):
        try:
            memory_block = await get_memory_context_for_prompt(
                user_id=int(conv_row["user_id"]),
                conversation_id=conv_id or "",
                query=req.user_query,
            )
            parts = [base_system_prompt]
            if conv_row.get("system_prompt"):
                parts.append(str(conv_row["system_prompt"]))
            if memory_block:
                parts.append("【长期记忆】\n" + memory_block)
            system_prompt = "\n\n".join(parts)
        except Exception:
            system_prompt = base_system_prompt
    history_messages = await _get_agentic_history_messages(conv_id)

    trace_events: list[dict[str, Any]] = []

    async def on_thought_http(thought: str, step: int) -> None:
        trace_events.append({"type": "thought", "step": step, "content": thought})

    async def on_action_http(tool: str, parameters: Dict[str, Any], step: int) -> None:
        trace_events.append(
            {
                "type": "action",
                "step": step,
                "tool": tool,
                "parameters": parameters,
                "content": "",
            }
        )

    async def on_observation_http(content: str, step: int) -> None:
        trace_events.append({"type": "observation", "step": step, "content": content})

    final_answer = await run_agentic_session(
        user_query=req.user_query,
        system_prompt=system_prompt,
        model_id=model_id,
        user_id=effective_user_id,
        history_messages=history_messages,
        enabled_tool_names=req.enabled_tools,
        temperature=req.temperature,
        max_tokens=req.max_tokens,
        on_thought=on_thought_http,
        on_action=on_action_http,
        on_observation=on_observation_http,
    )

    # 持久化本轮对话
    if conv_id is not None:
        try:
            await persist_round(
                conv_id,
                req.user_query,
                final_answer,
                assistant_metadata={
                    "agentic_trace": {
                        "version": 1,
                        "status": "done",
                        "events": trace_events,
                    }
                },
                model_id=model_id,
            )
        except Exception as exc:
            logger.exception("Agentic HTTP 持久化（含 trace）失败，降级为仅保存最终答案: %s", exc)
            try:
                await persist_round(
                    conv_id,
                    req.user_query,
                    final_answer,
                    model_id=model_id,
                )
            except Exception as exc2:
                logger.exception("Agentic HTTP 持久化（降级）仍失败: %s", exc2)

    return {"final_answer": final_answer, "conversation_id": conv_id}


app.include_router(router)

