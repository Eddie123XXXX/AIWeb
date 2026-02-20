# 后端 Infra 服务

本目录用于集中管理对接**外部/基础设施**的代码（如 MinIO、Redis、数据库等），与业务路由 `routers/`、通用业务服务 `services/` 区分开，便于扩展和维护。

## 目录约定

每个子目录对应一种基础设施服务，建议结构：

```
infra/
  minio/           # MinIO 对象存储
    __init__.py
    service.py
    router.py
  redis/           # Redis 缓存
    __init__.py
    service.py
    router.py
  postgres/        # PostgreSQL 数据库
    __init__.py
    service.py
    router.py
  milvus/          # Milvus 向量数据库
    __init__.py
    service.py
    router.py
  rabbitmq/        # RabbitMQ 消息队列
    __init__.py
    service.py
    router.py
  elasticsearch/   # Elasticsearch 搜索引擎
    __init__.py
    service.py
    router.py
```

- **service / client**：连接配置、读写逻辑，不依赖 FastAPI。
- **router**：对外 HTTP 接口，仅在本模块内引用 service，在 `main.py` 中挂载。

## 在 main.py 中挂载

```python
from infra.minio import router as storage_router
from infra.redis import router as redis_router
from infra.postgres import router as postgres_router
from infra.milvus import router as milvus_router
from infra.rabbitmq import router as rabbitmq_router
from infra.elasticsearch import router as es_router
app.include_router(storage_router, prefix="/api")
app.include_router(redis_router, prefix="/api")
app.include_router(postgres_router, prefix="/api")
app.include_router(milvus_router, prefix="/api")
app.include_router(rabbitmq_router, prefix="/api")
app.include_router(es_router, prefix="/api")
```

新增服务时同理：在对应子目录实现 `router`，在 `main.py` 中 `from infra.xxx import router` 并 `include_router`。
