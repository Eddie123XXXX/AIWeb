"""
对话功能数据流测试脚本。

验证当前数据流：
1. 意图路由：get_intent_domains 按 6 大领域分类（general_chat / user_preferences / professional_and_academic / lifestyle_and_interests / social_and_relationships / tasks_and_schedules）
2. 召回长期记忆 → 按 domain 过滤 → 拼入 system prompt
3. 上下文读取：Redis 热记忆 / DB 回源
4. 对话落库：DB + Redis 双写
5. 长期记忆异步写入（不阻塞）

运行方式（在 backend 目录下）：

    cd backend
    python -m test_chat_flow

前置：PostgreSQL、Redis、Milvus 已启动；.env 已配置；至少有一个模型配置（如 qwen-default）。
"""

import asyncio
from uuid import uuid4

from dotenv import load_dotenv

from db.user_repository import user_repository, hash_password
from db.conversation_repository import conversation_repository
from db.message_repository import message_repository
from db.agent_memory_repository import agent_memory_repository
from services.chat_context import (
    get_context,
    get_memory_context_for_prompt,
    persist_round,
)
from memory import extract_and_store_memories_for_round, get_intent_domains
from routers.models import get_model_config_by_id


async def main() -> None:
    load_dotenv()

    print("=" * 60)
    print("对话功能数据流测试（含领域路由）")
    print("=" * 60)

    # -------------------------------------------------------------------------
    print("\n【1】创建测试用户与会话")
    print("-" * 40)
    email = f"chat_flow_test_{uuid4().hex[:8]}@example.com"
    user = await user_repository.create(
        email=email,
        password_hash=hash_password("test_chat_123456"),
        username="chat-flow-test",
    )
    user_id = user["id"]
    conversation_id = str(uuid4())
    await conversation_repository.create(
        conversation_id=conversation_id,
        user_id=user_id,
        title="数据流测试",
        model_provider="qwen",
    )
    print(f"用户: id={user_id}, email={email}")
    print(f"会话: id={conversation_id}")

    # -------------------------------------------------------------------------
    print("\n【2】意图路由：验证 get_intent_domains（6 大领域）")
    print("-" * 40)
    for q in ["我最近在做什么项目？", "明天下午3点有什么安排？", "今天天气怎么样"]:
        domains = await get_intent_domains(q)
        print(f"  查询: {q[:30]}...")
        print(f"  路由: {domains}")

    # -------------------------------------------------------------------------
    print("\n【3】预写入长期记忆（professional_and_academic 领域）")
    print("-" * 40)
    await extract_and_store_memories_for_round(
        user_id=user_id,
        conversation_id=conversation_id,
        user_content="我最近在做一个 Python 项目，用的是 FastAPI 框架，打算做 API 网关。",
        assistant_content="已记录：您正在用 FastAPI 做 Python 项目，目标是 API 网关。",
    )
    print("已写入预置记忆（若 LLM 未命中高分则可能为空）")

    # -------------------------------------------------------------------------
    print("\n【4】persist_round：模拟一轮对话落库")
    print("-" * 40)
    user_content = "我最近在做什么项目？"
    assistant_content = "根据记录，您正在用 FastAPI 做 Python 项目，目标是 API 网关。"
    await persist_round(
        conversation_id=conversation_id,
        user_content=user_content,
        assistant_content=assistant_content,
        model_id="default",
    )
    print(f"User: {user_content[:50]}...")
    print(f"Assistant: {assistant_content[:50]}...")
    print("已落库 DB + Redis")

    # -------------------------------------------------------------------------
    print("\n【5】get_context：验证上下文读取")
    print("-" * 40)
    context = await get_context(conversation_id)
    print(f"上下文条数: {len(context)}")
    for i, m in enumerate(context[:4], 1):
        role = m.get("role", "?")
        content = (m.get("content", "") or "")[:40]
        print(f"  [{i}] {role}: {content}...")

    # -------------------------------------------------------------------------
    print("\n【6】get_memory_context_for_prompt：验证召回（按 domain 过滤）")
    print("-" * 40)
    memory_block = await get_memory_context_for_prompt(
        user_id=user_id,
        conversation_id=conversation_id,
        query="我最近在做什么项目？",
    )
    if memory_block:
        print(f"召回记忆: {memory_block[:80]}...")
    else:
        print("无召回记忆（可能预置记忆未写入或查询不匹配）")

    # -------------------------------------------------------------------------
    print("\n【7】general_chat 不召回：验证闲聊场景不检索记忆")
    print("-" * 40)
    memory_block_chat = await get_memory_context_for_prompt(
        user_id=user_id,
        conversation_id=conversation_id,
        query="今天天气怎么样？",
    )
    print(f"闲聊查询召回: {'有' if memory_block_chat else '无（符合预期）'}")

    # -------------------------------------------------------------------------
    print("\n【8】等待异步记忆写入完成（约 3 秒）")
    print("-" * 40)
    await asyncio.sleep(3)
    for_retention = await agent_memory_repository.list_by_user_for_retention(user_id)
    print(f"当前长期记忆条数: {len(for_retention)}")
    for m in for_retention[:3]:
        domain = m.get("domain", "?")
        print(f"  - {domain}: {str(m.get('content', ''))[:50]}...")

    # -------------------------------------------------------------------------
    print("\n【9】验证完整数据流（可选：调用真实 LLM）")
    print("-" * 40)
    model_id = None
    for mid in ("default", "qwen-default", "deepseek-default"):
        try:
            model_id = mid
            config = get_model_config_by_id(mid)
            break
        except Exception:
            continue
    if not model_id:
        print("跳过 LLM 调用（无可用模型配置）")
    else:
        from models import ChatRequest, Message, Role
        from services.llm_service import LLMService
        from routers.chat import _resolve_conversation_and_messages

        req = ChatRequest(
            model_id=model_id,
            messages=[Message(role=Role.USER, content="我最近在做什么项目？")],
            stream=False,
            conversation_id=conversation_id,
        )
        conv_id, messages = await _resolve_conversation_and_messages(req)
        print(f"拼装后的 messages 条数: {len(messages)}")
        system_msg = next((m for m in messages if m.role == Role.SYSTEM), None)
        if system_msg and "【长期记忆】" in system_msg.content:
            print("  ✓ system 包含【长期记忆】块")
        else:
            print("  - system 无【长期记忆】或为空")

        llm = LLMService(config)
        reply = await llm.chat(messages, temperature=0.5, max_tokens=100)
        print(f"LLM 回复: {reply[:60]}...")

        # 持久化本轮
        await persist_round(
            conversation_id=conversation_id,
            user_content=req.messages[-1].content,
            assistant_content=reply,
            model_id=model_id,
        )
        print("已 persist_round")

    # -------------------------------------------------------------------------
    print("\n【10】验证消息已落库")
    print("-" * 40)
    count = await message_repository.count_by_conversation(conversation_id)
    print(f"会话消息总数: {count}")

    print("\n" + "=" * 60)
    print("数据流测试完成")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
