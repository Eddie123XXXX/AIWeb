-- 第三方授权登录表（与 MySQL 版语义一致，适配 PostgreSQL）
-- 依赖: 先执行 schema_users.sql。执行: psql $DATABASE_URL -f db/schema_user_oauths.sql

CREATE TABLE IF NOT EXISTS user_oauths (
    id              BIGSERIAL PRIMARY KEY,
    user_id         BIGINT NOT NULL,
    provider        VARCHAR(32) NOT NULL,
    provider_uid    VARCHAR(255) NOT NULL,
    provider_data   JSONB DEFAULT NULL,
    created_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT uk_provider_uid UNIQUE (provider, provider_uid),
    CONSTRAINT fk_oauth_user_id FOREIGN KEY (user_id)
        REFERENCES users (id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_user_oauths_user_id ON user_oauths (user_id);

COMMENT ON TABLE user_oauths IS '第三方授权登录表';
COMMENT ON COLUMN user_oauths.user_id IS '关联核心 users 表的主键 ID';
COMMENT ON COLUMN user_oauths.provider IS '第三方平台名称 (google, wechat, github, apple 等)';
COMMENT ON COLUMN user_oauths.provider_uid IS '第三方平台唯一用户 ID (如 Google sub, 微信 unionid)';
COMMENT ON COLUMN user_oauths.provider_data IS '第三方返回的冗余信息 (头像、昵称等)';
COMMENT ON COLUMN user_oauths.created_at IS '创建时间';
COMMENT ON COLUMN user_oauths.updated_at IS '最后更新时间';
