import asyncio
import json
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable, List

from openai import AsyncOpenAI

from db.agent_memory_repository import agent_memory_repository

logger = logging.getLogger("memory")
from memory.router import NON_GENERAL_DOMAINS
from memory.vector_store import delete_memories, upsert_memories, query_memories


# Embedding 模型：使用通义千问 text-embedding-v4（DashScope OpenAI 兼容接口）
EMBEDDING_MODEL = os.getenv("MEMORY_EMBEDDING_MODEL", "text-embedding-v4")

# 评价/打分模型：使用 DeepSeek 的 chat 模型（支持 JSON 输出）
SCORER_MODEL = os.getenv("MEMORY_SCORER_MODEL", "deepseek-chat")


def _get_embedding_client() -> AsyncOpenAI:
    """
    Embedding 客户端：使用通义千问（Qwen）OpenAI 兼容接口。

    - API Key 从 QWEN_API_KEY 读取（与你主聊天模型一致）；
    - 默认使用北京地域 base_url，可通过 QWEN_API_BASE 覆盖。
    """
    api_key = os.getenv("QWEN_API_KEY")
    if not api_key:
        raise RuntimeError("QWEN_API_KEY 未配置，无法执行向量化")
    base_url = os.getenv(
        "QWEN_API_BASE",
        "https://dashscope.aliyuncs.com/compatible-mode/v1",
    )
    return AsyncOpenAI(api_key=api_key, base_url=base_url)


def _get_scorer_client() -> AsyncOpenAI:
    """
    评价/打分客户端：使用 DeepSeek 的 OpenAI 兼容接口，并开启 JSON 输出。
    """
    api_key = os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        raise RuntimeError("DEEPSEEK_API_KEY 未配置，无法执行记忆重要性打分")
    base_url = os.getenv("DEEPSEEK_API_BASE", "https://api.deepseek.com/v1")
    return AsyncOpenAI(api_key=api_key, base_url=base_url)


@dataclass
class ScoredMemory:
    id: str
    user_id: int
    conversation_id: str | None
    content: str
    memory_type: str
    importance_score: float
    domain: str = "general_chat"
    source_role: str | None = None
    source_message_id: str | None = None
    metadata: dict[str, Any] | None = None


async def _embed_texts(texts: list[str]) -> list[list[float]]:
    """
    使用通义千问（Qwen）Embedding 模型进行向量化。
    """
    if not texts:
        return []
    client = _get_embedding_client()
    resp = await client.embeddings.create(model=EMBEDDING_MODEL, input=texts)
    return [d.embedding for d in resp.data]


async def _call_scorer_llm(
    *,
    user_content: str,
    assistant_content: str,
    ) -> list[dict[str, Any]]:
    """
    调用 DeepSeek 模型，基于单轮对话评估重要性并（在高分时）抽取一个核心事实。

    - 使用 JSON 输出模式，方便可靠解析；
    - importance_score ∈ [0.0, 1.0]，超出范围会在代码中强制裁剪；
    - 仅当 importance_score >= 0.7 且 extracted_fact 非空时，才写入记忆。
    """
    client = _get_scorer_client()
    system_prompt = (
        "你是一个专业的 AI 记忆分析师。"
    )
    user_prompt = (
        "请分析以下这段用户与 AI 的最新对话回合。\n\n"
        "【对话内容】\n"
        f"User: {user_content}\n"
        f"Assistant: {assistant_content}\n\n"
        "【任务指令】\n"
        "1. 评估这段对话对于理解用户的长期偏好、当前项目状态、关键决策或个人信息的“重要性得分”（0.0 到 1.0）。\n"
        "   - 0.0-0.3：日常寒暄、无意义的追问、已解决的临时小报错。\n"
        "   - 0.4-0.6：一般性知识探讨。\n"
        "   - 0.7-1.0：明确的用户个人信息、重大的架构决定、长期的项目目标。\n"
        "2. 如果得分 >= 0.7，请用第三人称的客观视角，用一句话总结必须记住的“核心事实 (Fact)”。\n"
        f"3. 为事实标注领域 domain，必须从以下选一个：{', '.join(NON_GENERAL_DOMAINS)}。\n\n"
        "【输出格式】(严格返回 JSON)\n"
        "{\n"
        '  \"importance_score\": 0.85,\n'
        '  \"extracted_fact\": \"\",\n'
        '  \"domain\": \"professional_and_academic\"\n'
        "}\n"
    )
    resp = await client.chat.completions.create(
        model=SCORER_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.2,
        max_tokens=512,
        response_format={"type": "json_object"},
    )
    raw = resp.choices[0].message.content or "{}"
    try:
        data = json.loads(raw)
        if not isinstance(data, dict):
            return []

        # 解析分数并强制裁剪到 [0.0, 1.0]
        try:
            score = float(data.get("importance_score", 0.0))
        except (TypeError, ValueError):
            score = 0.0
        score = max(0.0, min(1.0, score))

        extracted = (data.get("extracted_fact") or "").strip()

        # 打印大模型返回的原始结果（便于在 terminal 中查看）
        logger.info("[Memory] 打分 | importance_score=%.3f extracted_fact=%s", score, extracted[:50] if extracted else "")

        # 只有当分数足够高且有清晰的事实时，才生成记忆
        domain = (data.get("domain") or "general_chat").strip()
        if domain not in NON_GENERAL_DOMAINS:
            domain = "general_chat"

        if score >= 0.7 and extracted:
            return [
                {
                    "content": extracted,
                    "memory_type": "fact",
                    "importance_score": score,
                    "domain": domain,
                }
            ]
        return []
    except json.JSONDecodeError:
        return []


