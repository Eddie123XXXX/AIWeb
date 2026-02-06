"""
模型配置管理路由
"""
import os
from typing import List

from fastapi import APIRouter, HTTPException

from models import ModelConfigCreate, ModelConfigResponse
from config import ModelConfig, PROVIDER_CONFIGS

router = APIRouter(prefix="/models", tags=["models"])

    # 内存存储模型配置（生产环境应使用数据库）
model_configs: dict[str, ModelConfig] = {}


def _init_default_model_from_env() -> None:
    """
    从环境变量中加载一个“默认模型配置”（可选）

    相关环境变量：
    - DEFAULT_MODEL_ID
    - DEFAULT_MODEL_NAME
    - DEFAULT_MODEL_PROVIDER
    - DEFAULT_MODEL_MODEL_NAME
    - DEFAULT_MODEL_API_KEY
    - DEFAULT_MODEL_API_BASE
    - DEFAULT_MODEL_MAX_TOKENS
    - DEFAULT_MODEL_TEMPERATURE
    """
    model_id = os.getenv("DEFAULT_MODEL_ID")
    if not model_id:
        return

    # 已存在则不重复创建
    if model_id in model_configs:
        return

    provider = os.getenv("DEFAULT_MODEL_PROVIDER")
    name = os.getenv("DEFAULT_MODEL_NAME") or model_id
    model_name = os.getenv("DEFAULT_MODEL_MODEL_NAME")
    api_key = os.getenv("DEFAULT_MODEL_API_KEY")
    api_base = os.getenv("DEFAULT_MODEL_API_BASE") or None

    if not provider or not model_name or not api_key:
        # 配置不完整时直接跳过，避免启动失败
        return

    try:
        max_tokens = int(os.getenv("DEFAULT_MODEL_MAX_TOKENS", "4096"))
    except ValueError:
        max_tokens = 4096

    try:
        temperature = float(os.getenv("DEFAULT_MODEL_TEMPERATURE", "0.7"))
    except ValueError:
        temperature = 0.7

    config = ModelConfig(
        id=model_id,
        name=name,
        provider=provider,
        model_name=model_name,
        api_key=api_key,
        api_base=api_base,
        max_tokens=max_tokens,
        temperature=temperature,
    )

    model_configs[model_id] = config


def _init_provider_models_from_env() -> None:
    """
    根据各家 provider 的 API Key，预配置一批常用模型。

    - 如果环境变量中存在对应 provider 的 API Key，且尚未为该 provider 创建配置，
      则自动创建一个默认模型配置。
    - 实际可用模型名称来自 config.PROVIDER_CONFIGS 中的 models 列表。
    """
    # provider: (env_key, default_config_id)
    PROVIDER_ENV_KEYS: dict[str, tuple[str, str]] = {
        "openai": ("OPENAI_API_KEY", "openai-default"),
        "anthropic": ("ANTHROPIC_API_KEY", "anthropic-default"),
        "deepseek": ("DEEPSEEK_API_KEY", "deepseek-default"),
        "qwen": ("QWEN_API_KEY", "qwen-default"),
        "moonshot": ("MOONSHOT_API_KEY", "moonshot-default"),
        "zhipu": ("ZHIPU_API_KEY", "zhipu-default"),
        "gemini": ("GEMINI_API_KEY", "gemini-default"),
    }

    for provider, (env_key, default_id) in PROVIDER_ENV_KEYS.items():
        api_key = os.getenv(env_key)
        if not api_key:
            continue

        # 如果已经有同名配置（或者通过 DEFAULT_MODEL_* 创建了同 provider 的配置），就跳过
        if default_id in model_configs:
            continue

        provider_conf = PROVIDER_CONFIGS.get(provider) or {}
        models = provider_conf.get("models") or []
        if not models:
            # 没有预设模型列表时，交给用户通过 /api/models 自己添加
            continue

        # 这里简单地取该 provider 的第一个预设模型作为默认模型名
        model_name = models[0]
        name = f"{provider_conf.get('display_name', provider).title()} {model_name}".strip()
        api_base = provider_conf.get("api_base")

        config = ModelConfig(
            id=default_id,
            name=name,
            provider=provider,
            model_name=model_name,
            api_key=api_key,
            api_base=api_base,
            max_tokens=4096,
            temperature=0.7,
        )

        model_configs[default_id] = config


# 模块导入时尝试从环境变量中预加载默认模型和各 provider 的默认配置
_init_default_model_from_env()
_init_provider_models_from_env()


def mask_api_key(api_key: str) -> str:
    """隐藏 API Key 中间部分"""
    if len(api_key) <= 8:
        return "****"
    return f"{api_key[:4]}...{api_key[-4:]}"


def _display_name(provider: str) -> str:
    """从 PROVIDER_CONFIGS 取 display_name，供前端仅展示提供商名称"""
    return (PROVIDER_CONFIGS.get(provider) or {}).get("display_name", provider)


