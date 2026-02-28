-- 笔记本表 (notebooks) —— RAG 知识库的顶层容器
-- 依赖: schema_users.sql
-- 执行: python -m db.run_schema

CREATE TABLE IF NOT EXISTS notebooks (
    id              VARCHAR(36)     NOT NULL,
    title           VARCHAR(255)   NOT NULL DEFAULT '未命名笔记本',
    user_id         BIGINT          NOT NULL,

    created_at      TIMESTAMP       NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP       NOT NULL DEFAULT CURRENT_TIMESTAMP,

    PRIMARY KEY (id),
    CONSTRAINT fk_notebooks_user_id FOREIGN KEY (user_id)
        REFERENCES users (id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_notebooks_user
    ON notebooks (user_id);

COMMENT ON TABLE notebooks IS 'RAG 知识库笔记本表';
COMMENT ON COLUMN notebooks.id IS '笔记本主键 UUID';
COMMENT ON COLUMN notebooks.title IS '笔记本标题';
COMMENT ON COLUMN notebooks.user_id IS '所属用户';
