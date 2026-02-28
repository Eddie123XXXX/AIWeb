"""
一键清空当前系统下的 RAG 数据。

⚠️ 高危操作，仅用于本地开发/测试环境：
- 删除 PostgreSQL 中所有 RAG 文档与切片 (documents / document_chunks / notebooks)
- 删除 MinIO 中 rag/ 前缀下的所有对象
- 删除 Milvus 中 RAG 向量 collection (enterprise_rag_knowledge)

使用方式:
    cd backend
    python -m rag.clear_rag_data
"""
from __future__ import annotations

import asyncio
import logging
import os
from typing import Any

import asyncpg

from infra.minio import service as minio_service
from . import vector_store

logger = logging.getLogger("rag.clear")
logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")


def _get_pg_dsn() -> str:
    host = os.getenv("POSTGRES_HOST", "localhost")
    port = os.getenv("POSTGRES_PORT", "5432")
    user = os.getenv("POSTGRES_USER", "aiweb")
    password = os.getenv("POSTGRES_PASSWORD", "aiweb")
    database = os.getenv("POSTGRES_DB", "aiweb")
    return f"postgresql://{user}:{password}@{host}:{port}/{database}"


async def _clear_postgres() -> None:
    """
    清空 RAG 相关的 PostgreSQL 表:
    - document_chunks
    - documents
    - notebooks
    """
    dsn = _get_pg_dsn()
    logger.info(f"[RAG] 连接 PostgreSQL: {dsn}")
    conn: asyncpg.Connection
    conn = await asyncpg.connect(dsn)
    try:
        async with conn.transaction():
            # 先清空切片，再清空文档和笔记本
            logger.info("[RAG] 删除 document_chunks 表数据...")
            await conn.execute("DELETE FROM document_chunks;")

            logger.info("[RAG] 删除 documents 表数据...")
            await conn.execute("DELETE FROM documents;")

            logger.info("[RAG] 删除 notebooks 表数据...")
            await conn.execute("DELETE FROM notebooks;")
        logger.info("[RAG] PostgreSQL RAG 数据已清空")
    finally:
        await conn.close()


def _clear_minio() -> None:
    """
    删除 MinIO 中所有 RAG 相关对象:
    - 前缀 rag/ 下的对象 (上传的原始文档)
    """
    try:
        objects = minio_service.list_objects(prefix="rag/")
    except Exception as e:
        logger.warning(f"[RAG] 列出 MinIO 对象失败 (已跳过): {e}")
        return

    if not objects:
        logger.info("[RAG] MinIO 中无 rag/ 前缀对象，无需删除")
        return

    logger.info(f"[RAG] 即将删除 MinIO 中 {len(objects)} 个 rag/ 对象...")
    deleted = 0
    for obj in objects:
        name = obj.get("name")
        if not name:
            continue
        try:
            minio_service.delete_object(name)
            deleted += 1
        except Exception as e:
            logger.warning(f"[RAG] 删除 MinIO 对象失败 ({name}): {e}")
    logger.info(f"[RAG] MinIO 已删除 rag/ 对象: {deleted} 个")


def _clear_milvus() -> None:
    """
    删除 Milvus 中的 RAG 向量 collection:
    - enterprise_rag_knowledge (由 vector_store.COLLECTION_NAME 定义)

    下次写入时会自动重建 collection 与索引。
    """
    from pymilvus import connections, utility, MilvusException

    params: dict[str, Any] = {
        "host": os.getenv("MILVUS_HOST", "localhost"),
        "port": os.getenv("MILVUS_PORT", "19530"),
    }

    coll_name = vector_store.COLLECTION_NAME
    try:
        logger.info(f"[RAG] 连接 Milvus: {params['host']}:{params['port']}")
        connections.connect("default", **params)
        if utility.has_collection(coll_name):
            logger.info(f"[RAG] 删除 Milvus collection '{coll_name}'...")
            utility.drop_collection(coll_name)
            logger.info(f"[RAG] Milvus collection '{coll_name}' 已删除")
        else:
            logger.info(f"[RAG] Milvus collection '{coll_name}' 不存在，无需删除")
    except MilvusException as e:
        logger.warning(f"[RAG] Milvus 清理失败 (已跳过): {e}")
    except Exception as e:
        logger.warning(f"[RAG] 连接/操作 Milvus 失败 (已跳过): {e}")


async def main() -> None:
    confirm = os.getenv("RAG_CLEAR_CONFIRM", "").strip().lower()
    if confirm not in ("yes", "true", "i_know_what_i_am_doing"):
        logger.warning(
            "⚠️ 将要清空当前环境下所有 RAG 数据 (PostgreSQL + Milvus + MinIO)。\n"
            "若确认要执行，请在环境变量中设置 RAG_CLEAR_CONFIRM=yes 后再运行:\n"
            "    RAG_CLEAR_CONFIRM=yes python -m rag.clear_rag_data"
        )
        return

    logger.info("====== 开始清空 RAG 数据 (PostgreSQL + Milvus + MinIO) ======")
    await _clear_postgres()
    _clear_milvus()
    _clear_minio()
    logger.info("====== RAG 数据清理完成 ======")


if __name__ == "__main__":
    asyncio.run(main())

