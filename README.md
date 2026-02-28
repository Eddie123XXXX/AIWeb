# AIWeb 🚀

一个面向个人与小团队的全栈 AI 工作台。  
前端基于 React + Vite，后端基于 FastAPI，整合「聊天 / 记忆 / 知识库 / 文件解析」等能力，帮你在本地或私有环境里搭建**自己的 AI 助手控制台**。😎

> 如果你觉得「只用一个浏览器 tab」就能管理模型、记忆、RAG 和文件，那大概就是这个项目想给你的感觉。

## ✨ 功能概览

- 💬 **多模型聊天**
  - 支持多家 OpenAI 兼容模型（如 OpenAI、DeepSeek、Qwen 等）
  - WebSocket 流式输出，代码块高亮，支持复制按钮

- 🧠 **分层长期记忆模块（`backend/memory`）**
  - 使用 Milvus + PostgreSQL 做混合记忆检索
  - 重要性打分 + 时间衰减 + 反思压缩
  - 自动召回「用户偏好 / 关键决策 / 长期项目背景」这类高价值信息

- 📎 **Quick Parse 文件解析（聊天下的临时文件上传）**
  - 前端通过 MinIO 上传文件，在输入框 & 聊天记录中展示**文件预览卡片**
  - 后端用 `services/quick_parse.py` 将 PDF / Word / Excel / CSV / TXT 解析为 Markdown 文本
  - 解析结果只作为当前轮对话的「工作记忆」，**不会写入长期记忆或知识库**
  - 有 Token 粗略估算与截断，避免一不小心把上下文吃爆
  - 每次使用 Quick Parse，都有浅提示告诉你：如需长期/多轮使用，请上传到知识库

- 📚 **RAG 知识库**
  - 独立 RAG 页面（wiki/search）：上传文档 → MinerU/多格式解析 → 版面感知切块 → Dense+Sparse 向量化 → 三段式检索（精确+FTS+RRF+Reranker）
  - 与聊天结合：勾选知识源后提问，召回 chunk 注入上下文，AI 基于检索结果回答；右侧展示召回卡片（表格/图片/公式富文本）、展开文件可定位高亮
  - 来源指南：文档总结入库（大文档截断后生成），展开文件弹窗内展示

- 🧱 **基础运维与基础设施集成**
  - `infra/docker-compose.yml` 一键拉起 PostgreSQL / Redis / MinIO / Milvus / RabbitMQ / Elasticsearch 等依赖服务
  - 提供调试路由：Redis / Postgres / RabbitMQ / Elasticsearch 等健康检查

---

## 🗂 目录结构（简要）

- `frontend/`：前端 React 应用（对话页 / 知识库页 / 登录注册等）
- `backend/`：FastAPI 后端
  - `routers/chat.py`：聊天主路由（含 WebSocket）
  - `services/llm_service.py`：LLM 统一调用封装
  - `services/chat_context.py`：对话上下文读取与持久化（Redis + Postgres）
  - `memory/`：长期记忆模块（打分 / 向量检索 / 遗忘 / 反思）
  - `infra/minio/`：对象存储上传、预签名 URL 生成
  - `services/quick_parse.py`：Quick Parse 文件解析逻辑
  - `db/`：数据库建表脚本与说明
  - `infra/`：后端 Infra 适配（Redis / Postgres / MinIO / Milvus / RabbitMQ / Elasticsearch 等）

- `infra/`：Docker Compose 基础设施（MinIO, Redis, PostgreSQL, Milvus, Attu, RabbitMQ, RedisInsight, pgAdmin, Elasticsearch, Kibana）

---

## 🔄 实现流程与技术流程概览

### 请求与数据流（整体）

1. **用户发起对话（主聊天页）**
   - 前端：`useChat` → WebSocket `/api/chat/ws` 发送消息（含 `model_id`、`conversation_id`、可选 `rag_context`、`quick_parse_files`）。
   - 后端：`routers/chat.py` 接收 → 解析会话与历史（Redis/PostgreSQL）→ 意图路由与记忆召回（`memory.retrieve_relevant_memories`）→ 拼 system（长期记忆 + 知识库上下文 + Quick Parse 内容）→ 调用 `LLMService.chat()` 流式返回。
   - 落库：`chat_context.persist_round` 写 messages 表，异步触发 `memory.extract_and_store_memories_for_round` 写入/反思。

