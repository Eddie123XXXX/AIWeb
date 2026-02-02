"""
Vercel Serverless Function 入口文件
"""
import sys
from pathlib import Path

# 将父目录添加到 Python 路径，以便导入项目模块
sys.path.append(str(Path(__file__).parent.parent))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from routers import chat, models

# 创建 FastAPI 应用（Vercel 不支持 lifespan，使用简化版本）
app = FastAPI(
    title="AI 聊天平台",
    description="多模型 LLM 聊天服务 API",
    version="1.0.0"
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
        "version": "1.0.0",
        "platform": "Vercel"
    }


@app.get("/health", tags=["health"])
async def health_check():
    """健康检查"""
    return {"status": "healthy"}


# Vercel 需要的 handler（可选，FastAPI 会自动处理）
handler = app
