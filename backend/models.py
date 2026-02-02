"""
数据模型定义
"""
from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime
from enum import Enum


class Role(str, Enum):
    """消息角色"""
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"


class Message(BaseModel):
    """单条消息"""
    role: Role
    content: str


class ChatRequest(BaseModel):
    """聊天请求"""
    model_id: str = Field(..., description="使用的模型配置ID")
    messages: List[Message] = Field(..., description="对话历史")
    stream: bool = Field(default=True, description="是否流式返回")
    temperature: Optional[float] = Field(default=None, description="温度参数，覆盖模型默认值")
    max_tokens: Optional[int] = Field(default=None, description="最大token数，覆盖模型默认值")


class ChatResponse(BaseModel):
    """非流式聊天响应"""
    content: str
    model: str
    usage: Optional[dict] = None


class ModelConfigCreate(BaseModel):
    """创建模型配置的请求"""
    id: str = Field(..., description="配置唯一标识")
    name: str = Field(..., description="显示名称")
    provider: str = Field(..., description="提供商: openai, anthropic, deepseek, qwen, moonshot, zhipu, custom")
    model_name: str = Field(..., description="实际模型名称")
    api_key: str = Field(..., description="API密钥")
    api_base: Optional[str] = Field(default=None, description="自定义API地址(custom提供商必填)")
    max_tokens: int = Field(default=4096, description="最大token数")
    temperature: float = Field(default=0.7, description="默认温度")


class ModelConfigResponse(BaseModel):
    """模型配置响应（隐藏API Key）"""
    id: str
    name: str
    provider: str
    model_name: str
    api_base: Optional[str]
    max_tokens: int
    temperature: float
    api_key_preview: str  # 只显示部分 key


class ConversationInfo(BaseModel):
    """对话信息"""
    id: str
    title: str
    model_id: str
    created_at: datetime
    updated_at: datetime
    message_count: int
