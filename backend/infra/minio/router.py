"""
对象存储 API - 用于测试 MinIO 上传/下载/列表
"""
from io import BytesIO
from typing import Optional

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import Response

from . import service

router = APIRouter(prefix="/infra/minio", tags=["infra-minio"])


@router.post("/upload", summary="上传文件")
async def upload(
    file: UploadFile = File(...),
    object_name: Optional[str] = File(None, description="存储路径，不传则使用文件名"),
):
    """
    上传文件到 MinIO。
    - 不传 `object_name` 时使用原始文件名。
    - 传 `object_name` 可指定在桶内的路径（如 `docs/hello.txt`）。
    """
    name = object_name or (file.filename or "upload")
    content_type = file.content_type or "application/octet-stream"
    body = await file.read()
    length = len(body)
    try:
        service.upload_object(name, BytesIO(body), length, content_type=content_type)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"存储上传失败: {e}")
    return {"object_name": name, "size": length, "content_type": content_type}


@router.get("/list", summary="列出对象")
async def list_objects(prefix: Optional[str] = None):
    """列出桶内对象，可选前缀过滤。"""
    try:
        items = service.list_objects(prefix=prefix or "")
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"存储列表失败: {e}")
    return {"objects": items, "prefix": prefix or ""}


@router.get("/download/{object_name:path}", summary="下载对象")
async def download(object_name: str):
    """根据对象名下载文件。"""
    try:
        data, content_type = service.get_object(object_name)
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"对象不存在或读取失败: {e}")
    return Response(content=data, media_type=content_type)


@router.get("/url/{object_name:path}", summary="获取预签名下载链接")
async def presigned_url(object_name: str, expires: int = 3600):
    """获取临时下载 URL，默认 1 小时有效。"""
    try:
        url = service.get_presigned_url(object_name, expires_seconds=expires)
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"对象不存在或生成链接失败: {e}")
    return {"url": url, "expires_seconds": expires}


@router.delete("/{object_name:path}", summary="删除对象")
async def delete(object_name: str):
    """按对象名删除。"""
    try:
        service.delete_object(object_name)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"删除失败: {e}")
    return {"deleted": object_name}
