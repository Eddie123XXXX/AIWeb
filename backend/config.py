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


# 预定义的提供商配置；max_tokens 为该提供商/模型支持的最大输出 token 数
# 模型列表均为当前厂商最新/主推模型，并已设置对应 max_tokens
PROVIDER_CONFIGS = {
    "openai": {
        "display_name": "OpenAI  ChatGPT",
        "api_base": "https://api.openai.com/v1",
        "models": ["gpt-5.2", "gpt-5-mini", "gpt-4.1", "gpt-4o", "gpt-4o-mini"],
        "max_tokens": 16384,
        "model_max_tokens": {
            "gpt-5.2": 16384,
            "gpt-5-mini": 16384,
            "gpt-4.1": 16384,
            "gpt-4o": 16384,
            "gpt-4o-mini": 16384,
        },
    },
    "anthropic": {
        "display_name": "Anthropic  Claude",
        "api_base": "https://api.anthropic.com/v1",
        "models": ["claude-3-5-sonnet-20241022", "claude-3-5-haiku-20241022", "claude-3-opus-20240229"],
        "max_tokens": 8192,
    },
    "deepseek": {
        "display_name": "DeepSeek",
        "api_base": "https://api.deepseek.com/v1",
        "models": ["deepseek-chat", "deepseek-reasoner", "deepseek-coder"],
        "max_tokens": 8192,
    },
    "qwen": {
        "display_name": "通义千问  Qwen",
        "api_base": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "models": ["qwen-max", "qwen-plus", "qwen-turbo", "qwen-flash"],
        "max_tokens": 32768,
    },
    "zhipu": {
        "display_name": "智谱 GLM",
        "api_base": "https://open.bigmodel.cn/api/paas/v4",
        "models": ["glm-4-plus", "glm-4-flash", "glm-4-air"],
        "max_tokens": 8192,
    },
    "moonshot": {
        "display_name": "月之暗面 Kimi",
        "api_base": "https://api.moonshot.cn/v1",
        "models": ["kimi-latest", "kimi-k2-thinking", "moonshot-v1-128k", "moonshot-v1-1m"],
        "max_tokens": 128000,
        "model_max_tokens": {
            "kimi-latest": 128000,
            "kimi-k2-thinking": 128000,
            "moonshot-v1-128k": 128000,
            "moonshot-v1-1m": 128000,
        },
    },
    "gemini": {
        "display_name": "Google Gemini",
        "api_base": "https://generativelanguage.googleapis.com/v1beta/openai/",
        "models": ["gemini-2.5-pro", "gemini-2.5-flash", "gemini-2.5-flash-lite", "gemini-2.0-flash"],
        "max_tokens": 65536,
        "model_max_tokens": {
            "gemini-2.5-pro": 65536,
            "gemini-2.5-flash": 8192,
            "gemini-2.5-flash-lite": 8192,
            "gemini-2.0-flash": 8192,
        },
    },
    "custom": {
        "display_name": "自定义",
        "api_base": None,
        "models": [],
        "max_tokens": 8192,
    },
}


def get_max_tokens_for_model(provider: str, model_name: str) -> int:
    """返回该提供商/模型支持的最大输出 token 数；未知时返回 8192。"""
    conf = PROVIDER_CONFIGS.get(provider)
    if not conf:
        return 8192
    model_max = (conf.get("model_max_tokens") or {}).get(model_name)
    if model_max is not None:
        return model_max
    return conf.get("max_tokens", 8192)
