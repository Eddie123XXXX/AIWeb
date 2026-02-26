"""
MinIO 对象存储服务
"""
import os
from datetime import timedelta
from typing import BinaryIO, Optional

from minio import Minio
from minio.error import S3Error


def _get_client() -> Minio:
    endpoint = os.getenv("MINIO_ENDPOINT", "localhost:9000").strip()
    access_key = os.getenv("MINIO_ACCESS_KEY", "minioadmin")
    secret_key = os.getenv("MINIO_SECRET_KEY", "minioadmin")
    secure = os.getenv("MINIO_SECURE", "false").lower() in ("true", "1", "yes")
    return Minio(
        endpoint,
        access_key=access_key,
        secret_key=secret_key,
        secure=secure,
    )


def _get_bucket() -> str:
    return os.getenv("MINIO_BUCKET", "aiweb")


def _ensure_bucket(client: Minio, bucket: str) -> None:
    try:
        if not client.bucket_exists(bucket):
            client.make_bucket(bucket)
    except S3Error:
        raise


def upload_object(
    object_name: str,
    data: BinaryIO,
    length: int,
    content_type: str = "application/octet-stream",
) -> str:
    """上传对象，返回对象名（路径）。"""
    client = _get_client()
    bucket = _get_bucket()
    _ensure_bucket(client, bucket)
    client.put_object(bucket, object_name, data, length, content_type=content_type)
    return object_name


def get_object(object_name: str) -> tuple[bytes, Optional[str]]:
    """获取对象内容，返回 (bytes, content_type)。"""
    client = _get_client()
    bucket = _get_bucket()
    response = client.get_object(bucket, object_name)
    try:
        data = response.read()
        content_type = (
            getattr(response, "headers", {}).get("Content-Type")
            or "application/octet-stream"
        )
        return data, content_type
    finally:
        response.close()


def list_objects(prefix: str = "") -> list[dict]:
    """列出对象，返回 [{"name": str, "size": int}, ...]。"""
    client = _get_client()
    bucket = _get_bucket()
    _ensure_bucket(client, bucket)
    result = []
    for obj in client.list_objects(bucket, prefix=prefix or None, recursive=True):
        result.append({"name": obj.object_name, "size": obj.size})
    return result


def delete_object(object_name: str) -> None:
    """删除对象。"""
    client = _get_client()
    bucket = _get_bucket()
    client.remove_object(bucket, object_name)


def get_presigned_url(
    object_name: str,
    expires_seconds: int = 3600,
) -> str:
    """生成预签名下载 URL。"""
    client = _get_client()
    bucket = _get_bucket()
    # MinIO Python SDK 要求 expires 为 datetime.timedelta，而不是 int
    return client.presigned_get_object(
        bucket,
        object_name,
        expires=timedelta(seconds=int(expires_seconds)),
    )
