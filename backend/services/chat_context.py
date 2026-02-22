"""
聊天上下文服务：读取路径（Redis 热记忆 + 未命中回源 DB）、写入路径（双写 DB + Redis 并滑动窗口截断）。
首轮对话结束后异步调用 LLM 生成会话标题并更新。
"""
import asyncio
import json
import logging
from typing import Any

from db.conversation_repository import conversation_repository
from db.message_repository import message_repository
from infra.redis import service as redis_service

logger = logging.getLogger(__name__)
TITLE_MAX_CHARS = 28  # 侧栏显示用，约 20 字内

CHAT_CONTEXT_KEY_PREFIX = "chat:context:"
CONTEXT_TTL_SECONDS = 86400  # 24 小时
CONTEXT_WINDOW_SIZE = 20  # 保留最近 20 条消息


def _context_key(conversation_id: str) -> str:
    return f"{CHAT_CONTEXT_KEY_PREFIX}{conversation_id}"


def _message_to_json_item(msg: dict[str, Any]) -> str:
    """将单条消息转为存入 Redis 的 JSON 字符串（仅 role + content，用于拼 prompt）。"""
    return json.dumps(
        {"role": msg["role"], "content": msg["content"]},
        ensure_ascii=False,
    )


async def get_context(conversation_id: str, limit: int = CONTEXT_WINDOW_SIZE) -> list[dict[str, Any]]:
    """
    读取路径：先查 Redis，命中则返回；未命中则从 DB 取最近 limit 条，写回 Redis 并设置过期，再返回。
    返回 list[{"role": str, "content": str}]，按时间升序，可直接拼进大模型 messages。
    """
    key = _context_key(conversation_id)
    try:
        raw_list = await redis_service.lrange(key, 0, -1)
    except Exception:
        raw_list = []

    if raw_list:
        # 缓存命中
        out = []
        for s in raw_list:
            try:
                obj = json.loads(s)
                out.append({"role": obj.get("role", "user"), "content": obj.get("content", "")})
            except (json.JSONDecodeError, TypeError):
                continue
        return out

    # 缓存未命中：从 DB 取最近 limit 条
    rows = await message_repository.get_latest_n(conversation_id, limit)
    out = [{"role": r["role"], "content": r["content"]} for r in rows]

    # 写回 Redis，预热缓存
    if out:
        try:
            for m in out:
                await redis_service.rpush(key, _message_to_json_item(m))
            await redis_service.expire(key, CONTEXT_TTL_SECONDS)
        except Exception:
            pass

    return out


async def append_messages_and_trim(
    conversation_id: str,
    new_messages: list[dict[str, Any]],
    ttl: int = CONTEXT_TTL_SECONDS,
    max_len: int = CONTEXT_WINDOW_SIZE,
) -> None:
    """
    写入路径（在 DB 已写入之后调用）：将新消息追加到 Redis 列表，再 LTRIM 保留最近 max_len 条，并刷新过期时间。
    new_messages: list[{"role": str, "content": str, ...}]
    """
    if not new_messages:
        return
    key = _context_key(conversation_id)
    try:
        for m in new_messages:
            await redis_service.rpush(key, _message_to_json_item(m))
        # 保留最近 max_len 条：LTRIM key -max_len -1
        await redis_service.ltrim(key, -max_len, -1)
        await redis_service.expire(key, ttl)
    except Exception:
        pass


async def _generate_and_set_title(conversation_id: str, model_id: str = "default") -> None:
    """
    根据首轮对话内容调用 LLM 生成简短标题并更新会话。不阻塞、不抛错。
    """
    try:
        from routers.models import get_model_config_by_id
        from services.llm_service import LLMService
        from models import Message, Role

        config = get_model_config_by_id(model_id)
    except Exception as e:
        logger.debug("生成标题跳过（无可用模型或配置）: %s", e)
        return

    try:
        messages = await message_repository.get_latest_n(conversation_id, 2)
        if len(messages) < 2:
            return
        user_content = next((m["content"] for m in messages if m["role"] == "user"), "") or ""
        assistant_content = next((m["content"] for m in messages if m["role"] == "assistant"), "") or ""
        if not user_content.strip():
            return

        prompt = (
            "请用一句话总结以下对话作为标题，仅返回标题文本，不要引号、不要解释，不超过20个字。\n"
            "用户：" + (user_content[:500] if len(user_content) > 500 else user_content) + "\n"
            "助手：" + (assistant_content[:300] if len(assistant_content) > 300 else assistant_content)
        )
        llm = LLMService(config)
        title = await llm.chat(
            [Message(role=Role.USER, content=prompt)],
            temperature=0.3,
            max_tokens=80,
        )
        if title:
            title = title.strip().strip('"\'').replace("\n", " ")[:TITLE_MAX_CHARS]
            if title:
                await conversation_repository.update(conversation_id, title=title)
                logger.info("会话标题已更新: %s -> %s", conversation_id[:8], title)
    except Exception as e:
        logger.warning("生成会话标题失败: %s", e)


async def persist_round(
    conversation_id: str,
    user_content: str,
    assistant_content: str,
    assistant_metadata: dict | None = None,
    model_id: str | None = None,
) -> None:
    """
    写路径：先落库（插入 user 与 assistant 两条消息，并刷新会话 updated_at），再更新 Redis 热记忆并截断。
    若为本会话首轮对话（仅 2 条消息），则异步调用 LLM 生成标题并更新。
    """
    await message_repository.create(conversation_id, "user", user_content)
    await message_repository.create(
        conversation_id,
        "assistant",
        assistant_content,
        metadata=assistant_metadata,
    )
    await conversation_repository.touch(conversation_id)
    await append_messages_and_trim(
        conversation_id,
        [
            {"role": "user", "content": user_content},
            {"role": "assistant", "content": assistant_content},
        ],
    )
    # 首轮对话后异步生成标题，不阻塞响应
    n = await message_repository.count_by_conversation(conversation_id)
    if n == 2:
        asyncio.create_task(_generate_and_set_title(conversation_id, model_id or "default"))