@router.get("/providers", summary="获取支持的提供商列表")
async def get_providers():
    """获取所有支持的 LLM 提供商及其预设模型"""
    return PROVIDER_CONFIGS


@router.post("", response_model=ModelConfigResponse, summary="添加模型配置")
async def add_model_config(config: ModelConfigCreate):
    """添加新的模型配置"""
    if config.id in model_configs:
        raise HTTPException(status_code=400, detail=f"模型配置 ID '{config.id}' 已存在")
    
    # 验证 provider
    if config.provider not in PROVIDER_CONFIGS:
        raise HTTPException(
            status_code=400, 
            detail=f"不支持的提供商: {config.provider}。支持的提供商: {list(PROVIDER_CONFIGS.keys())}"
        )
    
    # custom 提供商必须提供 api_base
    if config.provider == "custom" and not config.api_base:
        raise HTTPException(status_code=400, detail="custom 提供商必须提供 api_base")
    
    model_config = ModelConfig(
        id=config.id,
        name=config.name,
        provider=config.provider,
        model_name=config.model_name,
        api_key=config.api_key,
        api_base=config.api_base,
        max_tokens=config.max_tokens,
        temperature=config.temperature
    )
    
    model_configs[config.id] = model_config
    
    return ModelConfigResponse(
        id=model_config.id,
        name=model_config.name,
        display_name=_display_name(model_config.provider),
        provider=model_config.provider,
        model_name=model_config.model_name,
        api_base=model_config.api_base,
        max_tokens=model_config.max_tokens,
        temperature=model_config.temperature,
        api_key_preview=mask_api_key(model_config.api_key)
    )


@router.get("", response_model=List[ModelConfigResponse], summary="获取所有模型配置")
async def list_model_configs():
    """获取所有已配置的模型"""
    return [
        ModelConfigResponse(
            id=config.id,
            name=config.name,
            display_name=_display_name(config.provider),
            provider=config.provider,
            model_name=config.model_name,
            api_base=config.api_base,
            max_tokens=config.max_tokens,
            temperature=config.temperature,
            api_key_preview=mask_api_key(config.api_key)
        )
        for config in model_configs.values()
    ]


@router.get("/{model_id}", response_model=ModelConfigResponse, summary="获取单个模型配置")
async def get_model_config(model_id: str):
    """获取指定模型配置"""
    if model_id not in model_configs:
        raise HTTPException(status_code=404, detail=f"模型配置 '{model_id}' 不存在")
    
    config = model_configs[model_id]
    return ModelConfigResponse(
        id=config.id,
        name=config.name,
        display_name=_display_name(config.provider),
        provider=config.provider,
        model_name=config.model_name,
        api_base=config.api_base,
        max_tokens=config.max_tokens,
        temperature=config.temperature,
        api_key_preview=mask_api_key(config.api_key)
    )


@router.delete("/{model_id}", summary="删除模型配置")
async def delete_model_config(model_id: str):
    """删除指定模型配置"""
    if model_id not in model_configs:
        raise HTTPException(status_code=404, detail=f"模型配置 '{model_id}' 不存在")
    
    del model_configs[model_id]
    return {"message": f"模型配置 '{model_id}' 已删除"}


@router.put("/{model_id}", response_model=ModelConfigResponse, summary="更新模型配置")
async def update_model_config(model_id: str, config: ModelConfigCreate):
    """更新模型配置"""
    if model_id not in model_configs:
        raise HTTPException(status_code=404, detail=f"模型配置 '{model_id}' 不存在")
    
    # 如果更改了 ID，检查新 ID 是否已存在
    if config.id != model_id and config.id in model_configs:
        raise HTTPException(status_code=400, detail=f"模型配置 ID '{config.id}' 已存在")
    
    # 删除旧配置
    del model_configs[model_id]
    
    # 创建新配置
    model_config = ModelConfig(
        id=config.id,
        name=config.name,
        provider=config.provider,
        model_name=config.model_name,
        api_key=config.api_key,
        api_base=config.api_base,
        max_tokens=config.max_tokens,
        temperature=config.temperature
    )
    
    model_configs[config.id] = model_config
    
    return ModelConfigResponse(
        id=model_config.id,
        name=model_config.name,
        display_name=_display_name(model_config.provider),
        provider=model_config.provider,
        model_name=model_config.model_name,
        api_base=model_config.api_base,
        max_tokens=model_config.max_tokens,
        temperature=model_config.temperature,
        api_key_preview=mask_api_key(model_config.api_key)
    )


def get_model_config_by_id(model_id: str) -> ModelConfig:
    """获取模型配置（供其他模块使用）"""
    if model_id not in model_configs:
        raise HTTPException(status_code=404, detail=f"模型配置 '{model_id}' 不存在")
    return model_configs[model_id]
