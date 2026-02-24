-- Agent 长期记忆与反思表（与 MySQL 版语义一致，适配 PostgreSQL）
-- 依赖: 先执行 schema_users.sql、schema_conversations.sql。
-- 执行: psql $DATABASE_URL -f db/schema_agent_memories.sql

CREATE TABLE IF NOT EXISTS agent_memories (
    id                  VARCHAR(36) NOT NULL,
    user_id             BIGINT NOT NULL,
    conversation_id     VARCHAR(36) DEFAULT NULL,

    memory_type         VARCHAR(20) NOT NULL,
    domain              VARCHAR(50) NOT NULL DEFAULT 'general_chat',
    source_role         VARCHAR(20) DEFAULT NULL,
    source_message_id   VARCHAR(64) DEFAULT NULL,

    content             TEXT NOT NULL,
    metadata            JSONB DEFAULT NULL,

    vector_collection   VARCHAR(64) NOT NULL DEFAULT 'agent_memories',

    importance_score    NUMERIC(4,3) NOT NULL DEFAULT 0.000,
    access_count        INT NOT NULL DEFAULT 0,
    last_accessed_at    TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    expires_at          TIMESTAMP DEFAULT NULL,
    is_deleted          BOOLEAN NOT NULL DEFAULT FALSE,

    created_at          TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at          TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    PRIMARY KEY (id),
    CONSTRAINT fk_agent_memories_user_id FOREIGN KEY (user_id)
        REFERENCES users (id) ON DELETE CASCADE
    -- 如需强制关联会话，可取消注释下面的外键，并保证 conversation_id 非空
    -- ,CONSTRAINT fk_agent_memories_conversation_id FOREIGN KEY (conversation_id)
    --     REFERENCES conversations (id) ON DELETE SET NULL
);

-- 领域路由：按用户+领域筛选（加速混合检索）
CREATE INDEX IF NOT EXISTS idx_agent_memories_user_domain
    ON agent_memories (user_id, domain);

-- 常用检索：按用户+类型筛选重要记忆
CREATE INDEX IF NOT EXISTS idx_agent_memories_user_type
    ON agent_memories (user_id, memory_type);

-- 常用检索：某用户某会话下的记忆（会话内记忆）
CREATE INDEX IF NOT EXISTS idx_agent_memories_user_conv_type
    ON agent_memories (user_id, conversation_id, memory_type);

-- 衰减/排序：按重要性+用户筛选
CREATE INDEX IF NOT EXISTS idx_agent_memories_user_importance
    ON agent_memories (user_id, importance_score);

-- 定时任务：按最后访问时间做 decay/清理
CREATE INDEX IF NOT EXISTS idx_agent_memories_last_accessed
    ON agent_memories (last_accessed_at);

-- 定时任务：按过期时间批量删除/归档
CREATE INDEX IF NOT EXISTS idx_agent_memories_expires_at
    ON agent_memories (expires_at);

-- 去重/追踪：同一用户同一来源消息只生成一条记忆
CREATE INDEX IF NOT EXISTS idx_agent_memories_user_source_msg
    ON agent_memories (user_id, source_message_id);

-- 向量库维度：快速查找同 collection 下的记忆
CREATE INDEX IF NOT EXISTS idx_agent_memories_vector_collection
    ON agent_memories (vector_collection);

COMMENT ON TABLE agent_memories IS 'Agent 长期记忆与反思表';
COMMENT ON COLUMN agent_memories.id IS '记忆ID (UUID 字符串，与向量库 Vector ID 一致)';
COMMENT ON COLUMN agent_memories.user_id IS '归属用户ID (关联 users.id)';
COMMENT ON COLUMN agent_memories.conversation_id IS '来源会话ID (跨会话全局记忆可为 NULL)';
COMMENT ON COLUMN agent_memories.memory_type IS '记忆类型: message(重要消息), reflection(反思), fact(客观事实)';
COMMENT ON COLUMN agent_memories.domain IS '所属通用领域: general_chat, user_preferences, professional_and_academic, lifestyle_and_interests, social_and_relationships, tasks_and_schedules';
COMMENT ON COLUMN agent_memories.source_role IS '来源角色: system,user,assistant,tool';
COMMENT ON COLUMN agent_memories.source_message_id IS '来源消息/内容ID, 用于去重与追踪';
COMMENT ON COLUMN agent_memories.content IS '记忆文本内容';
COMMENT ON COLUMN agent_memories.metadata IS '额外元信息(JSONB)，如 tags, model, tool_name 等';
COMMENT ON COLUMN agent_memories.vector_collection IS '向量库 collection 名称，用于区分不同记忆集合';
COMMENT ON COLUMN agent_memories.importance_score IS '重要性得分 0.000~1.000 (对应代码里的 importance_threshold)';
COMMENT ON COLUMN agent_memories.access_count IS '被检索/命中次数';
COMMENT ON COLUMN agent_memories.last_accessed_at IS '最后一次被检索或访问时间 (用于时间衰减)';
COMMENT ON COLUMN agent_memories.expires_at IS '逻辑过期时间(可为空, 方便批量清理)';
COMMENT ON COLUMN agent_memories.is_deleted IS '软删除标记: false=正常, true=删除';
COMMENT ON COLUMN agent_memories.created_at IS '创建时间';
COMMENT ON COLUMN agent_memories.updated_at IS '最后更新时间';

