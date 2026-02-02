"""
Vercel Serverless Function 入口文件
使用 Mangum 适配器将 FastAPI 转换为 AWS Lambda/Vercel 兼容格式
"""
import sys
import os

# 将父目录添加到 Python 路径
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from mangum import Mangum
from routers import chat, models

# 创建 FastAPI 应用
app = FastAPI(
    title="AI 聊天平台",
    description="多模型 LLM 聊天服务 API",
    version="1.0.0"
)

# CORS 配置
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
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


# 使用 Mangum 适配器 - 这是 Vercel 需要的格式
handler = Mangum(app, lifespan="off")