async def extract_and_store_memories_for_round(
    *,
    user_id: int,
    conversation_id: str,
    user_content: str,
    assistant_content: str,
    source_message_id: str | None = None,
    source_role: str | None = "user",
    vector_collection: str = "agent_memories",
) -> list[dict[str, Any]]:
    """
    阶段二：记忆写入（异步打分 + 双写落库）。

    - 调用 LLM 抽取记忆 + importance_score（[0,1]）
    - 在 PostgreSQL 写入 agent_memories
    - 在 Milvus 中写入对应向量（使用相同 UUID）
    """
    logger.info(
        "[Memory] 记忆写入 extract_and_store | user_id=%s conv=%s",
        user_id,
        conversation_id[:8] if conversation_id else "-",
    )
    from uuid import uuid4

    scored_items = await _call_scorer_llm(
        user_content=user_content,
        assistant_content=assistant_content,
    )
    if not scored_items:
        return []

    now = datetime.now(timezone.utc)

    # 构造记忆对象
    memories: list[ScoredMemory] = []
    for item in scored_items:
        mem_id = str(uuid4())
        memories.append(
            ScoredMemory(
                id=mem_id,
                user_id=user_id,
                conversation_id=conversation_id,
                content=item["content"],
                memory_type=item.get("memory_type", "fact"),
                importance_score=float(item.get("importance_score", 0.0)),
                domain=item.get("domain", "general_chat"),
                source_role=source_role,
                source_message_id=source_message_id,
                metadata={"conversation_id": conversation_id},
            )
        )

    # 先向量化
    embeddings = await _embed_texts([m.content for m in memories])

    # 双写：PostgreSQL + Milvus（向量）
    tasks = []
    # 1) 写入 PostgreSQL
    for mem in memories:
        tasks.append(
            agent_memory_repository.create(
                id=mem.id,
                user_id=mem.user_id,
                conversation_id=mem.conversation_id,
                memory_type=mem.memory_type,
                domain=mem.domain,
                source_role=mem.source_role,
                source_message_id=mem.source_message_id,
                content=mem.content,
                metadata=mem.metadata,
                vector_collection=vector_collection,
                importance_score=mem.importance_score,
                expires_at=None,
            )
        )

    # 2) 写入 Milvus
    # 将 user_id / conversation_id / content 等打进 metadata
    vec_metadatas: list[dict[str, Any]] = []
    for mem in memories:
        md = dict(mem.metadata or {})
        md.update(
            {
                "user_id": mem.user_id,
                "conversation_id": mem.conversation_id,
                "memory_type": mem.memory_type,
                "domain": mem.domain,
                "content": mem.content,
            }
        )
        vec_metadatas.append(md)

    tasks.append(
        upsert_memories(
            ids=[m.id for m in memories],
            embeddings=embeddings,
            metadatas=vec_metadatas,
        )
    )

    results = await asyncio.gather(*tasks, return_exceptions=True)
    out: list[dict[str, Any]] = []
    for r in results:
        if isinstance(r, dict):
            out.append(r)
        elif isinstance(r, BaseException):
            logger.warning("[Memory] 写入异常: %s", r)

    # 阶段四：累加 importance 达阈值时触发反思
    if out:
        asyncio.create_task(
            try_generate_reflection(
                user_id=user_id,
                conversation_id=conversation_id,
            )
        )

    return out


async def _call_reflection_llm(facts: list[dict[str, Any]]) -> str | None:
    """
    调用 LLM 基于多条 fact 记忆生成高层反思总结。
    """
    if not facts:
        return None
    contents = [f.get("content", "").strip() for f in facts if f.get("content")]
    if not contents:
        return None

    client = _get_scorer_client()
    prompt = (
        "以下是一组用户与 AI 对话中积累的「事实记忆」，请提炼成一段高层反思总结。\n\n"
        "【要求】\n"
        "1. 用第三人称客观视角，归纳用户的偏好、决策、项目状态或重要信息。\n"
        "2. 控制在 300 字以内，突出可长期参考的洞察。\n"
        "3. 不要逐条罗列，而是整合成连贯的总结。\n\n"
        "【事实记忆】\n"
        + "\n".join(f"- {c}" for c in contents)
        + "\n\n【输出】仅返回反思文本，不要解释、不要编号。"
    )
    resp = await client.chat.completions.create(
        model=SCORER_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3,
        max_tokens=256,
    )
    summary = (resp.choices[0].message.content or "").strip()
    return summary[:500] if summary else None


