-- AI 会话/聊天室表（与 MySQL 版语义一致，适配 PostgreSQL）
-- 对应前端左侧边栏的“历史对话框”。依赖: 先执行 schema_users.sql。
-- 执行: psql $DATABASE_URL -f db/schema_conversations.sql

CREATE TABLE IF NOT EXISTS conversations (
    id              VARCHAR(36) NOT NULL,
    user_id         BIGINT NOT NULL,
    title           VARCHAR(255) NOT NULL DEFAULT '新对话',
    system_prompt   TEXT DEFAULT NULL,
    model_provider  VARCHAR(64) DEFAULT 'vllm',
    created_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    deleted_at      TIMESTAMP DEFAULT NULL,

    PRIMARY KEY (id),
    CONSTRAINT fk_conversations_user_id FOREIGN KEY (user_id)
        REFERENCES users (id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_conversations_user_id_updated
    ON conversations (user_id, updated_at DESC);

COMMENT ON TABLE conversations IS 'AI 会话/聊天室表';
COMMENT ON COLUMN conversations.id IS '会话ID (强力推荐使用 UUID)';
COMMENT ON COLUMN conversations.user_id IS '关联 users 表的主键';
COMMENT ON COLUMN conversations.title IS '对话标题 (通常由AI在第一轮对话后自动生成总结)';
COMMENT ON COLUMN conversations.system_prompt IS '当前会话专属的系统提示词 (用于设定特殊的 AI 人设或场景)';
COMMENT ON COLUMN conversations.model_provider IS '当前会话使用的模型后端 (例如 vllm, openai, anthropic)';
COMMENT ON COLUMN conversations.created_at IS '创建时间';
COMMENT ON COLUMN conversations.updated_at IS '最后更新时间 (用于左侧边栏将会话按最新活跃度排序)';
COMMENT ON COLUMN conversations.deleted_at IS '软删除标记 (用户删除对话时不物理删除，防止审计数据丢失)';
