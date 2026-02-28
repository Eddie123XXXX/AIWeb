"""
RAG 知识库系统

模块职责:
- documents / document_chunks: PostgreSQL 元数据与溯源
- vector_store: Milvus 混合检索 (Dense + Sparse)
- chunking: 语义切块与 Parent-Child 结构
- embedding: 向量化服务封装
- service: 上传 → 防重 → 解析 → 切块 → 向量化 → 检索 全流程
- router: FastAPI HTTP 接口
"""
from .router import router

__all__ = ["router"]