async def try_generate_reflection(
    *,
    user_id: int,
    conversation_id: str,
    importance_threshold: float = 4.0,
    cooldown_hours: float = 1.0,
    max_facts: int = 15,
) -> dict[str, Any] | None:
    """
    阶段四：当近期 fact 记忆的 importance 累加达阈值时，生成反思并写入。

    - importance_threshold: 累加 importance 达到此值才触发（默认 4.0）
    - cooldown_hours: 距上次反思不足此小时数则跳过（默认 1.0）
    - max_facts: 参与累加的最大 fact 条数（默认 15）
    """
    logger.info(
        "[Memory] 反思检查 try_generate_reflection | user_id=%s conv=%s",
        user_id,
        conversation_id[:8] if conversation_id else "-",
    )
    from uuid import uuid4

    now = datetime.now(timezone.utc)

    # 冷却检查
    last = await agent_memory_repository.get_last_reflection(user_id, conversation_id)
    if last:
        created = last["created_at"]
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        if (now - created).total_seconds() < cooldown_hours * 3600:
            return None

    # 获取近期 fact 记忆
    facts = await agent_memory_repository.list_recent_facts_for_reflection(
        user_id=user_id,
        conversation_id=conversation_id,
        limit=max_facts,
    )
    if len(facts) < 2:
        return None

    total_importance = sum(f.get("importance_score", 0.0) for f in facts)
    if total_importance < importance_threshold:
        return None

    # 调用 LLM 生成反思
    reflection_text = await _call_reflection_llm(facts)
    if not reflection_text:
        return None

    logger.info(
        "[Memory] 反思生成 | importance_sum=%.2f 写入 %d 字",
        total_importance,
        len(reflection_text),
    )

    # 写入反思记忆（双写 PostgreSQL + Milvus）
    mem_id = str(uuid4())
    metadata = {
        "conversation_id": conversation_id,
        "reflection_source_ids": [f["id"] for f in facts[:10]],
    }

    try:
        await agent_memory_repository.create(
            id=mem_id,
            user_id=user_id,
            conversation_id=conversation_id,
            memory_type="reflection",
            domain="general_chat",  # 反思为跨领域总结
            content=reflection_text,
            metadata=metadata,
            vector_collection="agent_memories",
            importance_score=0.9,  # 反思为高层总结，给较高重要性
            expires_at=None,
        )

        embeddings = await _embed_texts([reflection_text])
        await upsert_memories(
            ids=[mem_id],
            embeddings=embeddings,
            metadatas=[{"user_id": user_id, "conversation_id": conversation_id, "memory_type": "reflection", "domain": "general_chat", "content": reflection_text}],
        )

        # 被总结的 fact 向量从 Milvus 中删除，避免冗余检索
        source_ids = [f["id"] for f in facts]
        try:
            deleted = await delete_memories(ids=source_ids)
            if deleted > 0:
                logger.info("[Memory] 反思后删除 Milvus 向量 | deleted=%d", deleted)
        except Exception as e:
            logger.warning("[Memory] 反思 Milvus 删除异常: %s", e)

        return {"id": mem_id, "content": reflection_text, "memory_type": "reflection"}
    except Exception as e:
        logger.warning("[Memory] 反思写入异常: %s", e)
        return None


