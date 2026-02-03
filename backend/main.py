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

from routers import chat, models


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    print("🚀 AI 聊天平台启动中...")
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

## 快速开始

1. 先通过 `/api/models` 接口添加模型配置
2. 然后通过 `/api/chat` 接口发送消息

## 后续规划

- RAG 支持
- 多轮对话历史
- 文件上传解析
    """,
    version="1.0.0",
    lifespan=lifespan
)

# CORS 配置
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 生产环境应限制具体域名
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册路由
app.include_router(chat.router, prefix="/api")
app.include_router(models.router, prefix="/api")


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
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
