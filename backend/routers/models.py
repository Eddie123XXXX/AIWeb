"""
模型配置管理路由
"""
from fastapi import APIRouter, HTTPException
from typing import List
from models import ModelConfigCreate, ModelConfigResponse
from config import ModelConfig, PROVIDER_CONFIGS

router = APIRouter(prefix="/models", tags=["models"])

# 内存存储模型配置（生产环境应使用数据库）
model_configs: dict[str, ModelConfig] = {}


def mask_api_key(api_key: str) -> str:
    """隐藏 API Key 中间部分"""
    if len(api_key) <= 8:
        return "****"
    return f"{api_key[:4]}...{api_key[-4:]}"


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
