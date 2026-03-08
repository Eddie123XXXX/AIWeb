-- 深度研究（Deep Research）会话表，与 conversations 分离，前端召回历史时与聊天对话互不冲突。
-- 依赖: 先执行 schema_users.sql。
-- 执行: psql $DATABASE_URL -f db/schema_research_sessions.sql

CREATE TABLE IF NOT EXISTS research_sessions (
    id              VARCHAR(36) NOT NULL,
    user_id         BIGINT NOT NULL,
    query           TEXT NOT NULL,
    title           VARCHAR(255) NOT NULL DEFAULT '',
    status          VARCHAR(32) NOT NULL DEFAULT 'running',
    final_report    TEXT DEFAULT NULL,
    sources         JSONB DEFAULT NULL,
    ui_state        JSONB DEFAULT NULL,
    created_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    deleted_at      TIMESTAMP DEFAULT NULL,

    PRIMARY KEY (id),
    CONSTRAINT fk_research_sessions_user_id FOREIGN KEY (user_id)
        REFERENCES users (id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_research_sessions_user_id_updated
    ON research_sessions (user_id, updated_at DESC);

CREATE INDEX IF NOT EXISTS idx_research_sessions_status
    ON research_sessions (user_id, status) WHERE deleted_at IS NULL;

COMMENT ON TABLE research_sessions IS '深度研究会话表，与聊天会话 conversations 分离';
COMMENT ON COLUMN research_sessions.id IS '会话ID，与 Deep Research 流式请求的 session_id 一致（推荐 UUID）';
COMMENT ON COLUMN research_sessions.user_id IS '关联 users 表主键';
COMMENT ON COLUMN research_sessions.query IS '用户发起的研究问题';
COMMENT ON COLUMN research_sessions.title IS '列表展示用标题，通常为 query 摘要或自动生成';
COMMENT ON COLUMN research_sessions.status IS 'running | completed | failed | cancelled';
COMMENT ON COLUMN research_sessions.final_report IS '完成时的报告正文快照，未完成或失败时为空';
COMMENT ON COLUMN research_sessions.sources IS '研究来源列表 JSON，与 research_complete 事件中的 references 一致';
COMMENT ON COLUMN research_sessions.ui_state IS '思考过程与 UI 状态：outline、panel_log、chart_count 等，用于刷新后恢复';
COMMENT ON COLUMN research_sessions.created_at IS '创建时间';
COMMENT ON COLUMN research_sessions.updated_at IS '最后更新时间（列表按此排序）';
COMMENT ON COLUMN research_sessions.deleted_at IS '软删除标记';
