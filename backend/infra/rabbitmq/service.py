"""
RabbitMQ 服务封装（aio-pika）
"""
import os
from typing import Optional

import aio_pika


def _get_url() -> str:
    host = os.getenv("RABBITMQ_HOST", "localhost")
    port = os.getenv("RABBITMQ_PORT", "5672")
    user = os.getenv("RABBITMQ_USER", "guest")
    password = os.getenv("RABBITMQ_PASSWORD", "guest")
    vhost = os.getenv("RABBITMQ_VHOST", "/")
    return f"amqp://{user}:{password}@{host}:{port}/{vhost.lstrip('/')}"


async def publish(
    queue_name: str,
    message: str,
) -> None:
    """
    向指定队列发送一条消息（简单直连队列）。
    """
    url = _get_url()
    connection = await aio_pika.connect_robust(url)
    try:
        channel = await connection.channel()
        queue = await channel.declare_queue(queue_name, durable=True)
        await channel.default_exchange.publish(
            aio_pika.Message(body=message.encode("utf-8")),
            routing_key=queue.name,
        )
    finally:
        await connection.close()


async def get_one(
    queue_name: str,
    auto_ack: bool = True,
) -> Optional[str]:
    """
    从队列中取出一条消息（若无则返回 None）。
    """
    url = _get_url()
    connection = await aio_pika.connect_robust(url)
    try:
        channel = await connection.channel()
        queue = await channel.declare_queue(queue_name, durable=True)
        message = await queue.get(no_ack=auto_ack, fail=False)
        if message is None:
            return None
        body = message.body.decode("utf-8")
        if not auto_ack:
            await message.ack()
        return body
    finally:
        await connection.close()


async def ping() -> bool:
    """
    简单健康检查：能否建立连接并声明一个测试队列。
    """
    url = _get_url()
    connection = await aio_pika.connect_robust(url)
    try:
        channel = await connection.channel()
        await channel.declare_queue("aiweb_ping", durable=False)
        return True
    finally:
        await connection.close()

