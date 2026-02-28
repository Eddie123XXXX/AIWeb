-- 文档表 (documents) —— 防重、版本追踪、状态机
-- 依赖: 先执行 schema_users.sql
-- 执行: python -m db.run_schema

CREATE TABLE IF NOT EXISTS documents (
    id              VARCHAR(36)     NOT NULL,
    notebook_id     VARCHAR(36)     NOT NULL,
    user_id         BIGINT          NOT NULL,

    -- 基础与防重信息
    filename        VARCHAR(255)    NOT NULL,
    file_hash       CHAR(64)        NOT NULL,
    byte_size       BIGINT          NOT NULL,
    storage_path    VARCHAR(500)    NOT NULL,

    -- 解析引擎与策略溯源
    parser_engine       VARCHAR(64)     DEFAULT 'MinerU',
    parser_version      VARCHAR(32)     DEFAULT 'v1.0.0',
    chunking_strategy   VARCHAR(64)     DEFAULT 'semantic_recursive',

    -- 状态机与审计
    status          VARCHAR(20)     NOT NULL DEFAULT 'UPLOADED',
    error_log       TEXT            DEFAULT NULL,
    metadata        JSONB           DEFAULT NULL,

    created_at      TIMESTAMP       NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP       NOT NULL DEFAULT CURRENT_TIMESTAMP,

    PRIMARY KEY (id),
    CONSTRAINT fk_documents_user_id FOREIGN KEY (user_id)
        REFERENCES users (id) ON DELETE CASCADE
);

-- 同一笔记本下同一文件内容不允许重复解析
CREATE UNIQUE INDEX IF NOT EXISTS uk_documents_notebook_hash
    ON documents (notebook_id, file_hash);

-- 状态机查询加速
CREATE INDEX IF NOT EXISTS idx_documents_status
    ON documents (status);

-- 按笔记本查询
CREATE INDEX IF NOT EXISTS idx_documents_notebook
    ON documents (notebook_id);

-- 按用户查询
CREATE INDEX IF NOT EXISTS idx_documents_user
    ON documents (user_id);

-- 按哈希快速查重 (跨笔记本秒传)
CREATE INDEX IF NOT EXISTS idx_documents_file_hash
    ON documents (file_hash);

COMMENT ON TABLE documents IS '文档元数据表 (防重、版本追踪、状态机)';
COMMENT ON COLUMN documents.id IS '文档主键 UUID';
COMMENT ON COLUMN documents.notebook_id IS '所属笔记本 ID';
COMMENT ON COLUMN documents.user_id IS '上传者';
COMMENT ON COLUMN documents.filename IS '原文件名';
COMMENT ON COLUMN documents.file_hash IS '文件 SHA-256 哈希 (秒传和防重复解析)';
COMMENT ON COLUMN documents.byte_size IS '文件大小 (字节)';
COMMENT ON COLUMN documents.storage_path IS 'MinIO 物理路径';
COMMENT ON COLUMN documents.parser_engine IS '解析引擎标识';
COMMENT ON COLUMN documents.parser_version IS '引擎版本号 (方便回滚重解析)';
COMMENT ON COLUMN documents.chunking_strategy IS '切块策略';
COMMENT ON COLUMN documents.status IS '严格状态机: UPLOADED → PARSING → PARSED → EMBEDDING → READY / FAILED';
COMMENT ON COLUMN documents.error_log IS '失败时的详细堆栈信息';
COMMENT ON COLUMN documents.metadata IS '文档级元数据扩展 (作者、出处、语言等)';
