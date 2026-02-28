"""
RAG 系统 Pydantic 数据模型

包含请求体、响应体以及内部传输对象。
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# 枚举
# ---------------------------------------------------------------------------

class DocumentStatus(str, Enum):
    UPLOADED = "UPLOADED"
    PARSING = "PARSING"
    PARSED = "PARSED"
    EMBEDDING = "EMBEDDING"
    READY = "READY"
    FAILED = "FAILED"


class ChunkType(str, Enum):
    TEXT = "TEXT"
    TABLE = "TABLE"
    IMAGE_CAPTION = "IMAGE_CAPTION"
    CODE = "CODE"


# ---------------------------------------------------------------------------
# 笔记本
# ---------------------------------------------------------------------------

class NotebookCreate(BaseModel):
    """创建笔记本请求"""
    title: str = Field(default="未命名笔记本", max_length=255)


class NotebookOut(BaseModel):
    """笔记本列表/详情响应"""
    id: str
    title: str
    user_id: int
    source_count: int = 0
    last_updated: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# 文档
# ---------------------------------------------------------------------------

class DocumentCreate(BaseModel):
    """上传文档时前端传递的元信息（文件本身通过 multipart 传）"""
    notebook_id: str = Field(..., max_length=36, description="目标笔记本 ID")


class DocumentOut(BaseModel):
    id: str
    notebook_id: str
    user_id: int
    filename: str
    file_hash: str
    byte_size: int
    storage_path: str
    parser_engine: Optional[str] = "MinerU"
    parser_version: Optional[str] = "v1.0.0"
    chunking_strategy: Optional[str] = "semantic_recursive"
    status: DocumentStatus
    error_log: Optional[str] = None
    metadata: Optional[dict[str, Any]] = None
    created_at: datetime
    updated_at: datetime


class DocumentBrief(BaseModel):
    """文档列表中的简要信息"""
    id: str
    filename: str
    byte_size: int
    status: DocumentStatus
    created_at: datetime


# ---------------------------------------------------------------------------
# 切片
# ---------------------------------------------------------------------------

class ChunkOut(BaseModel):
    id: str
    document_id: str
    notebook_id: str
    parent_chunk_id: Optional[str] = None
    chunk_index: int
    page_numbers: list[int] = []
    chunk_type: ChunkType
    content: str
    token_count: int
    is_active: bool = True
    created_at: datetime


# ---------------------------------------------------------------------------
# 检索
# ---------------------------------------------------------------------------

class SearchRequest(BaseModel):
    """三段式检索请求"""
    notebook_id: str = Field(..., description="笔记本 ID (分区隔离)")
    query: str = Field(..., min_length=1, description="检索问题")
    document_ids: Optional[list[str]] = Field(None, description="限定文档范围")
    chunk_types: Optional[list[ChunkType]] = Field(None, description="限定切片类型")
    top_k: Optional[int] = Field(
        None,
        ge=1,
        le=50,
        description="Reranker 安全上限，None 表示仅按及格线过滤、不设上限",
    )
    use_parent: bool = Field(True, description="是否启用 Parent-Child 上下文扩展")
    enable_exact: bool = Field(True, description="Path-1: 是否启用 PostgreSQL 精确匹配")
    enable_sparse: bool = Field(True, description="Path-2: 是否启用 Milvus 稀疏向量检索")
    enable_dense: bool = Field(True, description="Path-3: 是否启用 Milvus 稠密向量检索")
    enable_rerank: bool = Field(True, description="是否启用 Reranker 精排 (第三段)")
    rerank_threshold: Optional[float] = Field(
        None,
        ge=0.0,
        le=1.0,
        description="Jina Cross-Encoder 及格线 (0~1)，低于此分丢弃；None 表示不过滤",
    )
    fallback_cosine_threshold: Optional[float] = Field(
        None,
        ge=0.0,
        le=1.0,
        description="Embedding 降级时余弦相似度及格线 (通常 0.8~0.95)；None 表示不过滤",
    )


class SearchHit(BaseModel):
    """单条检索命中"""
    chunk_id: str
    document_id: str
    content: str
    chunk_type: ChunkType
    page_numbers: list[int] = []
    score: float = Field(description="RRF 融合分或 Reranker 分")
    rerank_score: Optional[float] = Field(None, description="Reranker 精排分数 (若启用)")
    sources: list[str] = Field(default_factory=list, description="命中来源: exact / sparse / dense")
    parent_content: Optional[str] = None


class SearchResponse(BaseModel):
    """三段式检索结果"""
    query: str
    hits: list[SearchHit]
    total: int
    path_stats: dict[str, int] = Field(
        default_factory=dict,
        description="各路召回命中数: {exact, sparse, dense, rrf_top, rerank_top}",
    )
