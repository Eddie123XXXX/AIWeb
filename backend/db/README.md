# AIWeb DB Layer 🧱

## 快速导航

- 建表入口：`python -m db.run_schema`
- 表结构：users / conversations / messages / research_sessions / agent_memories / documents / document_chunks
- 迁移策略：新库以 `schema_*.sql` 为准，兼容旧库的补列脚本已收敛
- 数据访问：各 `*_repository.py`

数据库主要负责用户、会话、消息以及 Agent 记忆等结构化信息的持久化，是 AIWeb 的「记事本 + 索引库」。📒

### DB 层架构图

```mermaid
flowchart TB
    subgraph 建表["建表 run_schema"]
        Schema[schema_*.sql 按序执行]
    end

    subgraph 表["核心表"]
        Users[users\nuser_profiles\nuser_oauths]
        Conv[conversations\nmessages]
        Research[research_sessions]
        Mem[agent_memories]
        NB[notebooks\ndocuments\ndocument_chunks]
    end

    subgraph 访问["Repository / 业务"]
        Auth[auth/]
        UserR[routers/user]
        ChatR[chat / chat_context]
        DeepR[deepresearch]
        MemS[memory/service]
        RAG[rag/]
    end

    Schema --> Users
    Schema --> Conv
    Schema --> Research
    Schema --> Mem
    Schema --> NB
    Auth --> Users
    UserR --> Users
    ChatR --> Conv
    DeepR --> Research
    MemS --> Mem
    RAG --> NB
```

## 🔄 实现流程

- **建表**：在 `backend` 目录执行 `python -m db.run_schema`，脚本按依赖顺序执行各 `schema_*.sql`（users → user_profiles → user_oauths → conversations → messages → research_sessions → agent_memories → notebooks → documents → document_chunks）。环境变量使用 `POSTGRES_*`，与 infra 一致。
- **使用**：各业务模块通过 `*_repository`（asyncpg）访问对应表。当前主 schema 已直接包含 `research_sessions.sources`、`research_sessions.ui_state`、`notebooks.emoji`、`documents.summary` 等当前运行所需字段，新库初始化不需要额外补列。
- **升级旧库**：如果你不是新装，而是在已有数据库上升级，请先备份，再对照最新 `schema_*.sql` 手动检查缺失列；仓库不再保留所有历史兼容脚本。

## 📑 表与建表顺序

1. **users**：`schema_users.sql`（核心用户账号表）
2. **user_profiles**：`schema_user_profiles.sql`（用户资料扩展表，依赖 users）
3. **user_oauths**：`schema_user_oauths.sql`（第三方授权登录表，依赖 users）
4. **conversations**：`schema_conversations.sql`（AI 会话/聊天室表，依赖 users）
5. **messages**：`schema_messages.sql`（AI 对话消息明细表，依赖 conversations）
6. **research_sessions**：`schema_research_sessions.sql`（深度研究会话表，与 conversations 分离，依赖 users）
7. **agent_memories**：`schema_agent_memories.sql`（Agent 长期记忆与反思表，依赖 users、conversations）
8. **notebooks**：`schema_notebooks.sql`（RAG 笔记本表，含 `emoji` 列，依赖 users）
9. **documents**：`schema_documents.sql`（RAG 文档元数据表，含 `summary` 列，防重+状态机+版本追踪，依赖 users、notebooks）
10. **document_chunks**：`schema_document_chunks.sql`（RAG 文档切片表，Parent-Child+多模态，依赖 documents）

执行方式（任选其一）：⚙️

**方式一：有 psql 时（Linux/Mac 或已安装 PostgreSQL 客户端）** 🐘

```bash
psql "postgresql://aiweb:aiweb@localhost:5432/aiweb" -f db/schema_users.sql
psql "postgresql://aiweb:aiweb@localhost:5432/aiweb" -f db/schema_user_profiles.sql
psql "postgresql://aiweb:aiweb@localhost:5432/aiweb" -f db/schema_user_oauths.sql
psql "postgresql://aiweb:aiweb@localhost:5432/aiweb" -f db/schema_conversations.sql
psql "postgresql://aiweb:aiweb@localhost:5432/aiweb" -f db/schema_messages.sql
psql "postgresql://aiweb:aiweb@localhost:5432/aiweb" -f db/schema_research_sessions.sql
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

## 🧩 当前库与业务模块的对应关系

| 表 / 表系 | 主要被谁使用 | 说明 |
|-----------|--------------|------|
| `users` / `user_profiles` / `user_oauths` | `auth/`、`routers/user.py` | 登录、注册、资料展示、第三方登录扩展 |
| `conversations` / `messages` | `routers/chat.py`、`services/chat_context.py` | 普通聊天、Agentic 聊天、历史恢复 |
| `research_sessions` | `agentic/deepresearch/`、`research_session_repository.py` | DeepResearch 独立会话、章节、来源、面板状态恢复 |
| `agent_memories` | `memory/service.py` | 长期记忆、反思、遗忘、人工管理 |
| `notebooks` / `documents` / `document_chunks` | `rag/` | 知识库上传、解析、切块、向量化、检索、来源指南 |

总之，这个目录解决的是「表从哪儿来」「如何一键建好」的问题，  
让你可以把注意力放在 AI 行为本身，而不是 DDL 细节上。😉
