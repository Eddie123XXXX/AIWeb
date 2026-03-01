"""
AI 聊天平台后端
基于 FastAPI 构建的多模型 LLM 聊天服务
"""
import logging
import sys

from dotenv import load_dotenv
from fastapi import FastAPI

# 配置记忆模块日志，确保 [Memory] 输出到终端
_mem_log = logging.getLogger("memory")
_mem_log.setLevel(logging.INFO)
if not _mem_log.handlers:
    _h = logging.StreamHandler(sys.stdout)
    _h.setFormatter(logging.Formatter("%(message)s"))
    _mem_log.addHandler(_h)

# 配置 RAG 模块日志，确保 [RAG] 解析/切块/向量化过程输出到终端
for _name in ("rag.router", "rag.service", "rag.tasks"):
    _rag_log = logging.getLogger(_name)
    _rag_log.setLevel(logging.INFO)
    if not _rag_log.handlers:
        _h = logging.StreamHandler(sys.stdout)
        _h.setFormatter(logging.Formatter("%(message)s"))
        _rag_log.addHandler(_h)
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

# 必须先加载 .env，再导入依赖环境变量的路由模块
load_dotenv()

from fastapi import HTTPException

from auth.router import router as auth_router
from routers import asr, chat, history, memory as memory_router, models, user
from infra.minio import router as storage_router
from db.user_repository import hash_password, user_repository
from models import UserCreate, UserProfile
from routers.user import _dict_to_profile
from infra.redis import router as redis_router
from infra.postgres import router as postgres_router
from infra.rabbitmq import router as rabbitmq_router
from infra.elasticsearch import router as es_router
from infra.mineru.router import router as mineru_router

# Milvus 依赖 pymilvus，在 uvicorn --reload 子进程中可能缺少 pkg_resources，改为可选加载
try:
    from infra.milvus import router as milvus_router
except Exception as e:
    milvus_router = None
    print(f"⚠️ Milvus 路由未加载（可忽略）: {e}")

# RAG 知识库模块
try:
    from rag import router as rag_router
