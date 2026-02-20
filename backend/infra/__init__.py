"""
Infra 服务模块：对接 MinIO、Redis、DB 等外部/基础设施服务。
每个子目录对应一种服务，包含该服务的 client/业务逻辑与 API 路由。
"""
# 按需从子模块挂载路由，例如：
# from infra.minio import router as minio_router