def _compute_time_decay(last_accessed_at: datetime, now: datetime, decay_rate: float) -> float:
    """
    计算 S_time_decay。
    """
    if last_accessed_at.tzinfo is None:
        last_accessed_at = last_accessed_at.replace(tzinfo=timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    delta = now - last_accessed_at
    hours = delta.total_seconds() / 3600.0
    if hours <= 0:
        return 1.0
    return float(decay_rate**hours)


async def retrieve_relevant_memories(
    *,
    user_id: int,
    query: str,
    conversation_id: str | None = None,
    target_domains: list[str] | None = None,
    alpha: float = 0.5,
    beta: float = 0.2,
    gamma: float = 0.3,
    decay_rate: float = 0.99,
    top_k_semantic: int = 50,
    top_k_final: int = 10,
    vector_collection: str = "agent_memories",
) -> list[dict[str, Any]]:
    """
    阶段三：混合计算与召回。

    - conversation_id: 可选，限定召回范围。
    - target_domains: 可选，领域路由过滤。为 None 或含 general_chat 时不过滤 domain；
      否则仅召回 domain in target_domains 的记忆。

    返回按 S_final 排序后的记忆列表，每条包含附加字段：
    - semantic_score
    - time_decay_score
    - final_score
    """
    logger.info(
        "[Memory] 记忆召回 retrieve_relevant_memories | user_id=%s conv=%s domains=%s",
        user_id,
        conversation_id[:8] if conversation_id else "-",
        target_domains,
    )
    if not query.strip():
        return []

    # 3.1: 语义粗筛（支持 domain 过滤）
    query_embedding = (await _embed_texts([query]))[0]
    where: dict[str, Any] = {"user_id": user_id}
    if target_domains and "general_chat" not in target_domains:
        where["domains"] = [d for d in target_domains if d != "general_chat"]
    search_result = await query_memories(
        query_embeddings=[query_embedding],
        where=where,
        n_results=top_k_semantic,
    )
    ids = search_result.get("ids") or [[]]
    distances = search_result.get("distances") or [[]]
    if not ids[0]:
        return []

    memory_ids: list[str] = [str(i) for i in ids[0]]
    raw_distances: list[float] = [float(d) for d in distances[0]]

    # 将向量检索返回的 distance 映射为 [0,1] 区间的相似度
    semantic_scores: dict[str, float] = {}
    for mem_id, dist in zip(memory_ids, raw_distances):
        # 经验映射：距离约在 [0,2]，简单归一化到 [0,1]
        score = 1.0 - max(0.0, min(2.0, dist)) / 2.0
        semantic_scores[mem_id] = score

    # 3.2: 元数据拉取
    mem_rows = await agent_memory_repository.get_by_ids(memory_ids)
    if not mem_rows:
        return []

    # 按 conversation_id 限定召回范围
    if conversation_id is not None:
        mem_rows = [
            m for m in mem_rows
            if m.get("conversation_id") == conversation_id or m.get("conversation_id") is None
        ]
        # 过滤后需重排 memory_ids，只保留范围内的 id，以维持语义排序
        valid_ids = {m["id"] for m in mem_rows}
        memory_ids = [i for i in memory_ids if i in valid_ids]

    row_map = {m["id"]: m for m in mem_rows}

    # 3.3 & 3.4: 时间衰减 + 精排打分
    now = datetime.now(timezone.utc)
    enriched: list[dict[str, Any]] = []
    for mem_id in memory_ids:
        row = row_map.get(mem_id)
        if not row:
            continue
        s_semantic = semantic_scores.get(mem_id, 0.0)
        s_importance = float(row.get("importance_score", 0.0))
        last_accessed_at: datetime = row.get("last_accessed_at") or row.get("created_at") or now
        s_time_decay = _compute_time_decay(last_accessed_at, now, decay_rate)
        s_final = alpha * s_semantic + beta * s_time_decay + gamma * s_importance

        item = dict(row)
        item["semantic_score"] = s_semantic
        item["time_decay_score"] = s_time_decay
        item["final_score"] = s_final
        enriched.append(item)

    enriched.sort(key=lambda x: x["final_score"], reverse=True)
    top = enriched[:top_k_final]
    if top:
        logger.info("[Memory] 记忆召回结果 | 返回 %d 条", len(top))

    # 3.5: touch（反馈）
    await agent_memory_repository.touch_many([m["id"] for m in top])

    return top


async def compress_memories(
    memories: list[dict[str, Any]],
    *,
    model: str | None = None,
    max_chars: int = 500,
) -> str:
    """
    记忆压缩器：将多条记忆压缩为一段简洁摘要。

    当召回的记忆条数过多、不便直接拼入 Prompt 时，可调用此函数生成摘要，
    减少 token 占用并保留关键事实与偏好。

    - memories: 记忆列表，每条至少含 content 字段
    - model: 使用的模型，默认与 SCORER_MODEL 一致
    - max_chars: 摘要最大字符数（约等于 token 上限）
    """
    logger.info("[Memory] 记忆压缩 compress_memories | 输入 %d 条 max_chars=%d", len(memories), max_chars)
    if not memories:
        return ""

    contents = [m.get("content", "").strip() for m in memories if m.get("content")]
    if not contents:
        return ""

    client = _get_scorer_client()
    prompt = (
        "以下是一组用户的长期记忆，请用简洁的语言归纳成一段摘要，"
        f"保留关键事实、偏好与重要信息，控制在 {max_chars} 字以内。\n\n"
        "【记忆列表】\n"
        + "\n".join(f"- {c}" for c in contents)
        + "\n\n【输出】仅返回摘要文本，不要解释、不要编号。"
    )
    resp = await client.chat.completions.create(
        model=model or SCORER_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3,
        max_tokens=256,
    )
    summary = (resp.choices[0].message.content or "").strip()
    return summary[:max_chars] if len(summary) > max_chars else summary

