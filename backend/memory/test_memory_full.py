"""
Memory 模块全功能测试脚本。

覆盖：写入记忆、反思、混合召回、记忆压缩、艾宾浩斯遗忘、定期清理。

运行方式（在 backend 目录下）：

    cd backend
    python -m memory.test_memory_full

前置要求：
- PostgreSQL 已建表、Milvus 已启动
- .env 中已配置 QWEN_API_KEY、DEEPSEEK_API_KEY
"""

import asyncio
from uuid import uuid4

from dotenv import load_dotenv

from db.user_repository import user_repository, hash_password
from db.conversation_repository import conversation_repository
from db.agent_memory_repository import agent_memory_repository
from memory import (
    extract_and_store_memories_for_round,
    retrieve_relevant_memories,
    compress_memories,
    cleanup_forgotten_memories,
    try_generate_reflection,
    EbbinghausForgetting,
)


async def main() -> None:
    load_dotenv()

    print("=" * 60)
    print("Memory 模块全功能测试")
    print("=" * 60)

    # -------------------------------------------------------------------------
    print("\n【1】创建测试用户与会话")
    print("-" * 40)
    email = f"memory_full_test_{uuid4().hex[:8]}@example.com"
    user = await user_repository.create(
        email=email,
        password_hash=hash_password("test_memory_123456"),
        username="memory-full-test",
    )
    user_id = user["id"]
    conversation_id = str(uuid4())
    await conversation_repository.create(
        conversation_id=conversation_id,
        user_id=user_id,
        title="Memory 全功能测试",
        model_provider="qwen",
    )
    print(f"用户: id={user_id}, email={email}")
    print(f"会话: id={conversation_id}")

    # -------------------------------------------------------------------------
    print("\n【2】记忆写入（extract_and_store_memories_for_round）")
    print("-" * 40)

    rounds = [
        (
            "我对青霉素严重过敏，请务必记住，以后推荐药物时要避开。",
            "已记录：您对青霉素严重过敏，后续推荐药物时会严格避开青霉素类。",
        ),
        (
            "我决定将整个项目从 Vue 迁移到 React，这是最终决策。",
            "已记录：您已决定将项目技术栈从 Vue 迁移到 React。",
        ),
        (
            "我偏好使用 TypeScript 而非 JavaScript，所有新项目都要求强类型。",
            "已记录：您偏好 TypeScript，新项目均要求强类型。",
        ),
    ]

    total_written = 0
    for i, (user_content, assistant_content) in enumerate(rounds, 1):
        print(f"\n--- 第 {i} 轮对话 ---")
        print(f"User: {user_content}")
        print(f"Assistant: {assistant_content}")
        memories = await extract_and_store_memories_for_round(
            user_id=user_id,
            conversation_id=conversation_id,
            user_content=user_content,
            assistant_content=assistant_content,
        )
        print(f"写入记忆条数: {len(memories)}")
        for m in memories:
            print(f"  - [{m.get('importance_score')}] {m.get('content', '')[:50]}...")
            total_written += 1

    print(f"\n合计写入: {total_written} 条")

    # -------------------------------------------------------------------------
    print("\n【2.5】反思触发（try_generate_reflection）")
    print("-" * 40)

    reflection = await try_generate_reflection(
        user_id=user_id,
        conversation_id=conversation_id,
        importance_threshold=2.0,  # 降低阈值便于测试（3 条 fact 约 2.4+）
        cooldown_hours=0,
    )
    if reflection:
        print(f"生成反思: {reflection['content'][:80]}...")
    else:
        print("未触发反思（累加 importance 未达阈值或 fact 不足 2 条）")

    # -------------------------------------------------------------------------
    print("\n【3】混合召回（retrieve_relevant_memories）")
    print("-" * 40)

    query = "我有什么药物过敏需要记住？"
    print(f"查询: {query}")

    recalled = await retrieve_relevant_memories(
        user_id=user_id,
        query=query,
        conversation_id=conversation_id,  # 限定当前会话 + 全局记忆
        top_k_semantic=20,
        top_k_final=5,
    )
    print(f"召回条数（限定 conversation_id）: {len(recalled)}")
    for idx, r in enumerate(recalled, 1):
        print(f"\n  [{idx}] final={r['final_score']:.3f} | {r['content'][:60]}...")

    # -------------------------------------------------------------------------
    print("\n【4】记忆压缩（compress_memories）")
    print("-" * 40)

    if recalled:
        summary = await compress_memories(recalled, max_chars=300)
        print(f"压缩摘要 ({len(summary)} 字):")
        print(f"  {summary}")
    else:
        print("无召回记忆，跳过压缩")

    # -------------------------------------------------------------------------
    print("\n【5】艾宾浩斯保持率（EbbinghausForgetting.calculate_retention）")
    print("-" * 40)

    for_retention = await agent_memory_repository.list_by_user_for_retention(user_id)
    ebbinghaus = EbbinghausForgetting(base_retention=0.9, strengthening_factor=1.5)

    for m in for_retention[:5]:
        r = ebbinghaus.calculate_retention(m)
        print(f"  id={m['id'][:8]}... | retention={r:.3f} | access={m['access_count']} | importance={m['importance_score']:.2f}")

    # -------------------------------------------------------------------------
    print("\n【6】遗忘清理（cleanup_forgotten_memories）")
    print("-" * 40)

    deleted = await cleanup_forgotten_memories(
        user_id=user_id,
        threshold=0.05,
        exclude_memory_types=["reflection"],
    )
    print(f"软删除条数: {deleted}")
    if deleted == 0:
        print("  （当前记忆均较新或保持率足够，无遗忘）")

    # -------------------------------------------------------------------------
    print("\n【7】再次召回（验证未被误删的记忆仍可检索）")
    print("-" * 40)

    recalled_after = await retrieve_relevant_memories(
        user_id=user_id,
        query=query,
        conversation_id=conversation_id,
        top_k_final=5,
    )
    print(f"召回条数: {len(recalled_after)}")
    for r in recalled_after[:3]:
        print(f"  - {r['content'][:50]}...")

    # -------------------------------------------------------------------------
    print("\n" + "=" * 60)
    print("全功能测试完成")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
