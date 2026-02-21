"""
认证依赖：从 JWT 或开发用请求头解析当前用户 id。
优先使用 Authorization: Bearer <token>，无 token 时可用 X-User-Id（仅开发）。
"""
from typing import Optional

from fastapi import Depends, Header, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .jwt_utils import decode_token

security = HTTPBearer(auto_error=False)
X_USER_ID_HEADER = "X-User-Id"


async def get_current_user_id(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    x_user_id: Optional[str] = Header(None, alias=X_USER_ID_HEADER),
) -> int:
    """
    解析当前用户 id：优先 JWT Bearer，其次请求头 X-User-Id（开发用）。
    无有效认证时 401。
    """
    # 1. 尝试 JWT
    if credentials and credentials.credentials:
        payload = decode_token(credentials.credentials)
        if payload and "sub" in payload:
            try:
                return int(payload["sub"])
            except (ValueError, TypeError):
                pass
        raise HTTPException(
            status_code=401,
            detail="无效或过期的令牌",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # 2. 开发用请求头
    if x_user_id:
        try:
            return int(x_user_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="X-User-Id 必须为数字")

    raise HTTPException(
        status_code=401,
        detail="需要登录：请携带 Authorization: Bearer <token> 或开发时使用 X-User-Id",
        headers={"WWW-Authenticate": "Bearer"},
    )
