"""
RAG 异步任务队列 (Redis RQ)

长耗时解析任务 (MinerU 50 页 PDF 可能数分钟) 不再使用 FastAPI BackgroundTasks，
改为消息队列 + Worker 消费模式，支持:
- 服务重启/崩溃时任务不丢失 (持久化在 Redis)
- 重试机制 (Retry)
- 失败任务进入死信队列 (RQ failed queue)
"""
from __future__ import annotations

import asyncio
import logging
import os

logger = logging.getLogger("rag.tasks")

QUEUE_NAME = "rag_tasks"
# 失败任务自动进入 RQ 的 failed 队列，可后续人工处理或重试
MAX_RETRIES = 3
RETRY_DELAY = 60  # 秒


def _get_redis_url() -> str:
    host = os.getenv("REDIS_HOST", "localhost")
    port = os.getenv("REDIS_PORT", "6379")
    db = os.getenv("REDIS_DB", "0")
    password = os.getenv("REDIS_PASSWORD") or None
    if password:
        return f"redis://:{password}@{host}:{port}/{db}"
    return f"redis://{host}:{port}/{db}"


def process_document_task(doc_id: str) -> dict | None:
    """
    同步任务入口: 驱动文档解析流水线。

    RQ Worker 调用此函数，内部用 asyncio.run 执行异步 process_document。
    """
    from . import service

    async def _run():
        return await service.process_document(doc_id)

    try:
        return asyncio.run(_run())
    except Exception as e:
        logger.error(f"[RAG] 任务 process_document({doc_id}) 执行失败: {e}")
        raise


def enqueue_process_document(doc_id: str) -> str | None:
    """
    将文档解析任务入队，返回 job_id；失败返回 None。
    """
    try:
        from redis import Redis
        from rq import Queue, Retry
    except ImportError:
        logger.warning("[RAG] rq 未安装，无法使用任务队列。pip install rq")
        return None

    url = _get_redis_url()
    try:
        conn = Redis.from_url(url)
        queue = Queue(QUEUE_NAME, connection=conn, default_timeout=600)  # 10 分钟超时
        job = queue.enqueue(
            process_document_task,
            doc_id,
            job_timeout="30m",  # MinerU 大文档可能很慢
            retry=Retry(max=MAX_RETRIES, interval=RETRY_DELAY),
            failure_ttl=86400,  # 失败记录保留 24h
        )
        return job.id if job else None
    except Exception as e:
        logger.warning(f"[RAG] 任务入队失败: {e}")
        return None


def is_queue_available() -> bool:
    """检查 Redis + RQ 是否可用"""
    try:
        from redis import Redis
        conn = Redis.from_url(_get_redis_url())
        conn.ping()
        return True
    except Exception:
        return False
