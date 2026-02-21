"""
用户路由：注册、当前用户资料获取与更新（users + user_profiles）
认证：优先 JWT（Authorization: Bearer），开发时可传 X-User-Id。
"""
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from auth.dependencies import get_current_user_id
from db.profile_repository import profile_repository
from db.user_repository import hash_password, user_repository
from models import (
    ProfileData,
    ProfileUpdate,
    UserCreate,
    UserProfile,
    UserProfileMe,
    UserProfileUpdate,
)

router = APIRouter(tags=["user"])

CurrentUserId = Annotated[int, Depends(get_current_user_id)]


def _dict_to_profile(d: dict) -> UserProfile:
    return UserProfile(
        id=d["id"],
        email=d["email"],
        username=d.get("username"),
        phone_code=d.get("phone_code"),
        phone_number=d.get("phone_number"),
        status=d["status"],
        last_login_ip=d.get("last_login_ip"),
        last_login_at=d.get("last_login_at"),
        created_at=d["created_at"],
        updated_at=d["updated_at"],
    )


def _dict_to_profile_data(d: dict) -> ProfileData:
    return ProfileData(
        user_id=d["user_id"],
        nickname=d.get("nickname"),
        avatar_url=d.get("avatar_url"),
        bio=d.get("bio"),
        gender=d.get("gender", 0),
        birthday=str(d["birthday"]) if d.get("birthday") else None,
        location=d.get("location"),
        website=d.get("website"),
        preferences=d.get("preferences"),
        created_at=d["created_at"],
        updated_at=d["updated_at"],
    )


# 注册接口已移至 main.py 直接挂载 POST /api/user/register，避免 404

@router.get("/me", response_model=UserProfileMe, summary="当前用户（含扩展资料）")
async def get_me(user_id: CurrentUserId):
    """
    获取当前登录用户：users 表基础信息 + user_profiles 扩展资料。
    需携带 JWT（Authorization: Bearer <token>）或开发时传 X-User-Id。
    """
    user = await user_repository.get_by_id(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在或已注销")
    profile_row = await profile_repository.get_by_user_id(user_id)
    return UserProfileMe(
        id=user["id"],
        email=user["email"],
        username=user.get("username"),
        phone_code=user.get("phone_code"),
        phone_number=user.get("phone_number"),
        status=user["status"],
        last_login_ip=user.get("last_login_ip"),
        last_login_at=user.get("last_login_at"),
        created_at=user["created_at"],
        updated_at=user["updated_at"],
        profile=_dict_to_profile_data(profile_row) if profile_row else None,
    )


@router.put("/me", response_model=UserProfile, summary="更新当前用户（users 表）")
async def update_me(
    body: UserProfileUpdate,
    user_id: CurrentUserId,
):
    """更新 users 表：用户名、手机号等。不包含邮箱与密码。"""
    user = await user_repository.update_profile(
        user_id,
        username=body.username,
        phone_code=body.phone_code,
        phone_number=body.phone_number,
    )
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在或已注销")
    return _dict_to_profile(user)


@router.get("/me/profile", response_model=ProfileData, summary="当前用户扩展资料")
async def get_me_profile(user_id: CurrentUserId):
    """仅获取 user_profiles 扩展资料；无记录时 404。"""
    profile_row = await profile_repository.get_by_user_id(user_id)
    if not profile_row:
        raise HTTPException(status_code=404, detail="暂无扩展资料，请先通过 PUT /me/profile 创建")
    return _dict_to_profile_data(profile_row)


@router.put("/me/profile", response_model=ProfileData, summary="更新当前用户扩展资料")
async def update_me_profile(
    body: ProfileUpdate,
    user_id: CurrentUserId,
):
    """
    更新 user_profiles：昵称、头像、简介、性别、生日、地区、网站、偏好等。
    仅传需要修改的字段；若尚无资料行会先创建再更新。
    """
    await profile_repository.ensure_row(user_id)
    payload = body.model_dump(exclude_unset=True)
    profile_row = await profile_repository.update(
        user_id,
        nickname=payload.get("nickname"),
        avatar_url=payload.get("avatar_url"),
        bio=payload.get("bio"),
        gender=payload.get("gender"),
        birthday=payload.get("birthday"),
        location=payload.get("location"),
        website=payload.get("website"),
        preferences=payload.get("preferences"),
    )
    if not profile_row:
        raise HTTPException(status_code=404, detail="用户不存在或已注销")
    return _dict_to_profile_data(profile_row)
