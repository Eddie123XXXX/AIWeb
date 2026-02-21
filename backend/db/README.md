# 数据库层

    ## 表与建表顺序

1. **users**：`schema_users.sql`（核心用户账号表）
2. **user_profiles**：`schema_user_profiles.sql`（用户资料扩展表，依赖 users）
3. **user_oauths**：`schema_user_oauths.sql`（第三方授权登录表，依赖 users）

执行方式（任选其一）：

**方式一：有 psql 时（Linux/Mac 或已安装 PostgreSQL 客户端）**

```bash
psql "postgresql://aiweb:aiweb@localhost:5432/aiweb" -f db/schema_users.sql
psql "postgresql://aiweb:aiweb@localhost:5432/aiweb" -f db/schema_user_profiles.sql
psql "postgresql://aiweb:aiweb@localhost:5432/aiweb" -f db/schema_user_oauths.sql
```

**方式二：无 psql 时（如 Windows 未装 PostgreSQL 客户端）**

在 `backend` 目录下用 Python 执行（会读取 `.env` 中的 `POSTGRES_*`）：

```bash
cd backend
python -m db.run_schema
```

环境变量与现有 Postgres 一致：`POSTGRES_HOST`、`POSTGRES_PORT`、`POSTGRES_USER`、`POSTGRES_PASSWORD`、`POSTGRES_DB`。

## 依赖

- `asyncpg`：已在 `requirements.txt`
- `passlib[bcrypt]`：已加入，用于密码哈希。安装：`pip install -r requirements.txt`
