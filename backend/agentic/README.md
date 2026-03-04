# AIWeb Agentic Module 🤖

## 快速导航

- 入口：`/api/agentic/ws`、`/api/agentic/chat`
- 核心：`agent_loop.py`（ReAct + Tool Calls）
- 工具：`agentic/tools/`（一工具一文件）
- 动态注册：skills / MCP tools（由配置驱动）

## Agentic 模式后端说明（backend/agentic）

### 1. 目录与入口

- `backend/requirements.txt`：本后端所需依赖（FastAPI / httpx / pydantic 等）
- `backend/agentic/main.py`：FastAPI 应用入口，包含：
  - `WebSocket /api/agentic/ws`：Agentic 模式主入口（token 级流式 + 工具结果流式）
  - `POST /api/agentic/chat`：非流式 HTTP 入口（仅返回最终回答）
- `backend/agentic/agent_loop.py`：核心 Agent Loop 实现（含 MAX_STEPS 熔断与 Error Observation）
- `backend/agentic/llm_client.py`：LLM 调用封装，假定使用 OpenAI 兼容 `/v1/chat/completions` 接口
- `backend/agentic/tools_base.py`：Tool 标准接口定义（Tool / ToolContext / ToolExecutionError）
- `backend/agentic/tools_registry.py`：工具注册中心，内置：
  - `user_memory`：用户记忆检索（对接 memory 模块）
  - `knowledge_search`：RAG 知识库检索（对接 rag 模块）
  - `web_search`：联网搜索
  - `data_analyzer`：智能数据分析（趋势/分布/对比/异常检测）
  - `chart_generator`：ECharts 图表生成（折线/柱状/饼图/散点/表格）
  - `SkillTool`：skills 占位（将系统中的技能封装为 Tool）
  - `MCPTool`：MCP 工具包装器，通过 `MCPClient` 调用 MCP Server
- `backend/agentic/mcp_client.py`：MCP 客户端占位实现（统一 `invoke(server_name, tool_name, arguments)` 接口）
- `backend/agentic/config.py`：Agentic 配置（LLM 模型、MAX_STEPS、MCP Server 列表、动态 Skill/MCPTool 配置等）
- `backend/agentic/SKILLS/`：Skill 定义目录，一 Skill 一文件（`<name>.md` 描述 + `<name>.py` 实现），示例：`web_search`；由 `SkillTool` 动态加载并暴露给大模型

### 2. 运行方式（已与主项目适配）

```bash
cd backend
pip install -r requirements.txt

# 推荐方式：直接启动主后端（已在 main.py 中挂载 agentic 路由）
python main.py
# 或 uvicorn main:app --host 0.0.0.0 --port 8000

# 可选：单独运行 agentic.main 作为独立服务
uvicorn agentic.main:app --host 0.0.0.0 --port 8001 --reload
```

环境变量（示例，按你的实际 LLM 网关调整）：

```bash
export OPENAI_API_KEY="xxx"
export OPENAI_BASE_URL="https://api.openai.com/v1"  # 或你的代理地址
```

### 3. 前端接入（WebSocket Agentic 模式）

前端在「Agentic 模式」下，可以使用 WebSocket 连接：

- URL：`ws://<backend-host>:8001/api/agentic/ws`
- 连接成功后先发送一条 JSON：

```json
{
  "user_query": "帮我查一下那个图纸审核项目的 YOLO 模型部署在哪个服务器，顺便查一下相关文档的配置。",
  "system_prompt": "你是一个具备 ReAct 能力的企业级助手，请严格使用 Thought / Action / Observation / Final Answer 模式……",
  "user_id": "optional-user-id"
}
```

后端在 Agent Loop 中会按步骤流式推送事件，典型序列如下：

```json
{ "event": "stream_delta", "content": "用" }
{ "event": "stream_delta", "content": "户" }
...
{ "event": "thought", "step": 0, "content": "用户询问了图纸审核项目中的 YOLO 模型服务器位置..." }
{ "event": "action", "step": 0, "tool": "user_memory", "parameters": {"domain": "vision_cad_agent", "query": "YOLO模型部署服务器位置"} }
{ "event": "observation_delta", "step": 0, "content": "从用户长期记忆中检索到" }
{ "event": "observation", "step": 0, "content": "Observation: 记忆显示：YOLOv8 部署在 192.168.1.100 ..." }
...
{ "event": "final_answer", "content": "根据您的记忆记录...", "conversation_id": "xxx" }
```

事件说明：

- `stream_delta`：LLM 逐 token 流式输出，前端实时渲染
- `thought`：完整思考内容（流结束后）
- `action`：工具调用（tool、parameters）
- `observation_delta`：工具结果流式块
- `observation`：工具结果完整内容
- `final_answer`：最终回答，渲染到聊天气泡

### 4. skills 与 MCP 接入说明

- **skills（动态注册 SkillTool）**
  - 在 `config.AgenticSettings.skills` 中声明要暴露给大模型的技能列表，每个包含：
    - `name`: 工具名（LLM 的 `Action.tool` 字段）
    - `description`: 在 Prompt 中描述这个工具的作用
  - 模块加载时，`tools_registry.register_dynamic_from_settings()` 会根据这些配置自动执行：
    - 为每个 `SkillConfig` 生成一个 `SkillTool` 实例并 `registry.register()`。
  - 你需要在 `SkillTool.run` 中，根据 `self.name` 和 `params` 调用你自己的技能系统（数据库 / 插件 / 函数映射）来完成真实执行。
  - LLM Prompt 中只需声明这些 skills 为可用工具，并约定使用 `Action: {"tool": "<skill_name>", "parameters": {...}}` 的格式即可。

- **MCP（动态注册 MCPTool）**
  - 在 `config.AgenticSettings.mcp_servers` 中配置可用的 MCP Server：
    - `name`：逻辑名，例如 `"infra-mcp"`
    - `endpoint`：MCP Server 地址（例如 `http://localhost:9000` 或 `unix://...`）
  - 在 `config.AgenticSettings.mcp_tools` 中配置要暴露给 Agentic 的 MCP 工具：
    - `name`: 工具名（LLM 的 `Action.tool` 字段）
    - `description`: 在 Prompt 中的说明
    - `server_name`: 上面 `mcp_servers` 中的某个 `name`
    - `tool_name`: MCP Server 侧真实工具名
  - 模块加载时，`tools_registry.register_dynamic_from_settings()` 会：
    - 为每个 `MCPToolConfig` 创建一个 `MCPTool` 实例并 `registry.register()`；
    - `MCPTool.run` 内部调用 `MCPClient.invoke(server_name, tool_name, arguments)`，再把结果包装为 Observation 返回给大模型。
  - 大模型只需输出 `Action: {"tool": "你的-mcp-tool-name", "parameters": {...}}`，Agent Loop 会自动调用 MCP 并把结果反馈。

### 5. 死循环与错误护栏

- **死循环熔断**：`config.LLMConfig.max_steps` 控制最大循环次数（默认 5）。超过后 Agent Loop 会自动返回一条友好的 fallback Final Answer。
- **错误 Observation**：
  - 工具内部抛出 `ToolExecutionError` 时，会被转成形如：
    - `Observation: 工具执行失败，错误信息：XXX。请尝试调整参数，或在无法修复时向用户解释情况。`
  - 其他未知异常也会被包装为 Observation，并提示模型在最终回答中说明失败原因，而不是直接 HTTP 500。

