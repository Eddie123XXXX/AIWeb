from __future__ import annotations

import importlib.util
import logging
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping, Optional, Set

import yaml

from .config import AgenticSettings, get_settings
from .tools import ChartGeneratorTool, DataAnalyzerTool, KnowledgeSearchTool, MCPTool, SkillTool, UserMemoryTool, WebSearchTool
from .tools_base import Tool, ToolExecutionError

logger = logging.getLogger("agentic.registry")


class ToolRegistry:
    """
    工具注册中心（支持 Router-Worker 多 Agent 架构）。

    核心能力：
    - 全局工具注册 / 查询
    - 按 agent 名称划分工具集（agent_tool_map）
    - 生成 OpenAI 兼容的 tools schema
    """

    def __init__(self) -> None:
        self._tools: Dict[str, Tool] = {}
        self._agent_tool_map: Dict[str, Set[str]] = {}

    def register(self, tool: Tool, *, agents: Iterable[str] | None = None) -> None:
        """
        注册一个工具。

        agents: 指定该工具属于哪些 agent；
                None 表示注册到全局（所有 agent 均可用）。
        """
        if tool.name in self._tools:
            raise ValueError(f"工具 {tool.name} 已存在，请检查重复注册。")
        self._tools[tool.name] = tool
        if agents:
            for agent_name in agents:
                self._agent_tool_map.setdefault(agent_name, set()).add(tool.name)

    def assign_tool_to_agent(self, tool_name: str, agent_name: str) -> None:
        """将已注册的工具分配给指定 agent。"""
        if tool_name not in self._tools:
            raise ValueError(f"工具 {tool_name} 尚未注册")
        self._agent_tool_map.setdefault(agent_name, set()).add(tool_name)

    def get_tools_for(self, agent_name: str) -> list[Tool]:
        """
        获取指定 agent 可用的工具列表。

        优先使用 agent_tool_map 中的映射；
        若该 agent 未配置专用工具集，则回退到全部工具。
        """
        if agent_name in self._agent_tool_map:
            return [
                self._tools[name]
                for name in self._agent_tool_map[agent_name]
                if name in self._tools
            ]
        return list(self._tools.values())

    def get_tools_schema_for(
        self,
        agent_name: str,
        enabled_tool_names: Optional[Set[str]] = None,
    ) -> list[dict]:
        """
        生成指定 agent 的 OpenAI 兼容 tools schema。

        同时支持 enabled_tool_names 过滤（前端勾选功能）。
        """
        available_tools = self.get_tools_for(agent_name)
        return _build_schema_from_tools(available_tools, enabled_tool_names)

    def get(self, name: str) -> Tool:
        try:
            return self._tools[name]
        except KeyError as exc:
            raise ToolExecutionError(f"未找到名为 {name} 的工具") from exc

    @property
    def tools(self) -> Mapping[str, Tool]:
        return self._tools


registry = ToolRegistry()


# ---------------------------------------------------------------------------
# Schema 生成
# ---------------------------------------------------------------------------

def _build_schema_from_tools(
    tools: list[Tool],
    enabled_names: Optional[Set[str]] = None,
) -> list[dict]:
    """将工具列表转为 OpenAI/DeepSeek 兼容的 tools schema。"""
    result: list[dict] = []
    for tool in tools:
        if enabled_names is not None and tool.name not in enabled_names:
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

        result.append(
            {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": getattr(tool, "description", "") or "",
                    "parameters": schema,
                },
            }
        )
    return result


def build_tools_schema(allowed_tool_names: Iterable[str] | None = None) -> list[dict]:
    """
    兼容旧接口：将当前注册的工具转换为 OpenAI 兼容的 tools 列表。
    """
    allowed_set = {str(x) for x in allowed_tool_names} if allowed_tool_names is not None else None
    return _build_schema_from_tools(list(registry.tools.values()), allowed_set)


# ---------------------------------------------------------------------------
# 内置工具注册
# ---------------------------------------------------------------------------

def register_builtins() -> None:
    """注册内置固定工具（全局可用，不绑定特定 agent）。"""
    registry.register(UserMemoryTool())
    registry.register(KnowledgeSearchTool())
    registry.register(WebSearchTool())
    registry.register(DataAnalyzerTool())
    registry.register(ChartGeneratorTool())


def register_dynamic_from_settings(settings: AgenticSettings | None = None) -> None:
    """
    根据 AgenticSettings 中的 skills / mcp_tools 动态注册 SkillTool 与 MCPTool。
    """
    cfg = settings or get_settings()

    for sk in cfg.skills:
        try:
            registry.register(SkillTool(name=sk.name, description=sk.description))
        except ValueError:
            continue

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
    """
    base_dir = Path(__file__).resolve().parent
    skills_path = Path(skills_dir) if skills_dir is not None else base_dir / "SKILLS"

    if not skills_path.exists() or not skills_path.is_dir():
        return

    for md_file in skills_path.glob("*.md"):
        try:
            content = md_file.read_text(encoding="utf-8")
        except OSError:
            continue

        if not content.startswith("---"):
            continue
        parts = content.split("---", 2)
        if len(parts) < 3:
            continue
        frontmatter_str = parts[1]
        markdown_body = parts[2].strip()

        try:
            meta = yaml.safe_load(frontmatter_str) or {}
        except yaml.YAMLError as exc:
            logger.warning("[SkillLoader] 解析 %s 的 YAML 失败: %s", md_file.name, exc)
            continue

        tool_name = (meta.get("name") or "").strip()
        if not tool_name:
            logger.warning("[SkillLoader] %s 缺少 name 字段，已跳过。", md_file.name)
            continue

        parameters_schema = meta.get("parameters") or {
            "type": "object",
            "properties": {},
            "additionalProperties": True,
        }

        description = markdown_body or (meta.get("description") or "")

        py_file = md_file.with_suffix(".py")
        if not py_file.exists():
            logger.warning("[SkillLoader] 未找到技能 %s 的 Python 文件: %s", tool_name, py_file.name)
            continue

        module_name = f"agentic_skill_{tool_name}"
        spec = importlib.util.spec_from_file_location(module_name, py_file)
        if spec is None or spec.loader is None:
            logger.warning("[SkillLoader] 无法为技能 %s 创建模块 spec", tool_name)
            continue

        module = importlib.util.module_from_spec(spec)
        try:
            spec.loader.exec_module(module)  # type: ignore[union-attr]
        except Exception as exc:
            logger.warning("[SkillLoader] 加载技能逻辑 %s 失败: %s", py_file.name, exc)
            continue

        handler = getattr(module, "execute", None)
        if handler is None or not callable(handler):
            logger.warning("[SkillLoader] 技能 %s 的 %s 中未找到 execute 函数", tool_name, py_file.name)
            continue

        # 从 frontmatter 读取可选的 agent 归属
        skill_agents = meta.get("agents")
        agents_list: list[str] | None = None
        if isinstance(skill_agents, list):
            agents_list = [str(a) for a in skill_agents]

        try:
            tool = SkillTool(
                name=tool_name,
                description=description,
                parameters_schema=parameters_schema,
                handler_func=handler,
            )
            registry.register(tool, agents=agents_list)
            logger.info("[SkillLoader] 成功注册 Markdown Skill: %s", tool_name)
        except ValueError:
            logger.info("[SkillLoader] 技能 %s 已存在，跳过", tool_name)
            continue


register_builtins()
register_dynamic_from_settings()
load_markdown_skills()
