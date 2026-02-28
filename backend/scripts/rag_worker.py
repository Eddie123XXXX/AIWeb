#!/usr/bin/env python
"""
RAG 文档解析 Worker

用法:
  cd backend && python -m scripts.rag_worker

需先启动 Redis，并设置 RAG_USE_QUEUE=true 使 API 将任务入队。
"""
import os
import sys

# 确保 backend 根目录在 path 中
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 加载 .env
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from redis import Redis
from rq import Worker, Queue, Connection

from rag.tasks import QUEUE_NAME, _get_redis_url


def main():
    redis_url = _get_redis_url()
    conn = Redis.from_url(redis_url)
    queue = Queue(QUEUE_NAME, connection=conn)

    print(f"[RAG Worker] 监听队列: {QUEUE_NAME} (Ctrl+C 退出)")
    with Connection(conn):
        worker = Worker([queue])
        worker.work()


if __name__ == "__main__":
    main()
