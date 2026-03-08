"""
聊天上下文服务：读取路径（Redis 热记忆 + 未命中回源 DB）、写入路径（双写 DB + Redis 并滑动窗口截断）。
首轮对话结束后异步调用 LLM 生成会话标题并更新。
记忆模块：对话结束后异步写入长期记忆；拼 prompt 前召回相关记忆注入 system。
"""
import asyncio
import json
import logging
from typing import Any

from db.conversation_repository import conversation_repository
from db.message_repository import message_repository
from infra.redis import service as redis_service
from memory import (
    compress_memories,
    extract_and_store_memories_for_round,
    retrieve_relevant_memories,
)
from memory.router import get_intent_domains

logger = logging.getLogger(__name__)
TITLE_MAX_CHARS = 28  # 侧栏显示用，约 20 字内

CHAT_CONTEXT_KEY_PREFIX = "chat:context:"
CONTEXT_TTL_SECONDS = 86400  # 24 小时
CONTEXT_WINDOW_SIZE = 20  # 保留最近 20 条消息

# Agentic 实时推理 trace 在 Redis 中的 key 前缀
AGENTIC_TRACE_KEY_PREFIX = "agentic:trace:"
# 普通 Chat 流式输出中间状态
CHAT_STREAM_KEY_PREFIX = "chat:stream:"


def _context_key(conversation_id: str) -> str:
    return f"{CHAT_CONTEXT_KEY_PREFIX}{conversation_id}"


def _agentic_trace_key(conversation_id: str) -> str:
    return f"{AGENTIC_TRACE_KEY_PREFIX}{conversation_id}"


def _chat_stream_key(conversation_id: str) -> str:
    return f"{CHAT_STREAM_KEY_PREFIX}{conversation_id}"


async def set_chat_stream_state(
    conversation_id: str,
    user_content: str,
    assistant_content: str,
    status: str = "streaming",
    ttl: int = CONTEXT_TTL_SECONDS,
) -> None:
    """
    将普通 Chat 流式输出的中间状态写入 Redis，便于刷新后恢复。
    status: 'streaming' | 'done'
    """
    if not conversation_id:
        return
    key = _chat_stream_key(conversation_id)
    try:
        if status == "done":
            await redis_service.delete_key(key)
            return
        payload = json.dumps(
            {"user_content": user_content, "assistant_content": assistant_content, "status": status},
            ensure_ascii=False,
        )
        await redis_service.set_key(key, payload, ttl_seconds=ttl)
    except Exception as e:
        logger.warning("写入 Chat 流式状态失败（忽略）: %s", e)


async def get_chat_stream_state(conversation_id: str) -> dict[str, Any] | None:
    """
    读取某会话当前进行中的 Chat 流式状态。
    """
    if not conversation_id:
        return None
    key = _chat_stream_key(conversation_id)
    try:
        raw = await redis_service.get_key(key)
    except Exception as e:
        logger.warning("读取 Chat 流式状态失败（忽略）: %s", e)
        return None
    if not raw:
        return None
    try:
        obj = json.loads(raw)
        if isinstance(obj, dict):
            return obj
    except Exception:
        return None
    return None


def _fallback_title_from_user_content(user_content: str) -> str:
    """基于用户首轮问题的本地兜底标题，避免长期停留“新对话”."""
    text = (user_content or "").strip().replace("\n", " ")
    if not text:
        return "新对话"
    return text[:TITLE_MAX_CHARS]


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


async def set_agentic_trace(
    conversation_id: str,
    trace: dict[str, Any] | None,
    ttl: int = CONTEXT_TTL_SECONDS,
) -> None:
    """
    将 Agentic 当前轮的推理 trace 实时写入 Redis。

    语义：
    - trace 为 None：删除 key，表示当前无进行中的 Agentic 轮次；
    - 否则写入 JSON（version/status/events/user_query 等），并设置 TTL。
    """
    if not conversation_id:
        return
    key = _agentic_trace_key(conversation_id)
    try:
        if trace is None:
            await redis_service.delete_key(key)
            return
        payload = json.dumps(trace, ensure_ascii=False)
        await redis_service.set_key(key, payload, ttl_seconds=ttl)
    except Exception as e:
        logger.warning("写入 Agentic 实时 trace 失败（忽略，不影响主流程）: %s", e)


