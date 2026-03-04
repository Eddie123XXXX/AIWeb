# Agentic Tools 🧩

## 快速导航

- 内置工具：`user_memory`、`knowledge_search`、`web_search`、`data_analyzer`、`chart_generator`
- 扩展工具：SkillTool、MCPTool、RemoteMCPTool、WorkerTool
- 注册入口：`tools_registry.register_builtins()`、`register_dynamic_from_settings()`、`mcp_manager.discover_and_register_mcp_tools()`
- 相关文档：`backend/agentic/README.md`

本目录包含 Agentic 模式下的所有工具实现，供 LLM 在 ReAct 循环中调用。  
一工具一文件，内置工具在应用启动时自动注册，扩展工具由配置、SKILLS 目录或 MCP Server 动态加载。📦

## ✨ 内置工具

以下工具在 `tools_registry.register_builtins()` 中自动注册，全局可用。

- 🧠 **user_memory**（`user_memory.py`）
  - 从用户长期记忆中根据 query 检索相关信息，支持按 domain_label 领域过滤
  - 参数：`query`（必填）、`domain_label`（可选：all / general_chat / user_preferences / professional_and_academic / lifestyle_and_interests / social_and_relationships / tasks_and_schedules）
  - 依赖：memory 模块（Milvus + PostgreSQL）；权限：`memory:read`

- 📚 **knowledge_search**（`knowledge_search.py`）
  - 从当前用户 RAG 知识库中根据 query 检索相关内容；遍历所有笔记本，合并结果取 Top 5
  - 参数：`query`（必填）、`notebook_id`（保留兼容，当前忽略）
  - 依赖：rag 模块（Milvus + PostgreSQL）；权限：`rag:search`

- 🌐 **web_search**（`web_search.py`）
  - 从互联网公开信息中根据 query 检索；支持 Serper 与 Bocha 两种搜索 API
  - 参数：`query`（必填）、`top_k`（默认 5）、`gl`、`hl`、`page`、`search_type`
  - 环境变量：`SERPER_API_KEY` 或 `BOCHA_API_KEY`（至少配置其一）

- 📊 **data_analyzer**（`data_analyzer.py`）
  - 自动识别数据类型和特征，执行趋势 / 分布 / 对比分析，推荐可视化类型
  - 参数：`data`（必填，字典列表/文本列表/单个字典）、`analysis_type`（auto / trend / distribution / comparison）
  - 能力：列类型推断、统计摘要、异常检测、可视化类型推荐

- 📈 **chart_generator**（`chart_generator.py`）
  - 生成 ECharts 图表配置，前端 `EChartsRenderer` 负责渲染
  - 参数：`data`（必填）、`chart_type`（line / bar / pie / scatter / table）、`title`、`subtitle`、`smooth`、`area`、`horizontal`、`stacked`、`rose`、`x_name`、`y_name`
  - 数据格式：折线/柱状 `{xAxis:[...], series:[{name, data}]}`；饼图 `[{name, value}, ...]`；散点 `[[x,y], ...]`；表格 `[{col1: val1, ...}, ...]`

---

## 🔌 扩展工具

以下为框架类工具，用于动态注册外部能力或封装子 Agent。

- **SkillTool**（`skill_tool.py`）
  - 将系统技能封装为 Tool
  - 注册方式：
    - 通过 `AgenticSettings.skills` 静态注册（仅 name/description）
    - 或通过 `SKILLS/*.md` + `*.py` 动态加载（Markdown frontmatter + `execute()` 函数）
  - 无执行逻辑时返回「尚未实现」提示，便于渐进式接入

- **MCPTool**（`mcp_tool.py`）
  - 通过 `MCPClient` 调用远端 MCP Server 上配置好的单个工具
  - 由 `AgenticSettings.mcp_tools` 中的静态映射注册（name/server_name/tool_name）
  - 权限：`mcp:invoke`

- **RemoteMCPTool**（定义在 `mcp_manager.py` 中）
  - 在 FastAPI 启动阶段通过 `discover_and_register_mcp_tools()` **自动发现** MCP Server 上的全部工具
  - 按 Server 配置的 `tool_prefix` + 远端工具名生成本地工具名，并注册到 `ToolRegistry`
  - 对 LLM 来说与普通 Tool 无差别，只需正常按工具名调用即可

- **WorkerTool**（`worker_tool.py`）
  - 将专业领域子 Agent 封装为标准 Tool，用于 Supervisor-Worker 多 Agent 架构
  - 参数：`query`（必填）、`context`（可选），返回子 Agent 的回答文本

---

## 📁 目录与注册流程

| 文件 | 说明 |
|------|------|
| `common.py` | `validate_params` 参数校验、`ensure_permissions` 权限检查（当前统一放行） |
| `tools_base.py` | 位于 `agentic/` 根目录，定义 `Tool`、`ToolContext`、`ToolExecutionError` 基类 |

**注册流程（整体）**：

1. `register_builtins()`：注册内置工具（user_memory / knowledge_search / web_search / data_analyzer / chart_generator）  
2. `register_dynamic_from_settings()`：根据 `AgenticSettings.skills` 与 `AgenticSettings.mcp_tools` 注册 SkillTool 与 MCPTool  
3. `load_markdown_skills()`：扫描 `SKILLS/` 目录下的 `*.md` + `*.py`，按 Markdown frontmatter 与 `execute()` 函数注册 SkillTool  
4. `discover_and_register_mcp_tools()`：并发向所有启用的 MCP Server 调用 `list_tools`，将每个远端工具包装为 RemoteMCPTool 并注册到 `ToolRegistry`（不覆盖已有同名工具）  

详见 `agentic/tools_registry.py` 与 `agentic/mcp_manager.py`。
