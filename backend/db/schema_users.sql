-- 用户表（与 MySQL 版语义一致，适配 PostgreSQL）
-- 执行: psql $DATABASE_URL -f db/schema_users.sql 或在迁移工具中执行

CREATE TABLE IF NOT EXISTS users (
    id              BIGSERIAL PRIMARY KEY,
    email           VARCHAR(255) NOT NULL,
    username        VARCHAR(64) DEFAULT NULL,
    phone_code      VARCHAR(10) DEFAULT NULL,
    phone_number    VARCHAR(20) DEFAULT NULL,
    password_hash   VARCHAR(255) NOT NULL,
    status          SMALLINT NOT NULL DEFAULT 1,
    last_login_ip   VARCHAR(45) DEFAULT NULL,
    last_login_at   TIMESTAMP DEFAULT NULL,
    created_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    deleted_at      TIMESTAMP DEFAULT NULL,

    CONSTRAINT uk_email UNIQUE (email)
);

-- 手机号唯一（仅当两者均非空时）
CREATE UNIQUE INDEX IF NOT EXISTS uk_phone ON users (phone_code, phone_number)
    WHERE phone_code IS NOT NULL AND phone_number IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_users_status ON users (status);
CREATE INDEX IF NOT EXISTS idx_users_created_at ON users (created_at);
CREATE INDEX IF NOT EXISTS idx_users_deleted_at ON users (deleted_at) WHERE deleted_at IS NOT NULL;

COMMENT ON TABLE users IS '核心用户账号表';
COMMENT ON COLUMN users.id IS '主键ID (分布式建议用雪花算法ID)';
COMMENT ON COLUMN users.email IS '登录邮箱';
COMMENT ON COLUMN users.username IS '用户名/昵称';
COMMENT ON COLUMN users.phone_code IS '国际区号，如 +86';
COMMENT ON COLUMN users.phone_number IS '手机号码';
COMMENT ON COLUMN users.password_hash IS '哈希密码 (bcrypt/argon2，不可存明文)';
COMMENT ON COLUMN users.status IS '状态: 0=禁用, 1=正常, 2=未激活, 3=锁定';
COMMENT ON COLUMN users.last_login_ip IS '最后登录IP (兼容IPv6)';
COMMENT ON COLUMN users.last_login_at IS '最后登录时间';
COMMENT ON COLUMN users.created_at IS '注册时间';
COMMENT ON COLUMN users.updated_at IS '最后更新时间';
COMMENT ON COLUMN users.deleted_at IS '软删除时间 (非NULL表示已注销)';
