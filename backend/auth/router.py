"""认证路由：登录（邮箱密码 + 第三方 OAuth）、绑定"""
import re
import secrets

from fastapi import APIRouter, Depends, HTTPException, Request
from typing import Annotated

from auth.dependencies import get_current_user_id
from db.oauth_repository import oauth_repository
from db.profile_repository import profile_repository
from db.user_repository import hash_password, user_repository, verify_password
from models import (
    LoginRequest,
    LoginResponse,
    LoginUserInfo,
    OAuthBindRequest,
    OAuthLoginRequest,
    OAuthRecordResponse,
    TokenResponse,
)

from .jwt_utils import create_access_token, get_expire_seconds

router = APIRouter(prefix="/auth", tags=["auth"])

CurrentUserId = Annotated[int, Depends(get_current_user_id)]


def _oauth_placeholder_email(provider: str, provider_uid: str) -> str:
    uid_safe = re.sub(r"[^a-zA-Z0-9_-]", "_", provider_uid.strip())[:200]
    return f"oauth_{provider.strip().lower()}_{uid_safe}@oauth.local"


@router.post("/login", response_model=LoginResponse, summary="邮箱密码登录")
async def login(body: LoginRequest, request: Request):
    """
    标准登录：查 users 表 → 校验密码(bcrypt) → 更新 last_login → 签发 JWT。
    返回 access_token 与用户基本信息（含 user_profiles 昵称/头像）。
    请求需登录的接口时在请求头携带：`Authorization: Bearer <access_token>`。
    """
    email = body.email.strip().lower()
    password_hash = await user_repository.get_password_hash_by_email(email)
    if not password_hash:
        raise HTTPException(status_code=401, detail="邮箱或密码错误")
    if not verify_password(body.password, password_hash):
        raise HTTPException(status_code=401, detail="邮箱或密码错误")

    user = await user_repository.get_by_email(email)
    if not user:
        raise HTTPException(status_code=401, detail="用户不存在或已注销")
    if user["status"] != 1:
        raise HTTPException(status_code=403, detail="账号已禁用或未激活")

    user_id = user["id"]
    client_host = request.client.host if request.client else None
    await user_repository.update_last_login(user_id, ip=client_host)

    profile = await profile_repository.get_by_user_id(user_id)
    nickname = profile.get("nickname") if profile else None
    avatar_url = profile.get("avatar_url") if profile else None

    access_token = create_access_token(sub=user_id)
    return LoginResponse(
        access_token=access_token,
        token_type="bearer",
        expires_in=get_expire_seconds(),
        user=LoginUserInfo(
            id=user["id"],
            email=user["email"],
            username=user.get("username"),
            nickname=nickname,
            avatar_url=avatar_url,
        ),
    )


@router.post("/oauth/login", response_model=TokenResponse, summary="第三方登录")
async def oauth_login(body: OAuthLoginRequest, request: Request):
    """
    第三方登录：用 provider + provider_uid 查找绑定；
    若已绑定则更新 last_login 并签发 JWT；若未绑定则自动创建用户（占位邮箱）并绑定后签发 JWT。
    """
    provider = body.provider.strip().lower()
    provider_uid = body.provider_uid.strip()
    provider_data = body.provider_data

    record = await oauth_repository.get_by_provider_uid(provider, provider_uid)
    if record:
        user_id = record["user_id"]
        user = await user_repository.get_by_id(user_id)
        if not user:
            raise HTTPException(status_code=403, detail="关联用户已注销")
        if user["status"] != 1:
            raise HTTPException(status_code=403, detail="账号已禁用或未激活")
        client_host = request.client.host if request.client else None
        await user_repository.update_last_login(user_id, ip=client_host)
    else:
        # 自动建用户并绑定
        email = _oauth_placeholder_email(provider, provider_uid)
        if await user_repository.get_by_email(email):
            raise HTTPException(status_code=409, detail="该第三方账号已与其它用户关联，请使用绑定接口")
        password_hash = hash_password(secrets.token_urlsafe(32))
        data = provider_data if isinstance(provider_data, dict) else {}
        username = data.get("name") or data.get("nickname")
        user = await user_repository.create(
            email=email,
            password_hash=password_hash,
            username=username,
            status=1,
        )
        user_id = user["id"]
        await oauth_repository.bind(user_id, provider, provider_uid, provider_data)
        client_host = request.client.host if request.client else None
        await user_repository.update_last_login(user_id, ip=client_host)

    access_token = create_access_token(sub=user_id)
    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
        expires_in=get_expire_seconds(),
    )


@router.post("/oauth/bind", response_model=OAuthRecordResponse, summary="绑定第三方账号")
async def oauth_bind(body: OAuthBindRequest, user_id: CurrentUserId):
    """
    将当前登录用户与第三方 (provider, provider_uid) 绑定。
    若该 provider_uid 已被其他用户绑定，会覆盖为当前用户（同平台唯一）。
    """
    record = await oauth_repository.bind(
        user_id,
        body.provider,
        body.provider_uid,
        body.provider_data,
    )
    return OAuthRecordResponse(
        id=record["id"],
        user_id=record["user_id"],
        provider=record["provider"],
        provider_uid=record["provider_uid"],
        provider_data=record.get("provider_data"),
        created_at=record["created_at"],
        updated_at=record["updated_at"],
    )


@router.get("/oauth/list", response_model=list[OAuthRecordResponse], summary="已绑定的第三方列表")
async def oauth_list(user_id: CurrentUserId):
    """查询当前用户已绑定的所有第三方账号。"""
    rows = await oauth_repository.list_by_user_id(user_id)
    return [
        OAuthRecordResponse(
            id=r["id"],
            user_id=r["user_id"],
            provider=r["provider"],
            provider_uid=r["provider_uid"],
            provider_data=r.get("provider_data"),
            created_at=r["created_at"],
            updated_at=r["updated_at"],
        )
        for r in rows
    ]


@router.delete("/oauth/{provider}", summary="解除第三方绑定")
async def oauth_unbind(provider: str, user_id: CurrentUserId):
    """解除当前用户与指定 provider 的绑定。"""
    ok = await oauth_repository.unbind(user_id, provider)
    if not ok:
        raise HTTPException(status_code=404, detail="未绑定该平台或已解除")
    return {"message": "已解除绑定"}
