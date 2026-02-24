# Memory 模块

Agent 长期记忆与反思模块，为对话模式提供分层记忆能力。支持**异步打分写入**与**三维混合召回**（语义 + 时间衰减 + 重要性）。

## 目录结构

```
memory/
├── __init__.py       # 导出 extract、retrieve、compress、get_intent_domains 等
├── router.py         # 意图路由：6 大领域分类，用于 domain 过滤
├── service.py        # 核心逻辑：打分、双写、混合召回、记忆压缩
├── vector_store.py   # Milvus 向量存储封装（含 domain、content 标量字段）
├── forgetting.py     # 艾宾浩斯遗忘曲线、定期清理
├── test_memory.py    # 手动测试脚本
└── README.md
```

## 架构概览

### 数据流

```
对话回合结束
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│ 阶段二：记忆写入 (extract_and_store_memories_for_round)     │
│  1. DeepSeek 打分 → importance_score, extracted_fact, domain │
│  2. 仅当 score ≥ 0.7 且 extracted_fact 非空时写入             │
│  3. 双写：PostgreSQL (agent_memories) + Milvus (向量+domain+content) │
└─────────────────────────────────────────────────────────────┘

用户新指令
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│ 意图路由 (get_intent_domains)                                 │
│  调用轻量模型对用户输入做领域分类 → target_domains             │
│  若为 general_chat 则跳过记忆检索；否则进入混合召回             │
└─────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│ 阶段三：混合召回 (retrieve_relevant_memories)                 │
│  1. 语义粗筛：Milvus 向量检索 + domain 标量过滤                │
│  2. 元数据拉取：PostgreSQL 取 importance_score、last_accessed │
│  3. 时间衰减：S_time_decay = decay_rate^Δt                     │
│  4. 精排：S_final = α·S_semantic + β·S_time_decay + γ·S_imp  │
│  5. Touch：更新被选中记忆的 last_accessed_at                   │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│ 阶段四：反思 (try_generate_reflection)                        │
│  1. 每次写入 fact 后异步检查：近期 fact 的 importance 累加     │
│  2. 若累加 ≥ 阈值（默认 4.0）且距上次反思 ≥ 冷却时间（1h）      │
│  3. 调用 LLM 生成高层总结，写入 memory_type=reflection         │
│  4. 被总结的 fact 向量从 Milvus 中删除，避免冗余检索            │
│  5. 反思记忆不参与遗忘（exclude_memory_types）                 │
└─────────────────────────────────────────────────────────────┘
```

### 打分公式

$$S_{final} = \alpha \cdot S_{semantic} + \beta \cdot S_{time\_decay} + \gamma \cdot S_{importance}$$

- **S_semantic**：Milvus 余弦相似度，归一化到 [0,1]
- **S_time_decay**：`decay_rate^(Δt/小时)`，Δt = 当前时间 - last_accessed_at
- **S_importance**：LLM 打分的 importance_score，严格 [0,1]

默认权重：α=0.5, β=0.2, γ=0.3（可通过参数覆盖）

## 依赖

| 组件 | 用途 |
|------|------|
| **PostgreSQL** | 存储 agent_memories 表（importance_score、last_accessed_at 等） |
| **Milvus** | 存储记忆向量，COSINE 距离，支持 user_id 过滤 |
| **Qwen API** | Embedding 模型（text-embedding-v4） |
| **DeepSeek API** | 重要性打分模型（deepseek-chat，JSON 输出） |

## 环境变量

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `QWEN_API_KEY` | 通义千问 API Key（Embedding） | 必填 |
| `QWEN_API_BASE` | Qwen API 地址 | `https://dashscope.aliyuncs.com/compatible-mode/v1` |
| `DEEPSEEK_API_KEY` | DeepSeek API Key（打分） | 必填 |
| `DEEPSEEK_API_BASE` | DeepSeek API 地址 | `https://api.deepseek.com/v1` |
| `MEMORY_EMBEDDING_MODEL` | Embedding 模型名 | `text-embedding-v4` |
| `MEMORY_SCORER_MODEL` | 打分模型名 | `deepseek-chat` |
| `MEMORY_ROUTER_MODEL` | 意图路由模型名 | `deepseek-chat` |
| `MILVUS_HOST` | Milvus 主机 | `localhost` |
| `MILVUS_PORT` | Milvus 端口 | `19530` |
| `MILVUS_MEMORY_COLLECTION` | 向量 collection 名 | `agent_memories_vectors` |

**Milvus Schema**：collection 含 `domain`（领域过滤）、`content`（原文本，便于人类阅读，最大 4096 字符）。

## 使用方式

### 1. 写入记忆（对话结束后调用）

```python
from memory import extract_and_store_memories_for_round

memories = await extract_and_store_memories_for_round(
    user_id=user_id,
    conversation_id=conversation_id,
    user_content="用户本轮输入",
    assistant_content="助手本轮回复",
)
# 返回写入成功的记忆列表（可能为空，若 LLM 判定重要性 < 0.7）
```

