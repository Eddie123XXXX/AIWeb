# MinIO + Redis + PostgreSQL + Milvus + Attu + RabbitMQ + RedisInsight + pgAdmin 基础设施

## 启动

在项目根目录（AIWeb）下执行：

```bash
docker compose -f infra/docker-compose.yml up -d
```

## 服务与端口

| 服务         | 端口        | 说明                     |
|--------------|-------------|--------------------------|
| MinIO        | 9000, 9001  | 对象存储                 |
| Redis        | 6379        | 缓存/存储                |
| PostgreSQL   | 5432        | 关系数据库               |
| Milvus       | 19530, 9091 | 向量数据库（服务端）     |
| Attu         | 8000        | Milvus Web 控制台        |
| RabbitMQ     | 5672, 15672 | 消息队列 / 控制台        |
| RedisInsight | 5540        | Redis Web 控制台         |
| pgAdmin      | 5050        | PostgreSQL Web 管理界面 |
| Elasticsearch| 9200, 9300  | 搜索引擎（服务端）       |
| Kibana       | 5601        | Elasticsearch Web 控制台 |

## 环境变量（后端 .env）

与后端对接时，在 `backend/.env` 中配置（可选，已有默认值）：

```env
# MinIO
MINIO_ENDPOINT=localhost:9000
MINIO_BUCKET=aiweb
MINIO_SECURE=false

# Redis
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_DB=0
REDIS_PASSWORD=

# PostgreSQL
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_USER=aiweb
POSTGRES_PASSWORD=aiweb
POSTGRES_DB=aiweb

# Milvus
MILVUS_HOST=localhost
MILVUS_PORT=19530

# RabbitMQ
RABBITMQ_HOST=localhost
RABBITMQ_PORT=5672
RABBITMQ_USER=guest
RABBITMQ_PASSWORD=guest
RABBITMQ_VHOST=/

# Elasticsearch
ELASTICSEARCH_HOST=localhost
ELASTICSEARCH_PORT=9200
```

MinIO：首次通过 API 上传或列表时，若桶不存在会自动创建。

## pgAdmin 访问 Postgres（展开 server 后为空时必读）

1. 打开 **http://localhost:5050**，登录：`admin@example.com` / `admin`。
2. **展开 server 后看不到任何东西**：说明还没连上库。请**双击** **aiweb-postgres**（不要只点 ▶）：
   - 会弹出密码框时，密码填 **aiweb**，勾选“保存”，确定；
   - 连成功后，下面才会出现 **Databases** 等，再展开 **Databases** → **aiweb** → **Schemas** → **public** → **Tables**。
3. **若双击后仍无反应或报错**：改用手动添加服务器。
   - 在左侧 **Servers** 上**右键** → **Register** → **Server**；
   - **General**：Name 填 `aiweb-postgres`；
   - **Connection**：Host 填 **postgres**，Port **5432**，Maintenance database **aiweb**，Username **aiweb**，Password **aiweb**，勾选 Save password；
   - 保存后，**双击**这个新服务器，输入密码 `aiweb`，即可展开。
4. **若 Host 填 postgres 连不上**：在项目根执行  
   `docker compose -f infra/docker-compose.yml up -d --force-recreate pgadmin`  
   再试；或手动添加时 Host 改为 **host.docker.internal**（Windows/Mac Docker Desktop）试一次。

