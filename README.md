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

- 📚 **RAG 知识库（规划中 / 部分实现）**
  - 独立的 RAG 页面，支持上传文档构建索引
  - 计划与聊天功能结合，实现「知识库检索 + 个人记忆」的混合召回

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
   pip install -r requirements.txt
   # Windows 推荐：
   python main.py
   # 或
   uvicorn main:app --host 0.0.0.0 --port 8000
   ```

4. 启动前端：

   ```bash
   cd frontend
   npm install
   npm run dev
   ```

5. 访问前端（默认）：

   - `http://localhost:5173/`

---

## 🗺 Roadmap / TODO

- [x] 对话历史持久化
- [x] 基于 Milvus + Postgres 的长期记忆
- [x] 聊天下的 Quick Parse 文件上传与解析
- [ ] 完整的知识库 RAG 工作流（上传 / 分片 / 索引 / 检索）
- [ ] 用户认证与多用户隔离
- [ ] 使用统计与配额（请求次数 / Token 用量）
- [ ] 更多文件类型解析与 MinerU 等专业解析器接入

如果你喜欢「把好玩的基础设施都拉起来、然后在浏览器里玩 AI」的感觉，  
这个项目大概会让你挺开心的。😉
