-- 切片表 (document_chunks) —— 支持 Parent-Child RAG 与多模态
-- 依赖: 先执行 schema_documents.sql
-- 执行: python -m db.run_schema

CREATE TABLE IF NOT EXISTS document_chunks (
    id              VARCHAR(36)     NOT NULL,
    document_id     VARCHAR(36)     NOT NULL,
    notebook_id     VARCHAR(36)     NOT NULL,

    -- Parent-Child 结构 (Auto-merging RAG)
    parent_chunk_id VARCHAR(36)     DEFAULT NULL,
    chunk_index     INT             NOT NULL,
    page_numbers    JSONB           NOT NULL DEFAULT '[]',
    chunk_type      VARCHAR(20)     NOT NULL DEFAULT 'TEXT',

    content         TEXT            NOT NULL,
    token_count     INT             NOT NULL DEFAULT 0,

    -- 软删除与并发控制
    is_active       BOOLEAN         NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMP       NOT NULL DEFAULT CURRENT_TIMESTAMP,

    PRIMARY KEY (id),
    CONSTRAINT fk_chunks_document_id FOREIGN KEY (document_id)
        REFERENCES documents (id) ON DELETE CASCADE
);

-- 按文档 + 激活状态查询
CREATE INDEX IF NOT EXISTS idx_chunks_doc_active
    ON document_chunks (document_id, is_active);

-- Parent-Child 查询加速
CREATE INDEX IF NOT EXISTS idx_chunks_parent
    ON document_chunks (parent_chunk_id);

-- 按笔记本查询
CREATE INDEX IF NOT EXISTS idx_chunks_notebook
    ON document_chunks (notebook_id);

-- 按文档 + 顺序查询
CREATE INDEX IF NOT EXISTS idx_chunks_doc_index
    ON document_chunks (document_id, chunk_index);

-- 全文搜索 GIN 索引 (三路召回 Path-1: 精确匹配)
-- 支持中英文混合 simple 配置; 生产环境可替换为 zhparser / pg_jieba 分词器
CREATE INDEX IF NOT EXISTS idx_chunks_content_fts
    ON document_chunks USING GIN (to_tsvector('simple', content));

-- ILIKE 前缀/正则匹配加速 (pg_trgm 扩展)
-- 需先执行: CREATE EXTENSION IF NOT EXISTS pg_trgm;
-- CREATE INDEX IF NOT EXISTS idx_chunks_content_trgm
--     ON document_chunks USING GIN (content gin_trgm_ops);

COMMENT ON TABLE document_chunks IS '文档切片表 (Parent-Child RAG + 多模态)';
COMMENT ON COLUMN document_chunks.id IS '切片 ID (严格对应 Milvus PK)';
COMMENT ON COLUMN document_chunks.document_id IS '所属文档 ID';
COMMENT ON COLUMN document_chunks.notebook_id IS '所属笔记本 ID';
COMMENT ON COLUMN document_chunks.parent_chunk_id IS '父切片 ID (Auto-merging RAG: 小块召回, 大块给 LLM)';
COMMENT ON COLUMN document_chunks.chunk_index IS '文档内物理顺序';
COMMENT ON COLUMN document_chunks.page_numbers IS '来源页码 (如 [12, 13], 前端精准跳转)';
COMMENT ON COLUMN document_chunks.chunk_type IS '切片类型: TEXT / TABLE / IMAGE_CAPTION';
COMMENT ON COLUMN document_chunks.content IS 'Markdown 内容';
COMMENT ON COLUMN document_chunks.token_count IS 'Token 量 (组装 Prompt 时计算剩余窗口)';
COMMENT ON COLUMN document_chunks.is_active IS 'FALSE=已废弃, TRUE=生效 (重新解析时旧切片标 FALSE, 不物理删除)';
