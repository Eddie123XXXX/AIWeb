"""
在未安装 psql 时，用 Python + asyncpg 执行建表脚本。
用法（在 backend 目录下）:
  python -m db.run_schema
  # 或指定 .env 后: set DOTENV=... && python -m db.run_schema
"""
import asyncio
import os
import sys

# 确保 backend 在 path 上并加载 .env
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv

load_dotenv()

import asyncpg


def get_dsn() -> str:
    host = os.getenv("POSTGRES_HOST", "localhost")
    port = os.getenv("POSTGRES_PORT", "5432")
    user = os.getenv("POSTGRES_USER", "aiweb")
    password = os.getenv("POSTGRES_PASSWORD", "aiweb")
    database = os.getenv("POSTGRES_DB", "aiweb")
    return f"postgresql://{user}:{password}@{host}:{port}/{database}"


async def run_file(conn: asyncpg.Connection, filepath: str) -> None:
    with open(filepath, "r", encoding="utf-8") as f:
        sql = f.read()
    # 去掉注释行和空行，按分号拆成多条执行（简单处理；COMMENT 等单独一句）
    statements = []
    current = []
    for line in sql.splitlines():
        line = line.strip()
        if not line or line.startswith("--"):
            continue
        current.append(line)
        if line.endswith(";"):
            st = " ".join(current).strip()
            if st:
                statements.append(st)
            current = []
    if current:
        st = " ".join(current).strip()
        if st:
            statements.append(st)
    for i, st in enumerate(statements):
        try:
            await conn.execute(st)
        except Exception as e:
            raise RuntimeError(f"执行第 {i+1} 条语句失败: {e}\n语句: {st[:200]}...") from e


async def main() -> None:
    host = os.getenv("POSTGRES_HOST", "localhost")
    port = os.getenv("POSTGRES_PORT", "5432")
    database = os.getenv("POSTGRES_DB", "aiweb")
    user = os.getenv("POSTGRES_USER", "aiweb")
    print(f"连接: {host}:{port}/{database} (用户: {user})")
    dsn = get_dsn()
    schema_dir = os.path.dirname(os.path.abspath(__file__))
    files = [
        os.path.join(schema_dir, "schema_users.sql"),
        os.path.join(schema_dir, "schema_user_profiles.sql"),
        os.path.join(schema_dir, "schema_user_oauths.sql"),
        os.path.join(schema_dir, "schema_conversations.sql"),
        os.path.join(schema_dir, "schema_messages.sql"),
        os.path.join(schema_dir, "schema_agent_memories.sql"),
    ]
    try:
        conn = await asyncpg.connect(dsn)
    except Exception as e:
        print(f"连接数据库失败: {e}")
        print("请确认: 1) Postgres 已启动  2) .env 中 POSTGRES_* 正确")
        sys.exit(1)
    try:
        for path in files:
            if not os.path.isfile(path):
                print(f"跳过（文件不存在）: {path}")
                continue
            print(f"执行: {os.path.basename(path)}")
            await run_file(conn, path)
        # 验证：列出 public 下的表
        rows = await conn.fetch(
            "SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY tablename"
        )
        tables = [r["tablename"] for r in rows]
        print(f"建表完成。当前数据库 [{database}] public 下表: {tables}")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