2. **RAG 检索与回答（wiki/search 页）**
   - 前端：用户勾选知识源后输入问题 → 先请求 `POST /api/rag/search`（`document_ids` 仅包含勾选文档）→ 用 `buildRAGContextFromHits` 拼上下文 → 再通过 WebSocket 发同一问题并带上 `rag_context`。
   - 后端：RAG 检索三路召回（精确 + Sparse + Dense）→ RRF 融合 → Reranker 精排 → 返回 hits；聊天侧将 `rag_context` 注入 system，LLM 基于检索内容回答。

3. **文档入库（RAG）**
   - 上传：`POST /api/rag/documents/upload` → SHA-256 防重/秒传 → MinIO 存储 → `documents` 表。
   - 解析：`POST /api/rag/documents/{id}/process` → MinerU（或本地/pdfplumber）/多格式解析 → Block 规范化 → 图片上传 MinIO + 可选 VLM → 版面感知切块（Parent-Child）→ PostgreSQL 全量切片 + 仅 Child 向量化写入 Milvus。

4. **展开文件与来源指南**
   - `GET /api/rag/documents/{id}/markdown` 返回 `filename`、`segments`（含 `chunk_id`）、`summary`；无 summary 时后端截断内容调用 LLM 生成并入库，前端弹窗内定位到对应 chunk 并高亮。

### 技术栈与分层

| 层级 | 技术 | 职责 |
|------|------|------|
| 前端 | React 18, Vite, WebSocket | 路由、聊天 UI、RAG 知识源/检索卡片、Markdown+公式渲染、主题与 i18n |
| 网关/API | FastAPI | 路由、CORS、OpenAPI/Swagger、认证占位 |
| 对话与上下文 | chat router, chat_context, LLMService | 会话解析、历史持久化、Prompt 组装、流式输出 |
| 记忆 | memory 模块 | 打分写入、混合召回（语义+时间衰减+重要性）、反思与遗忘 |
| RAG | rag 模块 | 上传/解析/切块/向量化、三段式检索、来源指南总结 |
| 存储 | PostgreSQL, Redis, MinIO, Milvus | 用户/会话/消息/记忆/文档与切片、缓存、对象存储、向量 |

---

## 🚀 快速开始（本地开发）

1. 克隆仓库并进入项目目录：

   ```bash
   git clone <your-repo-url>
   cd AIWeb
   ```

2. 启动基础设施（可选，但强烈推荐）：

   ```bash
   cd infra
   docker compose -f docker-compose.yml up -d
   ```

3. 启动后端：

   ```bash
   cd backend
   # 首次部署：复制 .env.example 为 .env，按需填写 API Key、数据库等
   pip install -r requirements.txt
   python -m db.run_schema              # 首次：建表（需 PostgreSQL 已启动）
   python -m rag.migrate_add_summary    # 首次且使用 RAG：为 documents 增加 summary 列
   python main.py
   # 或 uvicorn main:app --host 0.0.0.0 --port 8000
   ```

4. 启动前端：

   ```bash
   cd frontend
   npm install
   npm run dev
   ```

5. 访问前端（默认）：

   - `http://localhost:5173/`

**首次部署建议**：在 `backend` 目录将 `.env.example` 复制为 `.env`，按需填写 API Key、数据库等；不填的项使用代码内默认值（如本机 Redis/PostgreSQL/MinIO）。**无需配置 ngrok 即可本地使用**；仅当使用 [mineru.net](https://mineru.net) 云端解析 PDF 时，才需要把本机 MinIO 通过 ngrok/cloudflared 暴露公网并配置 `MINIO_PUBLIC_ENDPOINT`，详见 `backend/rag/README.md` 中「本地开发 + 外部 MinerU」一节。

---

## 🗺 Roadmap / TODO

- [x] 对话历史持久化
- [x] 长期记忆模块
- [x] 聊天下的 Quick Parse 文件上传与解析
- [x] 知识库 RAG 工作流（上传 / 解析 / 切块 / 向量化 / 三段式检索 / 来源指南）
- [x] RAG 与聊天结合（勾选知识源、召回注入、卡片展示与展开定位高亮）
- [ ] 用户认证与多用户隔离（当前为占位）
- [ ] 使用统计与配额（请求次数 / Token 用量）
- [ ] 个人中心页面优化
- [ ] RAG 系统更多格式文件支持及测试
- [ ] RAG功能优化
- [ ] 语音转文字输入
- [ ] 联网搜索
- [ ] 深度搜索功能及页面
- [ ] mcp接口
- [ ] skill接口
- [ ] 临时对话