async def get_agentic_trace(conversation_id: str) -> dict[str, Any] | None:
    """
    读取某会话当前进行中的 Agentic 推理 trace。

    - 若 key 不存在或解析失败，返回 None；
    - 若存在，则返回形如 {version, status, events} 的字典。
    """
    if not conversation_id:
        return None
    key = _agentic_trace_key(conversation_id)
    try:
        raw = await redis_service.get_key(key)
    except Exception as e:
        logger.warning("读取 Agentic 实时 trace 失败（忽略，不影响主流程）: %s", e)
        return None
    if not raw:
        return None
    try:
        obj = json.loads(raw)
        if isinstance(obj, dict):
            return obj
    except Exception:
        return None
    return None


async def get_memory_context_for_prompt(
    user_id: int,
    conversation_id: str,
    query: str,
    *,
    top_k_final: int = 5,
    compress_threshold: int = 5,
    max_chars: int = 500,
) -> str:
    """
    召回与当前查询相关的长期记忆，用于拼入 system prompt。
    若召回条数 > compress_threshold，则压缩为摘要以节省 token。
    失败时返回空字符串，不阻塞聊天。
    """
    if not query or not query.strip():
        return ""
    # 1. 意图路由：判断目标领域
    target_domains = await get_intent_domains(query.strip())
    # 2. 纯闲聊不检索记忆
    if target_domains == ["general_chat"] or not target_domains:
        return ""

    logging.getLogger("memory").info(
        "[Memory] 聊天拼 prompt 召回记忆 get_memory_context_for_prompt | user_id=%s conv=%s domains=%s",
        user_id,
        conversation_id[:8] if conversation_id else "-",
        target_domains,
    )
    try:
        memories = await retrieve_relevant_memories(
            user_id=user_id,
            query=query.strip(),
            conversation_id=conversation_id,
            target_domains=target_domains,
            top_k_final=top_k_final,
        )
        if not memories:
            return ""
        if len(memories) > compress_threshold:
            return await compress_memories(memories, max_chars=max_chars)
        return "\n".join(m.get("content", "").strip() for m in memories if m.get("content"))
    except Exception as e:
        logger.warning("召回长期记忆失败（忽略，不影响聊天）: %s", e)
        return ""


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
    # 标题生成：只要当前还是默认标题，就按对话内容异步生成标题（不阻塞响应）
    # 这样可兼容 agentic 场景下可能出现的“首轮计数不严格等于 2”的边界情况。
    try:
        conv_for_title = await conversation_repository.get_by_id(conversation_id)
        current_title = (conv_for_title or {}).get("title") or ""
        if current_title in {"新对话", "New conversation"}:
            # 先同步用用户问题做一个兜底标题，避免前端长时间显示“新对话”
            fallback_title = _fallback_title_from_user_content(user_content)
            if fallback_title and fallback_title not in {"新对话", "New conversation"}:
                await conversation_repository.update(conversation_id, title=fallback_title)
            asyncio.create_task(_generate_and_set_title(conversation_id, model_id or "default"))
    except Exception as e:
        logger.warning("触发会话标题生成失败（忽略，不影响主流程）: %s", e)

    # 异步写入长期记忆（不阻塞前端，后台执行）
    try:
        conv = await conversation_repository.get_by_id(conversation_id)
        if conv and conv.get("user_id"):
            user_id = int(conv["user_id"])
            logging.getLogger("memory").info(
                "[Memory] 聊天对话结束后异步写入长期记忆 | user_id=%s conv=%s",
                user_id,
                conversation_id[:8] if conversation_id else "-",
            )
            asyncio.create_task(
                extract_and_store_memories_for_round(
                    user_id=user_id,
                    conversation_id=conversation_id,
                    user_content=user_content,
                    assistant_content=assistant_content,
                )
            )
    except Exception as e:
        logger.warning("写入长期记忆失败（忽略错误，不影响主流程）: %s", e)
