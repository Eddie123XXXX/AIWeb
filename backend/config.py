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
PROVIDER_CONFIGS = {
    "openai": {
        "display_name": "OpenAI  ChatGPT",
        "api_base": "https://api.openai.com/v1",
        "models": ["gpt-4", "gpt-4-turbo", "gpt-3.5-turbo"],
        "max_tokens": 16384,
        "model_max_tokens": {"gpt-4": 8192, "gpt-4-turbo": 4096, "gpt-3.5-turbo": 4096},
    },
    "anthropic": {
        "display_name": "Anthropic  Claude",
        "api_base": "https://api.anthropic.com/v1",
        "models": ["claude-3-opus", "claude-3-sonnet", "claude-3-haiku"],
        "max_tokens": 8192,
    },
    "deepseek": {
        "display_name": "DeepSeek",
        "api_base": "https://api.deepseek.com/v1",
        "models": ["deepseek-chat", "deepseek-coder"],
        "max_tokens": 8192,
    },
    "qwen": {
        "display_name": "通义千问  Qwen",
        "api_base": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "models": ["qwen-turbo", "qwen-plus", "qwen-max"],
        "max_tokens": 8192,
    },
    "zhipu": {
        "display_name": "智谱 GLM",
        "api_base": "https://open.bigmodel.cn/api/paas/v4",
        "models": ["glm-4", "glm-4-flash", "glm-3-turbo"],
        "max_tokens": 8192,
    },
    "moonshot": {
        "display_name": "月之暗面 Kimi",
        "api_base": "https://api.moonshot.cn/v1",
        "models": ["moonshot-v1-8k", "moonshot-v1-32k", "moonshot-v1-128k"],
        "max_tokens": 128000,
        "model_max_tokens": {"moonshot-v1-8k": 8192, "moonshot-v1-32k": 32768, "moonshot-v1-128k": 128000},
    },
    "gemini": {
        "display_name": "Google Gemini",
        "api_base": "https://generativelanguage.googleapis.com/v1beta/openai/",
        "models": ["gemini-2.0-flash", "gemini-1.5-pro", "gemini-1.5-flash", "gemini-1.0-pro"],
        "max_tokens": 8192,
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
