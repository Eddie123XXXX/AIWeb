# Agentic Tools 🧩

## 快速导航

- 内置工具：`user_memory`、`knowledge_search`、`web_search`、`data_analyzer`、`chart_generator`
- 扩展工具：SkillTool、MCPTool、WorkerTool
- 注册入口：`tools_registry.register_builtins()`、`register_dynamic_from_settings()`
- 相关文档：`backend/agentic/README.md`

本目录包含 Agentic 模式下的所有工具实现，供 LLM 在 ReAct 循环中调用。  
一工具一文件，内置工具在应用启动时自动注册，扩展工具由配置或 SKILLS 目录动态加载。📦

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

以下为框架类工具，用于动态注册外部能力。

- **SkillTool**（`skill_tool.py`）：将系统技能封装为 Tool；可通过 `AgenticSettings.skills` 静态注册，或通过 `SKILLS/*.md` + `*.py` 动态加载；无执行逻辑时返回「尚未实现」提示
- **MCPTool**（`mcp_tool.py`）：通过 `MCPClient` 调用远端 MCP Server 上暴露的工具；由配置或 MCP Server 发现时动态注册；权限：`mcp:invoke`
- **WorkerTool**（`worker_tool.py`）：将专业领域子 Agent 封装为标准 Tool，用于 Supervisor-Worker 多 Agent 架构；参数：`query`（必填）、`context`（可选）

---

## 📁 目录与注册流程

| 文件 | 说明 |
|------|------|
| `common.py` | `validate_params` 参数校验、`ensure_permissions` 权限检查（当前统一放行） |
| `tools_base.py` | 位于 `agentic/` 根目录，定义 `Tool`、`ToolContext`、`ToolExecutionError` 基类 |

**注册流程**：① `register_builtins()` 注册内置工具 → ② `register_dynamic_from_settings()` 根据配置注册 SkillTool、MCPTool → ③ `load_markdown_skills()` 扫描 `SKILLS/` 按 `*.md` 定义注册 SkillTool。详见 `agentic/tools_registry.py`。
