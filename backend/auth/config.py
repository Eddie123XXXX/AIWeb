"""JWT 相关配置，从环境变量读取"""
import os


def get_jwt_secret() -> str:
    """JWT 签名密钥，生产环境必须设置强随机值。"""
    secret = os.getenv("JWT_SECRET")
    if not secret or len(secret) < 16:
        # 开发环境占位；生产务必设置 JWT_SECRET
        return os.getenv("JWT_SECRET", "dev-secret-change-in-production-32bytes")
    return secret


def get_jwt_algorithm() -> str:
    return os.getenv("JWT_ALGORITHM", "HS256")


def get_jwt_expire_seconds() -> int:
    try:
        return int(os.getenv("JWT_EXPIRE_SECONDS", "86400"))  # 默认 24 小时
    except ValueError:
        return 86400
