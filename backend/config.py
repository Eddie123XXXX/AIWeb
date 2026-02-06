"""
配置管理模块
支持多个 LLM 提供商的配置
"""
from pydantic import BaseModel, ConfigDict
from typing import Optional


class ModelConfig(BaseModel):
    """单个模型的配置"""
    id: str
    name: str
    provider: str  # openai, anthropic, deepseek, qwen, etc.
    model_name: str  # 实际调用的模型名称
    api_key: str
    api_base: Optional[str] = None  # 自定义 API 地址
    max_tokens: int = 4096
    temperature: float = 0.7
    
    # 关闭受保护命名空间限制，允许使用 model_id / model_name 等字段名
    model_config = ConfigDict(protected_namespaces=())


# 预定义的提供商配置
PROVIDER_CONFIGS = {
    "openai": {
        "display_name": "OpenAI  GPT",
        "api_base": "https://api.openai.com/v1",
        "models": ["gpt-4", "gpt-4-turbo", "gpt-3.5-turbo"]
    },
    "anthropic": {
        "display_name": "Anthropic  Claude",
        "api_base": "https://api.anthropic.com/v1",
        "models": ["claude-3-opus", "claude-3-sonnet", "claude-3-haiku"]
    },
    "deepseek": {
        "display_name": "DeepSeek",
        "api_base": "https://api.deepseek.com/v1",
        "models": ["deepseek-chat", "deepseek-coder"]
    },
    "qwen": {
        "display_name": "通义千问  Qwen",
        "api_base": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "models": ["qwen-turbo", "qwen-plus", "qwen-max"]
    },
    "zhipu": {
        "display_name": "智谱 GLM",
        "api_base": "https://open.bigmodel.cn/api/paas/v4",
        "models": ["glm-4", "glm-4-flash", "glm-3-turbo"]
    },
    "moonshot": {
        "display_name": "月之暗面 Kimi",
        "api_base": "https://api.moonshot.cn/v1",
        "models": ["moonshot-v1-8k", "moonshot-v1-32k", "moonshot-v1-128k"]
    },
    "gemini": {
        "display_name": "Google Gemini",
        "api_base": "https://generativelanguage.googleapis.com/v1beta/openai/",
        "models": ["gemini-2.0-flash", "gemini-1.5-pro", "gemini-1.5-flash", "gemini-1.0-pro"]
    },
    "custom": {
        "display_name": "自定义",
        "api_base": None,
        "models": []
    }
}
