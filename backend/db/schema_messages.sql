-- AI 对话消息明细表（与 MySQL 版语义一致，适配 PostgreSQL）
-- 依赖: 先执行 schema_conversations.sql。
-- 执行: psql $DATABASE_URL -f db/schema_messages.sql

CREATE TABLE IF NOT EXISTS messages (
    id                  BIGSERIAL PRIMARY KEY,
    conversation_id     VARCHAR(36) NOT NULL,
    role                VARCHAR(20) NOT NULL,
    content             TEXT NOT NULL,
    token_count         INT DEFAULT 0,
    metadata            JSONB DEFAULT NULL,
    created_at          TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_messages_conversation_id FOREIGN KEY (conversation_id)
        REFERENCES conversations (id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_messages_conversation_created
    ON messages (conversation_id, created_at ASC);

COMMENT ON TABLE messages IS 'AI 对话消息明细表';
COMMENT ON COLUMN messages.id IS '消息主键 (用自增ID保证物理层面的严格绝对排序)';
COMMENT ON COLUMN messages.conversation_id IS '关联的会话ID';
COMMENT ON COLUMN messages.role IS '消息角色：system, user, assistant, tool';
COMMENT ON COLUMN messages.content IS '消息文本内容 (存 Markdown 格式)';
COMMENT ON COLUMN messages.token_count IS '当前消息估算的 Token 数 (用于上下文截断和成本核算)';
COMMENT ON COLUMN messages.metadata IS '扩展元数据 (极度重要：存 RAG 引用文档、Agent 工具调用状态等)';
COMMENT ON COLUMN messages.created_at IS '发送时间 (精确到毫秒)';