except Exception as e:
    rag_router = None
    print(f"⚠️ RAG 路由未加载（可忽略）: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    print("🚀 AI 聊天平台启动中...")
    # 预加载记忆模块，确保启动时打印模块就绪
    try:
        import memory  # noqa: F401
        print("[Memory] 记忆模块已就绪（extract/store, retrieve, compress, reflection, forget）")
    except Exception as e:
        print(f"[Memory] 记忆模块加载异常（可忽略）: {e}")

    yield
    print("👋 AI 聊天平台已关闭")


app = FastAPI(
    title="AI 聊天平台 🧠",
    description="""
欢迎来到 AIWeb 的后端 API。多模型对话、长期记忆、RAG 知识库与 Quick Parse 均由本服务统一编排。

## 功能特性

- 🤖 多模型：OpenAI、Anthropic、DeepSeek、通义千问、Moonshot、智谱等（OpenAI 兼容）
- 💬 流式/非流式对话：WebSocket `/api/chat/ws`，支持 conversation_id、rag_context、quick_parse_files
- 🧠 长期记忆：打分写入、三维混合召回（语义+时间衰减+重要性）、反思与遗忘（见 memory 模块）
- 📎 Quick Parse：MinIO 上传，解析为 Markdown 仅注入当轮上下文，不写入记忆/知识库
- 📚 RAG 知识库：上传→解析→版面感知切块→Dense+Sparse 向量化→三段式检索；`/api/rag/search` 支持 document_ids 限定范围；文档总结（来源指南）入库，大文档截断后生成

## 实现流程概览

1. **对话**：前端 WebSocket 发消息 → 解析会话与历史（Redis/PostgreSQL）→ 记忆召回 + 可选 RAG 上下文 + Quick Parse 内容拼入 system → LLM 流式返回 → 落库并异步写入记忆。
2. **RAG 检索**：`POST /api/rag/search` 三路召回（精确+FTS、Sparse、Dense）→ RRF 融合 → Reranker 精排 → Parent-Child 溯源返回；前端可将结果注入下次对话的 rag_context。
3. **文档入库**：`POST /api/rag/documents/upload` 防重/秒传 → `POST /api/rag/documents/{id}/process` 解析→切块→向量化；`GET /api/rag/documents/{id}/markdown` 返回片段与来源指南（无则生成并入库）。

## 技术栈

- FastAPI、WebSocket、OpenAPI/Swagger
- PostgreSQL（用户/会话/消息/记忆/文档与切片）、Redis（缓存/会话）、MinIO（对象）、Milvus（向量）
- 详见各模块 README：`backend/README.md`、`backend/rag/README.md`、`backend/memory/README.md`

在 Swagger 中可直接调试各接口；也可将本服务作为自托管 OpenAI 兼容后端使用。
    """,
    version="1.0.0",
    lifespan=lifespan
)

# 先挂载关键 API，确保即使子路由异常也能响应（/ping 与 /api/ping 均可探活）
@app.get("/ping", tags=["debug"])
async def ping_root():
    return {"pong": True, "message": "backend ok"}

@app.get("/api/ping", tags=["debug"])
async def api_ping():
    return {"pong": True, "message": "backend ok"}


@app.post("/api/user/register", response_model=UserProfile, tags=["user"], summary="注册")
async def api_register(body: UserCreate):
    """邮箱注册。"""
    email = body.email.strip().lower()
    if await user_repository.get_by_email(email):
        raise HTTPException(status_code=400, detail="该邮箱已注册")
    password_hash = hash_password(body.password)
    u = await user_repository.create(
        email=email,
        password_hash=password_hash,
        username=body.username,
        phone_code=body.phone_code,
        phone_number=body.phone_number,
        status=1,
    )
    return _dict_to_profile(u)


# CORS 配置：allow_credentials=True 时不能使用 allow_origins=["*"]，否则浏览器会拦截
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://192.168.3.38:5173",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册路由
app.include_router(auth_router, prefix="/api")
app.include_router(chat.router, prefix="/api")
app.include_router(history.router, prefix="/api")
app.include_router(asr.router, prefix="/api")
app.include_router(memory_router.router, prefix="/api")
app.include_router(models.router, prefix="/api")
app.include_router(user.router, prefix="/api/user")
app.include_router(storage_router, prefix="/api")
app.include_router(redis_router, prefix="/api")
app.include_router(postgres_router, prefix="/api")
if milvus_router is not None:
    app.include_router(milvus_router, prefix="/api")
app.include_router(rabbitmq_router, prefix="/api")
app.include_router(es_router, prefix="/api")
app.include_router(mineru_router, prefix="/api")
if rag_router is not None:
    app.include_router(rag_router, prefix="/api")
else:
    # RAG 模块未加载时的后备路由，避免前端 404
    @app.get("/api/rag/notebooks", tags=["rag"])
    async def _rag_notebooks_fallback():
        return []

    @app.post("/api/rag/notebooks", tags=["rag"])
    async def _rag_create_notebook_fallback():
        from fastapi.responses import JSONResponse
        return JSONResponse(
            status_code=503,
            content={"detail": "RAG 模块未加载，请检查后端日志（notebooks 表、依赖等）并重启后端"},
        )


@app.get("/", tags=["root"])
async def root():
    """根路径"""
    return {
        "message": "欢迎使用 AI 聊天平台",
        "docs": "/docs",
        "version": "1.0.0"
    }


@app.get("/health", tags=["health"])
async def health_check():
    """健康检查"""
    return {"status": "healthy"}


if __name__ == "__main__":
    import uvicorn
    # Windows 下 --reload 子进程可能收不到请求，默认不用 reload；需热重载可改为 reload=True
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=False)
