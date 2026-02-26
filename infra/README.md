# 🚀 MinIO + Redis + PostgreSQL + Milvus + Attu + RabbitMQ + RedisInsight + pgAdmin 基础设施

一条命令，把一整套「个人 AI 数据中心」拉起来。  
这就是 AIWeb 背后安静工作的 **小型云平台**。😎

## 🧰 一键启动

在项目根目录（AIWeb）下执行：

```bash
docker compose -f infra/docker-compose.yml up -d
```

然后你就拥有了：对象存储、缓存、数据库、向量库、消息队列、搜索引擎和各种 Web 控制台。  
适合：

- 本地玩 AI / RAG / 记忆系统 🧪
- 自己搭一个「轻量版 OpenAI 控制台」🧰
- 把这套 infra 直接复用到你的其他项目里 ✂️

## 🌐 服务与端口

| 服务          | 端口        | 说明                          |
|---------------|-------------|-------------------------------|
| MinIO         | 9000, 9001  | 对象存储（API / Console）     |
| Redis         | 6379        | 缓存 / KV 存储                |
| PostgreSQL    | 5432        | 关系数据库                    |
| Milvus        | 19530, 9091 | 向量数据库（服务端）          |
| Attu          | 8000        | Milvus Web 控制台             |
| RabbitMQ      | 5672, 15672 | 消息队列 / 管理控制台         |
| RedisInsight  | 5540        | Redis Web 控制台              |
| pgAdmin       | 5050        | PostgreSQL Web 管理界面       |
| Elasticsearch | 9200, 9300  | 搜索引擎（服务端）            |
| Kibana        | 5601        | Elasticsearch Web 控制台      |

可以把这张表当成你本地「AI 基础设施机房地图」🗺️。

## ⚙️ 环境变量（后端 .env）

与后端对接时，在 `backend/.env` 中配置（可选，已有默认值）：  
（懒得改的话，大部分默认值已经能直接跑起来 👌）

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

💡 MinIO 小提示：首次通过 API 上传或列表对象时，如果桶还不存在，会自动创建 `MINIO_BUCKET`。  
「先用再说」的那种开心感。😏

## 🐘 pgAdmin 访问 Postgres（展开 server 后为空时必读）

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

连上之后，你就有了一个看得见、点得着的 Postgres：  
表结构、数据、索引一目了然，调试 AI 记忆/RAG 时非常安心。🧯

---

## 💡 我能拿这套 infra 干嘛？

- 🧪 搭建本地 AI 实验环境：向量检索、长期记忆、RAG 都可以真·连到数据库里测
- 🧱 作为其他项目的「通用底座」：直接拷贝 `infra/` 就能复用
- ⚙️ 观察 AIWeb 的「内脏」：对话落库、记忆写入、向量 upsert、消息队列消费都是真实可见的

你可以把它当成一个**很严肃的 infra**，  
也可以把它当成一个「按下开关就亮起来的玩具机房」—— 取决于你今天的心情。🎉