已在 `services/chat_context.py` 的 `persist_round` 中接入，对话落库后异步触发（`asyncio.create_task`，不阻塞前端）。

### 2. 召回记忆（拼入 Prompt 前调用）

```python
from memory import retrieve_relevant_memories

memories = await retrieve_relevant_memories(
    user_id=user_id,
    query="用户当前输入",
    alpha=0.5,
    beta=0.2,
    gamma=0.3,
    decay_rate=0.99,
    top_k_semantic=50,
    top_k_final=10,
)
# 返回按 S_final 排序的 Top-K 记忆，每条含 content、importance_score、final_score 等
```

已在 `routers/chat.py` 的 `_resolve_conversation_and_messages` 中接入：拼 prompt 前调用 `get_memory_context_for_prompt`，召回记忆注入 system 的 `【长期记忆】` 块。

### 3. 记忆压缩（召回过多时使用）

当召回的记忆条数较多、不便直接拼入 Prompt 时，可调用压缩器生成摘要：

```python
from memory import retrieve_relevant_memories, compress_memories

memories = await retrieve_relevant_memories(user_id=user_id, query=query, top_k_final=10)

if len(memories) > 5:
    summary = await compress_memories(memories, max_chars=500)
    # 将 summary 拼入 system prompt
else:
    # 直接使用 memories 中的 content
    content_block = "\n".join(m["content"] for m in memories)
```

### 4. 遗忘清理（定期调用）

基于艾宾浩斯遗忘曲线，将长期不被召回、保持率低于阈值的记忆软删除：

```python
from memory import cleanup_forgotten_memories

deleted = await cleanup_forgotten_memories(
    user_id=user_id,
    base_retention=0.9,        # 基础遗忘率
    strengthening_factor=1.5,  # 访问强化系数
    threshold=0.1,             # 保持率 < 0.1 时软删除
    exclude_memory_types=["reflection"],  # 反思类记忆不参与遗忘
)
# 返回实际软删除的记忆条数
```

建议由定时任务（如 cron、Celery beat）定期调用，例如每日一次。

### 5. 反思（阶段四，自动触发）

每次 `extract_and_store_memories_for_round` 写入新 fact 后，会异步检查是否触发反思：

- 近期 fact 的 `importance_score` 累加 ≥ 4.0
- 距上次反思 ≥ 1 小时（冷却）
- 至少 2 条 fact

满足时调用 LLM 生成高层总结，写入 `memory_type=reflection`，importance=0.9。

也可手动触发（如测试）：

```python
from memory import try_generate_reflection

reflection = await try_generate_reflection(
    user_id=user_id,
    conversation_id=conversation_id,
    importance_threshold=2.5,  # 降低阈值便于测试
    cooldown_hours=0,          # 测试时跳过冷却
)
# 返回反思记忆 dict 或 None
```

### 6. 手动测试

```bash
cd backend
python -m memory.test_memory
```

会依次执行：创建测试用户/会话 → 写入记忆 → 混合召回，并在终端打印每步结果。

## 数据表

依赖 `db/schema_agent_memories.sql`，执行 `python -m db.run_schema` 时会自动建表。核心字段：

- `id`：UUID，与 Milvus 向量 ID 一致
- `user_id`：归属用户
- `conversation_id`：来源会话（可为 NULL 表示全局记忆）
- `content`：记忆文本
- `memory_type`：`message` / `reflection` / `fact`
- `domain`：`general_chat` / `user_preferences` / `professional_and_academic` / `lifestyle_and_interests` / `social_and_relationships` / `tasks_and_schedules`
- `importance_score`：0.0 ~ 1.0
- `last_accessed_at`：用于时间衰减计算

### 艾宾浩斯遗忘公式

保持率 = `base_retention^(Δt / (24 × strengthening_factor^access_count)) × (0.5 + 0.5 × importance)`

- **Δt**：距上次召回的小时数（`last_accessed_at`）
- **access_count**：被召回次数，越高越抗遗忘
- **importance**：重要性得分，越高越抗遗忘

## 全功能测试

`test_memory_full.py` 覆盖记忆模块所有能力：

```bash
cd backend
python -m memory.test_memory_full
```

测试流程：

1. **记忆写入**：使用高重要性对话（如青霉素过敏、技术栈决策）触发 LLM 打分并写入
2. **反思触发**：累加 importance 达阈值时生成高层总结（memory_type=reflection）
3. **混合召回**：语义检索 + 时间衰减 + 重要性混合打分
4. **记忆压缩**：将多条召回记忆压缩为一段摘要
5. **艾宾浩斯保持率**：展示 `EbbinghausForgetting.calculate_retention` 对每条记忆的保持率
6. **遗忘清理**：`cleanup_forgotten_memories` 软删除保持率低于阈值的记忆
7. **再次召回**：验证未被误删的记忆仍可检索

前置：PostgreSQL 已建表、Milvus 已启动，`.env` 中配置 `QWEN_API_KEY`、`DEEPSEEK_API_KEY`。

