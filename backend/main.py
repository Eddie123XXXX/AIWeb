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
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

# 必须先加载 .env，再导入依赖环境变量的路由模块
load_dotenv()

from fastapi import HTTPException

from auth.router import router as auth_router
from routers import chat, history, models, user
from infra.minio import router as storage_router
from db.user_repository import hash_password, user_repository
from models import UserCreate, UserProfile
from routers.user import _dict_to_profile
from infra.redis import router as redis_router
from infra.postgres import router as postgres_router
from infra.rabbitmq import router as rabbitmq_router
from infra.elasticsearch import router as es_router

# Milvus 依赖 pymilvus，在 uvicorn --reload 子进程中可能缺少 pkg_resources，改为可选加载
try:
    from infra.milvus import router as milvus_router
except Exception as e:
    milvus_router = None
    print(f"⚠️ Milvus 路由未加载（可忽略）: {e}")


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
欢迎来到 AIWeb 的后端 API。这里是多模型对话、长期记忆、RAG 和 Quick Parse 背后的「控制中心」。🚀

## 功能特性

- 🤖 支持多种 LLM 提供商（OpenAI、Anthropic、DeepSeek、通义千问、Moonshot、智谱等）
- 🔑 灵活的 API Key 管理
- 💬 流式 / 非流式对话
- 🧠 长期记忆模块（Milvus + PostgreSQL）
- 📎 Quick Parse 文件解析（MinIO + 长上下文模型）
- 🔌 OpenAI 兼容接口设计（/api/chat, /api/models）

## 进度概览

- ✅ 对话历史持久化
- ✅ 长期记忆与混合召回（memory）
- ✅ 文件上传与 Quick Parse 解析
- ⏳ 知识库 RAG 工作流（进行中）
- ⏳ 用户系统与使用统计（规划中）

你可以：

- 直接在 Swagger 里试用接口；
- 把本服务当成「自托管的 OpenAI 兼容后端」接到自己的前端里。😄
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
app.include_router(models.router, prefix="/api")
app.include_router(user.router, prefix="/api/user")
app.include_router(storage_router, prefix="/api")
app.include_router(redis_router, prefix="/api")
app.include_router(postgres_router, prefix="/api")
if milvus_router is not None:
    app.include_router(milvus_router, prefix="/api")
app.include_router(rabbitmq_router, prefix="/api")
app.include_router(es_router, prefix="/api")


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
