# AIWeb DB Layer 🧱

## 快速导航

- 建表入口：`python -m db.run_schema`
- 表结构：users / conversations / messages / agent_memories / documents / document_chunks
- 迁移脚本：`rag.migrate_add_summary`、`db.migrate_notebooks_emoji`
- 数据访问：各 `*_repository.py`

数据库主要负责用户、会话、消息以及 Agent 记忆等结构化信息的持久化，是 AIWeb 的「记事本 + 索引库」。📒

## 🔄 实现流程

- **建表**：在 `backend` 目录执行 `python -m db.run_schema`，脚本按依赖顺序执行各 `schema_*.sql`（users → user_profiles → user_oauths → conversations → messages → agent_memories → documents → document_chunks）。环境变量使用 `POSTGRES_*`，与 infra 一致。
- **使用**：各业务模块通过 `*_repository`（asyncpg）访问对应表；RAG 需先跑 `python -m rag.migrate_add_summary` 为 documents 增加 summary 列。记忆管理 API（`routers/memory.py`）读写 `agent_memories` 表。笔记本 emoji 列：若表已存在且无 `emoji` 列，需执行 `python -m db.migrate_notebooks_emoji` 一次。

## 📑 表与建表顺序

1. **users**：`schema_users.sql`（核心用户账号表）
2. **user_profiles**：`schema_user_profiles.sql`（用户资料扩展表，依赖 users）
3. **user_oauths**：`schema_user_oauths.sql`（第三方授权登录表，依赖 users）
4. **conversations**：`schema_conversations.sql`（AI 会话/聊天室表，依赖 users）
5. **messages**：`schema_messages.sql`（AI 对话消息明细表，依赖 conversations）
6. **agent_memories**：`schema_agent_memories.sql`（Agent 长期记忆与反思表，依赖 users、conversations）
7. **notebooks**：`schema_notebooks.sql`（RAG 笔记本表，含 emoji 列，依赖 users）
8. **documents**：`schema_documents.sql`（RAG 文档元数据表，防重+状态机+版本追踪，依赖 users、notebooks）
9. **document_chunks**：`schema_document_chunks.sql`（RAG 文档切片表，Parent-Child+多模态，依赖 documents）

执行方式（任选其一）：⚙️

**方式一：有 psql 时（Linux/Mac 或已安装 PostgreSQL 客户端）** 🐘

```bash
psql "postgresql://aiweb:aiweb@localhost:5432/aiweb" -f db/schema_users.sql
psql "postgresql://aiweb:aiweb@localhost:5432/aiweb" -f db/schema_user_profiles.sql
psql "postgresql://aiweb:aiweb@localhost:5432/aiweb" -f db/schema_user_oauths.sql
psql "postgresql://aiweb:aiweb@localhost:5432/aiweb" -f db/schema_conversations.sql
psql "postgresql://aiweb:aiweb@localhost:5432/aiweb" -f db/schema_messages.sql
psql "postgresql://aiweb:aiweb@localhost:5432/aiweb" -f db/schema_agent_memories.sql
psql "postgresql://aiweb:aiweb@localhost:5432/aiweb" -f db/schema_notebooks.sql
psql "postgresql://aiweb:aiweb@localhost:5432/aiweb" -f db/schema_documents.sql
psql "postgresql://aiweb:aiweb@localhost:5432/aiweb" -f db/schema_document_chunks.sql
```

**方式二：无 psql 时（如 Windows 未装 PostgreSQL 客户端）** 🪟

在 `backend` 目录下用 Python 执行（会读取 `.env` 中的 `POSTGRES_*`）：

```bash
cd backend
python -m db.run_schema
```

环境变量与现有 Postgres 一致：`POSTGRES_HOST`、`POSTGRES_PORT`、`POSTGRES_USER`、`POSTGRES_PASSWORD`、`POSTGRES_DB`。

## 📦 依赖

- `asyncpg`、`bcrypt`：已在 `backend/requirements.txt`（异步 Postgres 客户端与密码哈希，用户模块直接使用 bcrypt）

总之，这个目录解决的是「表从哪儿来」「如何一键建好」的问题，  
让你可以把注意力放在 AI 行为本身，而不是 DDL 细节上。😉
