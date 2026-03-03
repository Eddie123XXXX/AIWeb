from __future__ import annotations

from typing import Any, Dict, Iterable, Mapping

import importlib.util
from pathlib import Path

import yaml

from .config import AgenticSettings, get_settings
from .tools import MCPTool, QueryRAGKnowledgeTool, QueryUserMemoryTool, SkillTool, WebSearchTool
from .tools_base import Tool, ToolExecutionError


class ToolRegistry:
    """
    工具注册中心：
    - 内置业务工具（query_user_memory / query_rag_knowledge / web_search 等）
    - skills 工具：把你在系统里定义的「技能」抽象为 Tool 实现
    - MCP 工具：把 MCP Server 上暴露的工具包装为本地 Tool
    """

    def __init__(self) -> None:
        self._tools: Dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        if tool.name in self._tools:
            raise ValueError(f"工具 {tool.name} 已存在，请检查重复注册。")
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool:
        try:
            return self._tools[name]
        except KeyError as exc:
            raise ToolExecutionError(f"未找到名为 {name} 的工具") from exc

    @property
    def tools(self) -> Mapping[str, Tool]:
        return self._tools


registry = ToolRegistry()


def build_tools_schema(allowed_tool_names: Iterable[str] | None = None) -> list[dict]:
    """
    将当前注册的工具转换为 OpenAI/DeepSeek 兼容的 tools 列表。
    支持三类工具的 schema 来源：
    - param_model（Pydantic BaseModel）：调用 model_json_schema()
    - get_json_schema()（RemoteMCPTool 等）：直接调用该方法
    - 兜底：空 object schema + additionalProperties
    """
    allowed_set = {str(x) for x in allowed_tool_names} if allowed_tool_names is not None else None
    tools: list[dict] = []
    for tool in registry.tools.values():
        if allowed_set is not None and tool.name not in allowed_set:
            continue
        param_model = getattr(tool, "param_model", None)
        if param_model is not None and hasattr(param_model, "model_json_schema"):
            schema = param_model.model_json_schema()
        elif hasattr(tool, "get_json_schema"):
            schema = tool.get_json_schema()
        else:
            schema = {
                "type": "object",
                "properties": {},
                "additionalProperties": True,
            }
        tools.append(
            {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": getattr(tool, "description", "") or "",
                    "parameters": schema,
                },
            }
        )
    return tools


def register_builtins() -> None:
    """注册内置固定工具。"""
    registry.register(QueryUserMemoryTool())
    registry.register(QueryRAGKnowledgeTool())
    registry.register(WebSearchTool())


def register_dynamic_from_settings(settings: AgenticSettings | None = None) -> None:
    """
    根据 AgenticSettings 中的 skills / mcp_tools 动态注册 SkillTool 与 MCPTool。

    使用方式（示例）：
    - 在 config.AgenticSettings.skills 中配置若干 SkillConfig(name, description)
    - 在 config.AgenticSettings.mcp_tools 中配置若干 MCPToolConfig(name, description, server_name, tool_name)
    然后在项目启动时调用一次本函数。
    """
    cfg = settings or get_settings()

    # 注册 SkillTool
    for sk in cfg.skills:
        try:
            registry.register(SkillTool(name=sk.name, description=sk.description))
        except ValueError:
            # 已存在同名工具时跳过，避免覆盖内置或手工注册的实现
            continue

    # 注册 MCPTool
    for mt in cfg.mcp_tools:
        try:
            registry.register(
                MCPTool(
                    name=mt.name,
                    description=mt.description,
                    server_name=mt.server_name,
                    tool_name=mt.tool_name,
                ),
            )
        except ValueError:
            continue


def load_markdown_skills(skills_dir: str | Path | None = None) -> None:
    """
    扫描 SKILLS 目录下的 Markdown 定义文件（*.md），
    为每个技能创建对应的 SkillTool 并注册到 registry。

    目录约定：
        backend/agentic/SKILLS/
            ├── web_search.md   # YAML frontmatter + Markdown 正文
            └── web_search.py   # 定义 async def execute(...)
    """
    # 解析技能目录路径（默认使用与本模块同级的 SKILLS 子目录）
    base_dir = Path(__file__).resolve().parent
    skills_path = Path(skills_dir) if skills_dir is not None else base_dir / "SKILLS"

    if not skills_path.exists() or not skills_path.is_dir():
        return

    for md_file in skills_path.glob("*.md"):
        try:
            content = md_file.read_text(encoding="utf-8")
        except OSError:
            continue

        # 提取 YAML frontmatter
        if not content.startswith("---"):
            continue
        parts = content.split("---", 2)
        if len(parts) < 3:
            continue
        frontmatter_str = parts[1]
        markdown_body = parts[2].strip()

        try:
            meta = yaml.safe_load(frontmatter_str) or {}
        except yaml.YAMLError as exc:  # noqa: BLE001
            print(f"[SkillLoader] 解析 {md_file.name} 的 YAML 失败: {exc}")
            continue

        tool_name = (meta.get("name") or "").strip()
        if not tool_name:
            print(f"[SkillLoader] {md_file.name} 缺少 name 字段，已跳过。")
            continue

        parameters_schema = meta.get("parameters") or {
            "type": "object",
            "properties": {},
            "additionalProperties": True,
        }

        description = markdown_body or (meta.get("description") or "")

        # 加载同名 Python 执行逻辑
        py_file = md_file.with_suffix(".py")
        if not py_file.exists():
            print(f"[SkillLoader] 未找到技能 {tool_name} 对应的 Python 文件: {py_file.name}，已跳过。")
            continue

        module_name = f"agentic_skill_{tool_name}"
        spec = importlib.util.spec_from_file_location(module_name, py_file)
        if spec is None or spec.loader is None:
            print(f"[SkillLoader] 无法为技能 {tool_name} 创建模块 spec。")
            continue

        module = importlib.util.module_from_spec(spec)
        try:
            spec.loader.exec_module(module)  # type: ignore[union-attr]
        except Exception as exc:  # noqa: BLE001
            print(f"[SkillLoader] 加载技能逻辑 {py_file.name} 失败: {exc}")
            continue

        handler = getattr(module, "execute", None)
        if handler is None or not callable(handler):
            print(f"[SkillLoader] 技能 {tool_name} 未在 {py_file.name} 中找到可调用的 execute 函数，已跳过。")
            continue

        try:
            tool = SkillTool(
                name=tool_name,
                description=description,
                parameters_schema=parameters_schema,
                handler_func=handler,
            )
            registry.register(tool)
            print(f"[SkillLoader] 成功注册 Markdown Skill: {tool_name}")
        except ValueError:
            # 已存在同名工具时跳过（不覆盖内置工具或配置式 Skill）
            print(f"[SkillLoader] 技能 {tool_name} 已存在，跳过 Markdown 注册。")
            continue


# 模块导入时完成一次默认注册，保证开箱即用；
# 如需更精细控制，可以在应用启动时手动调用 register_builtins / register_dynamic_from_settings。
register_builtins()
register_dynamic_from_settings()
load_markdown_skills()

