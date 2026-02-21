"""
JWT 签发与校验。
payload 中建议只放 sub（用户 id）、exp、iat，避免敏感信息。
"""
from datetime import datetime, timezone, timedelta
from typing import Any

import jwt

from .config import get_jwt_algorithm, get_jwt_expire_seconds, get_jwt_secret


def create_access_token(sub: int | str) -> str:
    """
    生成访问令牌。sub 建议为 user_id。
    返回 JWT 字符串。
    """
    secret = get_jwt_secret()
    algorithm = get_jwt_algorithm()
    expire_seconds = get_jwt_expire_seconds()
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(sub),
        "exp": now + timedelta(seconds=expire_seconds),
        "iat": now,
    }
    return jwt.encode(payload, secret, algorithm=algorithm)


def decode_token(token: str) -> dict[str, Any] | None:
    """
    校验并解析 JWT。过期或签名无效返回 None。
    """
    try:
        payload = jwt.decode(
            token,
            get_jwt_secret(),
            algorithms=[get_jwt_algorithm()],
        )
        return payload
    except jwt.PyJWTError:
        return None


def get_expire_seconds() -> int:
    """返回当前配置的过期秒数，用于登录响应中的 expires_in。"""
    return get_jwt_expire_seconds()
