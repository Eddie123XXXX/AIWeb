"""
AI 聊天平台后端
基于 FastAPI 构建的多模型 LLM 聊天服务
"""
from dotenv import load_dotenv
from fastapi import FastAPI
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
    # 打印已注册的路由，便于确认 /api/user/register、/api/models 等是否存在
    
    yield
    print("👋 AI 聊天平台已关闭")


app = FastAPI(
    title="AI 聊天平台",
    description="""
## 功能特性

- 🤖 支持多种 LLM 提供商（OpenAI、Anthropic、DeepSeek、通义千问、Moonshot、智谱等）
- 🔑 灵活的 API Key 管理
- 💬 流式/非流式对话
- 🔌 OpenAI 兼容接口

## 当前进展
用户界面

## 后续规划

- RAG 支持
- 多轮对话历史
- 文件上传解析
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
