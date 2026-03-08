# DeepResearch（Agentic 下）🔎

## 快速导航

- 入口：`/api/agentic/deepresearch/*`
- 交互模型：先规划章节，再等待用户确认，之后继续研究
- 持久化：`research_sessions` + `ui_state` + `sources`
- 前端页面：`frontend/src/pages/DeepResearch.jsx`

`DeepResearch` 是 AIWeb 里专门面向“复杂主题调研与报告生成”的子系统。  
它和普通聊天、普通 Agentic 都不完全一样：不是单轮问答，也不是一次请求直接吐完整报告，而是一个**带中间确认、可恢复、可编辑、可导出**的研究工作流。

## ✨ 能力概览

- **规划先行**
  - 先根据 `query` 生成章节框架与研究问题
  - 前端展示大纲编辑器，等待用户确认后再继续
- **多智能体协作**
  - 角色包括 `ResearchArchitect`、`Research`、`DataAnalyst`、`ChartGenerate`、`Writer`、`Reviewer`
  - 流程大体为：Planning → Research → Analyze / Write → Review
- **流式研究**
  - 后端通过 SSE 推送阶段事件，前端实时更新步骤条、思考面板、引用来源和报告正文
- **可恢复**
  - 研究会话写入 `research_sessions`
  - `ui_state` 中保存 outline、panel_log、research_steps、draft_sections、search_results 等前端恢复所需状态
- **可继续编辑**
  - 报告完成后，前端仍可做局部改写、正文编辑、PDF 导出

## 🧱 与普通聊天 / Agentic 的区别

| 维度 | 普通聊天 | Agentic | DeepResearch |
|------|----------|---------|--------------|
| 会话存储 | `conversations` / `messages` | `conversations` / `messages` + trace | `research_sessions` |
| 传输方式 | WebSocket / SSE | WebSocket | SSE |
| 主要交互 | 单轮或多轮问答 | ReAct + 工具调用 | 规划 → 确认 → 研究 → 写作 → 审校 |
| 前端恢复 | 历史消息 + 流状态 | 历史消息 + trace | `ui_state` + sources + final_report |
| 模型选择 | 前端 `model_id` 生效 | 前端 `model_id` 生效 | 当前固定 `deepseek-v3.2` |

## 🔄 核心流程

1. 前端提交研究主题到 `POST /api/agentic/deepresearch/stream`
2. 后端先进入 `planning_only`，生成章节框架和研究问题
3. 服务端发送 `awaiting_outline_confirmation`，前端展示可编辑大纲
4. 用户确认后再调用继续研究接口，后端进入检索、写作、审校流程
5. 过程中的阶段、引用、正文草稿、章节内容持续写入 `research_sessions`
6. 前端可基于 `ui_state` 恢复研究步骤、思考日志、来源列表和报告内容

## 📡 主要接口

### 1. 启动规划

- **POST** `/api/agentic/deepresearch/stream`
- 常用字段：
  - `query`
  - `session_id`（可选，恢复已有会话时传）
  - `max_iterations`
  - `user_id`
  - `search_web`
  - `search_local`
  - `mode`：当前默认 `planning_only`

说明：

- `model_id` 字段当前保留在请求体中，但后端实际固定使用 `deepseek-v3.2`
- `search_web=true` 时可用联网搜索，依赖 `BOCHA_API_KEY` 或 `SERPER_API_KEY`
- `search_local=true` 时会结合当前用户的知识库检索

### 2. 继续研究

- 用户确认大纲后，通过继续研究相关接口进入正式研究阶段
- 后端会把确认后的 outline 作为批准版本继续推进，而不是重新随机规划

### 3. 历史与恢复

- 支持按 `session_id` 拉取研究详情
- 支持恢复：
  - `final_report`
  - `sources`
  - `ui_state.outline`
  - `ui_state.panel_log`
  - `ui_state.research_steps`
  - `ui_state.search_results`
  - `ui_state.draft_sections`

### 4. 报告编辑与导出

- 支持报告正文保存
- 支持选中文本后做局部改写
- 支持 PDF 导出

## 📨 SSE 事件

常见事件包括：

- `phase`：当前阶段，如 planning / researching / writing / reviewing
- `thought`：思考面板文本
- `phase_detail`：阶段细节说明
- `outline`：章节框架
- `awaiting_outline_confirmation`：等待用户确认章节
- `search_result`：新增引用或搜索结果
- `section_content`：章节级正文
- `report_draft`：汇总中的整篇报告草稿
- `review`：审校结果
- `research_complete`：研究完成
- `done`：流结束
- `error`：错误

## 🗂 关键文件

| 文件 | 作用 |
|------|------|
| `router.py` | DeepResearch 路由、SSE 编排、会话写库、恢复接口 |
| `service.py` | 研究服务入口，负责调度各阶段 |
| `graph.py` | 研究工作流状态推进 |
| `agents/` | 各角色 Agent 的具体实现 |
| `pdf_exporter.py` | Markdown / 报告转 PDF |
| `utils.py` | 事件序列化、outline 规范化、引用去重等工具函数 |

## 🧾 数据持久化

`research_sessions` 表当前至少承载以下数据：

- `query`
- `title`
- `status`
- `final_report`
- `sources`
- `ui_state`

其中 `ui_state` 主要用于前端恢复，常见字段包括：

- `phase`
- `phase_detail`
- `outline`
- `editable_outline`
- `research_steps`
- `panel_log`
- `search_results`
- `draft_sections`
- `streaming_report`
- `awaiting_user_input`

## ⚙️ 环境与依赖

- 搜索：`BOCHA_API_KEY` 或 `SERPER_API_KEY`
- 本地知识库检索：需要 RAG 依赖和当前用户已有文档
- 研究模型：当前固定使用 `DEEPSEEK_API_KEY` 对应的 `deepseek-v3.2`
- PDF 导出：依赖 `pdf_exporter.py` 中使用的报告渲染链路

## ⚠️ 当前限制

- `model_id` 目前不是 DeepResearch 的真实控制项，后端固定使用 `deepseek-v3.2`
- 这是双阶段交互流，不是“一个请求直接生成终稿”
- 若你要做生产化权限控制，还需要额外补充更细的工具与搜索边界治理
