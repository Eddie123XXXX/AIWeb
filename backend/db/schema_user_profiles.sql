-- 用户资料扩展表（与 MySQL 版语义一致，适配 PostgreSQL）
-- 依赖: 先执行 schema_users.sql。执行: psql $DATABASE_URL -f db/schema_user_profiles.sql

CREATE TABLE IF NOT EXISTS user_profiles (
    user_id         BIGINT NOT NULL,
    nickname        VARCHAR(64) DEFAULT NULL,
    avatar_url      VARCHAR(255) DEFAULT NULL,
    bio             VARCHAR(500) DEFAULT NULL,
    gender          SMALLINT DEFAULT 0,
    birthday        DATE DEFAULT NULL,
    location        VARCHAR(100) DEFAULT NULL,
    website         VARCHAR(255) DEFAULT NULL,
    preferences     JSONB DEFAULT NULL,
    created_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    PRIMARY KEY (user_id),
    CONSTRAINT fk_profile_user_id FOREIGN KEY (user_id)
        REFERENCES users (id) ON DELETE CASCADE
);

COMMENT ON TABLE user_profiles IS '用户资料扩展表';
COMMENT ON COLUMN user_profiles.user_id IS '关联 users 表的主键 ID，同时作为本表主键';
COMMENT ON COLUMN user_profiles.nickname IS '展示昵称';
COMMENT ON COLUMN user_profiles.avatar_url IS '头像链接 (MinIO Object Key 或完整 URL)';
COMMENT ON COLUMN user_profiles.bio IS '个人简介/个性签名';
COMMENT ON COLUMN user_profiles.gender IS '性别: 0=保密/未知, 1=男, 2=女, 9=其他';
COMMENT ON COLUMN user_profiles.birthday IS '生日';
COMMENT ON COLUMN user_profiles.location IS '所在地区';
COMMENT ON COLUMN user_profiles.website IS '个人网站或 Github 链接';
COMMENT ON COLUMN user_profiles.preferences IS '用户偏好 (JSON: 主题、语言、默认 AI 模型等)';
COMMENT ON COLUMN user_profiles.created_at IS '创建时间';
COMMENT ON COLUMN user_profiles.updated_at IS '最后更新时间';
