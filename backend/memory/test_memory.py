"""
手动测试 memory 模块的写入 + 召回流程。

运行方式（在 backend 目录下）：

    cd backend
    python -m memory.test_memory

前置要求：
- PostgreSQL 已根据 db/schema_*.sql 建表并可连接；
- Milvus 已启动，并与 .env 中的 MILVUS_HOST / MILVUS_PORT 一致；
- .env 中已配置 QWEN_API_KEY（用于 Embedding）和 DEEPSEEK_API_KEY（用于重要性打分）。
"""

import asyncio
from uuid import uuid4

from dotenv import load_dotenv

from db.user_repository import user_repository, hash_password
from db.conversation_repository import conversation_repository
from memory import extract_and_store_memories_for_round, retrieve_relevant_memories


async def main() -> None:
    # 0) 加载环境变量
    load_dotenv()

    print("=== 1) 创建测试用户 ===")
    email = f"memory_test_{uuid4().hex[:8]}@example.com"
    user = await user_repository.create(
        email=email,
        password_hash=hash_password("test_memory_123456"),
        username="memory-test-user",
    )
    user_id = user["id"]
    print(f"用户已创建: id={user_id}, email={email}")

    print("\n=== 2) 创建测试会话 ===")
    conversation_id = str(uuid4())
    conv = await conversation_repository.create(
        conversation_id=conversation_id,
        user_id=user_id,
        title="Memory 模块测试会话",
        system_prompt=None,
        model_provider="qwen",
    )
    print(f"会话已创建: id={conv['id']}, user_id={conv['user_id']}")

    print("\n=== 3) 准备一轮对话内容（用于写入记忆） ===")
    # 使用更明确重要的内容，便于触发 importance_score >= 0.7
    #  "我对青霉素严重过敏，请务必记住，以后推荐药物时要避开。"
    # "已记录：您对青霉素严重过敏，后续推荐药物时会严格避开青霉素类。"
    user_content ="你好"
    assistant_content = "你好，有什么可以帮你的吗？"
    print(f"User: {user_content}")
    print(f"Assistant: {assistant_content}")

    print("\n=== 4) 调用 extract_and_store_memories_for_round 写入记忆（LLM 打分 + PostgreSQL + Milvus） ===")
    memories = await extract_and_store_memories_for_round(
        user_id=user_id,
        conversation_id=conversation_id,
        user_content=user_content,
        assistant_content=assistant_content,
    )
    print(f"写入返回的记忆条数: {len(memories)}")
    if not memories:
        print("当前这轮对话未被判定为高重要性记忆（importance_score < 0.7 或无 extracted_fact）。")
    else:
        for idx, m in enumerate(memories, 1):
            print(f"\n--- 记忆 {idx} ---")
            print(f"id            : {m.get('id')}")
            print(f"importance    : {m.get('importance_score')}")
            print(f"memory_type   : {m.get('memory_type')}")
            print(f"content       : {m.get('content')}")

    print("\n=== 5) 使用查询语句触发混合召回 retrieve_relevant_memories ===")
    query = "我有什么药物过敏需要特别注意？"
    print(f"查询语句: {query}")

    recalled = await retrieve_relevant_memories(
        user_id=user_id,
        query=query,
        alpha=0.5,
        beta=0.2,
        gamma=0.3,
        decay_rate=0.99,
        top_k_semantic=20,
        top_k_final=5,
    )
    print(f"\n混合召回结果条数: {len(recalled)}")
    for idx, r in enumerate(recalled, 1):
        print(f"\n--- 召回结果 {idx} ---")
        print(f"id             : {r['id']}")
        print(f"importance     : {r['importance_score']:.3f}")
        print(f"semantic_score : {r['semantic_score']:.3f}")
        print(f"time_decay     : {r['time_decay_score']:.3f}")
        print(f"final_score    : {r['final_score']:.3f}")
        print(f"content        : {r['content']}")

    print("\n=== 6) 测试完成 ===")


if __name__ == "__main__":
    asyncio.run(main())

