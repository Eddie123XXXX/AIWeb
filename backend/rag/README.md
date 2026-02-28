# 📚 RAG 知识库模块

将 PDF、Word、Excel 等文档解析为结构化内容，经版面感知切块与向量化后写入 Milvus + PostgreSQL，支持多路召回、Reranker 精排与 Parent-Child 溯源，为 AIWeb 提供「可检索、可溯源的智能上下文」。

> 文档怎么变成可检索的知识、怎么把最相关的片段精准捞出来，都在这个模块里实现。

---

## ✨ 功能概览

- **上传与防重**
  - 按文件 SHA-256 做同笔记本防重与跨笔记本秒传，同文件不重复解析
  - 文件落 MinIO，`storage_path` 形如 `rag/{notebook_id}/{doc_id}/{filename}`

- **多源解析（PDF 优先 MinerU）**
  - 配置 `MINERU_API_TOKEN` 时优先走 [mineru.net 外部 API](https://mineru.net/apiManage/docs)：创建任务 → 轮询结果 → 下载 ZIP → 提取 markdown + content_list，并从 ZIP 内图片文件注入 `image_bytes`
  - 未配置或失败时走本地 MinerU：`POST /file_parse`，传 `return_content_list=true`、`return_images=true`，从响应的 `results.xxx.images` 解码 base64 注入图片 block
  - 再失败则降级为本地 pdfplumber；非 PDF 用 `parsers.parse_local`（Word/Excel/MD/TXT/MP3 等）

- **版面感知切块**
  - 基于 MinerU 的 content_list（或 pdf_info）做 Block 统一规范化后，按标题/伪标题/跨页/类型突变等多信号切 Parent，每个段落/表格/图片/代码块为 Child
  - 表格、图片、代码按「原子块」整块写入，表格防撕裂；图片 block 若有 `_image_url` 则 chunk 内容存「图片 URL + 可选 VLM 说明」

- **图片管线（可选）**
  - 有 `image_bytes` 的图片 block 一律上传 MinIO 并写回 `block["_image_url"]`；若 `RAG_IMAGE_PIPELINE_ENABLE=true` 再调用 VLM（qwen3-vl-plus，统一用 `QWEN_API_KEY`）做初筛与专家分支，将说明写入 `block["text"]`
  - 图片类 chunk 做 embedding 时仅用 VLM 文字（第一行之后），不用 URL，保证语义检索一致

- **向量化与入库**
  - 仅 Child Chunk 做 Dense + Sparse 向量化；Parent 只存 PostgreSQL 供召回后组装上下文
  - 全量切片写 PostgreSQL，向量写 Milvus，支持按 `chunk_type` 过滤（如只查 IMAGE_CAPTION）

- **三段式检索**
  - 第一段：Milvus Dense Top 60 + Sparse Top 60 + PostgreSQL 精确 Top 10
  - 第二段：RRF 融合取 Top 20
  - 第三段：Reranker 精排（Jina 或 Embedding 降级），按双阈值过滤后 Parent-Child 溯源返回

- **来源指南与展开预览**
  - `GET /documents/{id}/markdown` 返回 `filename`、`segments`（每段含 `chunk_id`）、`summary`；无 summary 时截断内容（默认 6000 字）调 LLM 生成并写入 `documents.summary`。
  - 前端从检索卡片点「展开文件」可传 `chunkId`，加载后定位到对应 segment 并高亮；检索支持 `document_ids` 限定（仅勾选知识源参与召回）。

---

## 🔄 技术流程概览

```
上传 → MinIO → 解析（MinerU 外部 API / 本地 / pdfplumber / 多格式）
  → Block 规范化 → 图片上传 MinIO + 可选 VLM
  → 版面感知切块（Parent-Child）→ PostgreSQL 全量切片
  → 仅 Child：Dense+Sparse 向量化 → Milvus

检索：query + document_ids? → 精确 Top10 + Sparse Top60 + Dense Top60
  → RRF Top20 → Reranker 精排 → Parent 回填 → SearchHit[]
```

实现细节见下节「实现流程详解」。

---

## 🗂 目录结构

| 文件 | 职责 |
|------|------|
| `models.py` | Pydantic 请求/响应模型（SearchRequest、SearchHit、DocumentOut、ChunkType 等） |
| `document_repository.py` | documents 表 CRUD、防重、状态流转、秒传 |
| `chunk_repository.py` | document_chunks 表 CRUD、全文搜索（Path-1 精确匹配） |
| `parsers.py` | 多格式解析（PDF/Word/Excel/MD/TXT/MP3 等），PDF 路由到 MinerU 或 pdfplumber |
| `chunking.py` | 版面感知切块（Block → Parent-Child）、`get_content_for_embedding`（含 IMAGE_CAPTION 仅用 VLM 文字） |
| `embedding.py` | Dense（通义 text-embedding-v4）、Sparse（BGE-M3 / API / TF-IDF 降级） |
| `vector_store.py` | Milvus 写入与 Dense/Sparse 混合检索 |
| `reranker.py` | Reranker 精排（Jina + Embedding 降级，双阈值） |
| `image_pipeline.py` | 图片上传 MinIO、VLM 初筛与专家分支（qwen3-vl-plus，统一 QWEN_API_KEY） |
| `service.py` | 核心编排：上传→解析→Block 规范化→图片注入→图片预处理→切块→入库→向量化 |
| `router.py` | FastAPI 路由（笔记本、文档上传/process/reparse、检索） |
| `tasks.py` | 异步任务队列（Redis RQ，长解析入队） |
| `export_markdown.py` | 按 document_id 从 chunk 还原 Markdown（调试用） |
| `clear_rag_data.py` | 一键清空 Postgres + Milvus + MinIO rag/（仅开发） |

---

## 🔄 实现流程详解

整体顺序：**上传 → 解析 → Block 提取与规范化 → 图片注入（仅 PDF）→ 图片预处理 → 切块 → 入库与向量化 → 检索**。下面按步骤说明每一步如何实现。

### 1. 文档上传与防重

- **入口**：`router.py` 中 `POST /rag/documents/upload`，接收 `notebook_id` + 文件 multipart。
- **实现**：`service.upload_document`。
  - 计算文件 SHA-256，查 `document_repository.find_by_notebook_and_hash` 做同笔记本防重；若已存在直接返回。
  - 查 `find_any_by_hash` 做跨笔记本秒传：若其他笔记本有同 hash，则复制其 chunk 与向量到当前文档，并返回，不再解析。
  - 否则生成 `doc_id`，`storage_path = rag/{notebook_id}/{doc_id}/{filename}`，调用 MinIO 上传，写入 `documents` 表，状态 `UPLOADED`。
- **相关**：`document_repository.py`、`infra/minio/service.py`。

### 2. 触发解析与解析源选择

- **入口**：`POST /rag/documents/{id}/process`（或队列 Worker 消费任务）。
- **实现**：`service.process_document(doc_id)`。
  - 若状态已为 `READY` 直接返回；否则 `UPLOADED` → `PARSING`。
  - 根据文件名选解析器：PDF 走 MinerU 分支，其它走 `parsers.parse_local`。
  - **PDF 分支**：从 MinIO 拉取文件字节；若配置了 `MINERU_API_TOKEN` 则优先外部 API（见下），否则调用本地 MinerU `_call_mineru_parse`；再失败则 `parsers._parse_pdf_local` 降级。得到统一结构的 `parse_result`：`markdown`、`content_list`（列表或需从 results 解包）。

### 3. 外部 MinerU API 路径（可选）

- **条件**：`MINERU_API_TOKEN` 已配置；生成给 mineru.net 拉取用的文件 URL 时使用 `get_presigned_url_for_external`（若配置 `MINIO_PUBLIC_ENDPOINT` 则用该地址，否则用默认 MinIO 预签名）。
- **实现**：`service._call_mineru_external_api(file_url, filename)`。
  - `POST {MINERU_EXTERNAL_API_BASE_URL}/api/v4/extract/task`，body：`url`、`model_version`（vlm/pipeline/MinerU-HTML）、`language=ch` 等。
  - 轮询 `GET .../api/v4/extract/task/{task_id}` 直至返回 `full_zip_url`（或失败/超时）。
  - 下载 ZIP，解压：收集所有 `.md` 拼成 `markdown`；遍历所有 `.json` 用 `_extract_content_list_from_obj` 从根或 `results`/`data`/单键包装中取出 `content_list`。
  - **图片注入**：`_inject_image_bytes_from_zip(zf, names, content_list)`：ZIP 内图片文件（.png/.jpg 等）按 block 的 `img_path`/`image_path` 等匹配，或按序兜底，将读到的字节写入 `block["image_bytes"]`。
  - 返回 `{ "markdown": markdown, "content_list": content_list }`。

### 4. 本地 MinerU 路径

- **实现**：`service._call_mineru_parse(file_data, filename)`。
  - `POST {MINERU_API_BASE_URL}/file_parse`，multipart：`files` + `return_md=true`、`return_content_list=true`、**`return_images=true`**、`lang_list=ch`、`backend`（pipeline/vlm-auto-engine 等）。
  - 响应用 `_normalize_mineru_response` 解包 `results` 得到 `markdown`、`content_list`。
  - **图片注入**：`_inject_image_bytes_from_local_response(normalized, result)`：从 `result["results"][文档]["images"]`（文件名 → data URL 或 base64）解码得到 bytes，按 block 的 `img_path`/`image_path` 或按序注入 `block["image_bytes"]`。
  - 返回与外部 API 同结构的 `normalized`。

### 5. Block 提取与统一规范化

- **实现**：`service._extract_blocks(parse_result)`。
  - 优先从 `parse_result["content_list"]` 取列表（兼容字符串或 `{content_list/items}` 包装）；对每条 block 调用 `_normalize_content_list_block`：
    - `type`：`_normalize_block_type(type/content_type/block_type)`，统一为 title/table/image/image_caption/text 等。
    - `text`：从 `text`/`content`/`md` 取一。
    - `page_idx`：`_normalize_page_idx` 转为 `list[int]`。
    - 保留 `image_bytes`、`b64_image`、`img_path`、`image_path`、`_image_url`、`table_body` 等字段。
  - 若无 content_list 则从 `pdf_info` 按页取 `preproc_blocks`/`blocks`，同样用 `_normalize_block_type` 与 `page_idx` 构造 block 列表。
  - 若仍无则返回空列表，下游用 markdown 降级切块（`chunking.chunk_markdown`）。

### 6. 图片预处理（上传 MinIO + 可选 VLM）

- **实现**：`service._preprocess_image_blocks(blocks, document_id, notebook_id)`；在解析完成后、切块前调用。
  - 对每个属于 `chunking.IMAGE_FAMILY` 且含 `image_bytes` 的 block：
    - 若尚无 `_image_url`：调用 `image_pipeline.upload_image_to_minio` 上传到 `rag/images/{notebook_id}/{document_id}/{uuid}.png`，将返回的预签名 URL 写入 `block["_image_url"]`。
    - 若 `RAG_IMAGE_PIPELINE_ENABLE=true`：再调 `image_pipeline.process_multimodal_image`（`upload_to_minio=False`，传入已有 `_image_url`），用 VLM 做初筛与专家分支，将融合后的说明写回 `block["text"]`。
  - 保证本地 MinerU 与外部 API 路径在「图片 block 带 _image_url、可选带 VLM 文本」上一致。

### 7. 版面感知切块

- **实现**：`chunking.process_mineru_blocks(blocks, document_id, notebook_id)`。
  - Block 的 `type` 再次经 `_normalize_block_type`（兼容 figure/img 等），`page_idx` 经 `_normalize_page_idx`。
  - 噪声类型（header/footer/page_number 等）丢弃；表格/图片/代码按族聚合后整块输出；正文按标题/伪标题/跨页/类型突变等信号切 Parent，段落为 Child。
  - **图片 chunk**：有 `_image_url` 的 block 每个单独一个 IMAGE_CAPTION chunk，`content = url + "\n" + text`（无文字则仅 URL）；无 URL 的图片 block 合并为一个 chunk，content 为合并文字或 `[图片]`。
  - 输出为 `List[Chunk]`（含 `chunk_type`、`content`、`page_numbers`、`parent_chunk_id` 等）。

### 8. 入库与向量化

- **实现**：`service.process_document` 后半段。
  - 先 `chunk_repository.deactivate_by_document(doc_id)`，再 `chunk_repository.bulk_create(chunk_dicts)` 将全部 Parent+Child 写入 PostgreSQL。
  - 仅 Child Chunk 参与向量化：`texts = [chunking.get_content_for_embedding(c) for c in child_chunks]`。
    - **IMAGE_CAPTION**：`get_content_for_embedding` 内若 `chunk_type == "IMAGE_CAPTION"` 且 `content` 含 `\n`，则只取第一行之后的子串（VLM 文字）用于 embedding；若无 `\n` 则用空串（不拿 URL 做语义向量）。
  - 其它类型用完整 `content`，超过 `RAG_MAX_EMBEDDING_TOKENS` 则截断并加省略提示。
  - Dense + Sparse 并发计算后写入 Milvus（`vector_store.upsert_chunks`），并写入 chunk 元数据（含 `chunk_type`、`content_preview` 等）。

### 9. 检索（三段式）

- **入口**：`POST /rag/search`，body 为 `SearchRequest`（notebook_id、query、top_k、enable_rerank、chunk_types 等）。
- **实现**：`service` 内三路召回 + RRF + Reranker。
  - Path-1：`chunk_repository` 全文/ILIKE 精确匹配，取 Top 10。
  - Path-2：Sparse 向量检索 Milvus，Top 60。
  - Path-3：Dense 向量检索 Milvus，Top 60。
  - 三路结果按 chunk_id 做 RRF 融合，取 Top 20；若 `enable_rerank=true` 则用 `reranker.rerank`（Jina 或 Embedding 降级）精排，按 `rerank_threshold` / `fallback_cosine_threshold` 过滤。
  - 按 `parent_chunk_id` 回查 Parent 内容，组装为 `SearchHit`（含 `content`、`parent_content`、`chunk_type` 等）返回。

---

## 🧩 切块策略（多信号 + 安全阀）

- **标题切分**：MinerU `type=title` 或伪标题（Markdown `#`、编号标题、章节词等）时刷新 Parent。
- **软切分**：跨页且父块已有一定 token/子块数、或类型在 text/table/image 等间突变时开新 Parent。
- **安全阀**：单 Parent token 超过 `RAG_PARENT_MAX_TOKENS` 强制切分。
- **环境变量**：`RAG_PARENT_MAX_TOKENS`、`RAG_PARENT_SPLIT_ENABLE_PSEUDO_TITLE`、`RAG_PARENT_SPLIT_ENABLE_PAGE_BREAK`、`RAG_PARENT_SPLIT_ENABLE_TYPE_SHIFT`、`RAG_PARENT_SPLIT_MIN_PARENT_TOKENS`、`RAG_PARENT_SPLIT_MIN_CHILDREN`、`RAG_PARENT_PSEUDO_TITLE_MAX_CHARS`（见下方环境变量表）。

---

## 🖼 图片 Pipeline 与召回一致性

- **图片类型识别**：chunking 中 `_normalize_block_type` 将 figure/img/image_body 等统一为 image，image_caption/figure_caption 统一为 image_caption，保证本地 MinerU 与 API 返回的 block 都能正确归入 IMAGE_FAMILY。
- **内容与 embedding**：图片 chunk 的 `content` 存「图片 URL + 换行 + VLM 说明」；embedding 仅用 VLM 文字（第一行之后），避免 URL 参与语义向量。
- **VLM**：统一使用 `QWEN_API_KEY`；未配置 `QWEN_API_BASE` 时默认 `https://dashscope.aliyuncs.com/compatible-mode/v1`，模型默认 `qwen3-vl-plus`（`RAG_IMAGE_VLM_MODEL`）。

---

## 🚀 API 端点

所有接口挂载在 `/api/rag/` 下：

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/notebooks` | 笔记本列表 |
| POST | `/notebooks` | 创建笔记本 |
| PUT | `/notebooks/{id}` | 更新笔记本 |
| DELETE | `/notebooks/{id}` | 删除笔记本 |
| POST | `/documents/upload` | 上传文档（防重 + 秒传） |
| POST | `/documents/{id}/process` | 触发解析流水线（可异步入队） |
| POST | `/documents/{id}/reparse` | 重新解析（弃旧切片与向量） |
| GET | `/documents` | 笔记本下文档列表 |
| GET | `/documents/{id}` | 文档详情 |
| GET | `/documents/{id}/chunks` | 文档切片列表 |
| GET | `/documents/{id}/markdown` | 文档还原 Markdown + 来源指南总结（展开文件预览） |
| DELETE | `/documents/{id}` | 删除文档 |
| POST | `/search` | 三路召回 + RRF + Reranker |

---

## ⚙️ 环境变量

在 `backend/.env` 中配置（可选，有默认值）：

```env
# ----- RAG Embedding（与 memory 一致：通义 text-embedding-v4） -----
# RAG_EMBEDDING_MODEL=
# RAG_EMBEDDING_DIM=1536
# RAG_EMBEDDING_BASE_URL=
# RAG_EMBEDDING_BATCH_SIZE=10

# ----- Reranker -----
# JINA_API_KEY=
# RAG_RERANK_THRESHOLD=0.2
# RAG_FALLBACK_COSINE_THRESHOLD=0.85

# ----- Sparse / 护栏 -----
# RAG_SPARSE_PROVIDER=auto
# RAG_MAX_EMBEDDING_TOKENS=2048

# ----- 切块策略 -----
# RAG_PARENT_MAX_TOKENS=2000
# RAG_PARENT_SPLIT_ENABLE_PSEUDO_TITLE=true
# RAG_PARENT_SPLIT_ENABLE_PAGE_BREAK=true
# RAG_PARENT_SPLIT_ENABLE_TYPE_SHIFT=true
# RAG_PARENT_SPLIT_MIN_PARENT_TOKENS=600
# RAG_PARENT_SPLIT_MIN_CHILDREN=3
# RAG_PARENT_PSEUDO_TITLE_MAX_CHARS=64

# ----- 异步队列 -----
# RAG_USE_QUEUE=false

# ----- PDF 解析：优先外部 MinerU API -----
# MINERU_EXTERNAL_API_BASE_URL=https://mineru.net
# MINERU_API_TOKEN=              # 配置后优先 mineru.net，失败再本地/ pdfplumber
# MINERU_EXTERNAL_MODEL_VERSION=  # 可选: pipeline | vlm | MinerU-HTML

# ----- 本地 MinerU（未用外部 API 时） -----
# MINERU_API_BASE_URL=http://localhost:9999
# MINERU_BACKEND=pipeline

# ----- 外部 API 时 MinIO 公网地址（隧道） -----
# MINIO_PUBLIC_ENDPOINT=https://xxxx.ngrok-free.app

# ----- 图片 Pipeline（VLM 统一 QWEN_API_KEY） -----
# RAG_IMAGE_PIPELINE_ENABLE=false
# RAG_IMAGE_PIPELINE_TIMEOUT=30
# RAG_IMAGE_VLM_MODEL=qwen3-vl-plus
# RAG_IMAGE_VLM_BASE_URL=         # 不填则用 QWEN_API_BASE 或 DashScope 默认
# RAG_IMAGE_CHART_MAX_TOKENS=1500

# ----- 基础设施（与 infra 一致） -----
# MINIO_ENDPOINT=localhost:9000
# POSTGRES_HOST=localhost
# MILVUS_HOST=localhost
# MILVUS_PORT=19530

# ----- 清理确认 -----
# RAG_CLEAR_CONFIRM=
```

### 本地开发 + 外部 MinerU：隧道暴露 MinIO（可选）

**不需要此配置即可本地部署**：未配置 `MINERU_API_TOKEN` 或 `MINIO_PUBLIC_ENDPOINT` 时，RAG 使用本地 MinerU（docker 9999 端口）或 pdfplumber 解析 PDF，无需公网暴露。

仅当使用 [mineru.net](https://mineru.net) 云端解析时，mineru.net 需通过公网 URL 拉取你上传到 MinIO 的文件，此时需要把本机 MinIO（9000）暴露到公网：

- **ngrok**：`ngrok http 9000`，将得到的 `https://xxxx.ngrok-free.app` 写入 `MINIO_PUBLIC_ENDPOINT`（不要带末尾斜杠），并在 `.env` 中配置 `MINERU_API_TOKEN`。
- **cloudflared**：`cloudflared tunnel --url http://localhost:9000`，将得到的地址写入 `MINIO_PUBLIC_ENDPOINT`。

隧道重启后地址会变，需重新更新 `.env`。

---

## 📦 依赖与脚本

- **依赖**：`asyncpg`、`pymilvus`、`openai`（Dense Embedding / VLM）、`httpx`。
- **建表**：`db/schema_documents.sql`、`db/schema_document_chunks.sql`，执行 `python -m db.run_schema`。
- **来源指南（文档总结）**：需为 `documents` 表增加 `summary` 列，执行 `python -m rag.migrate_add_summary`（PostgreSQL 9.6+）。总结由 LLM 在首次展开文件时生成并入库，大文档会截断到 `RAG_SUMMARY_MAX_CHARS`（默认 6000）再送模型；可选 `RAG_SUMMARY_BASE_URL`、`RAG_SUMMARY_API_KEY`、`RAG_SUMMARY_MODEL`，未配置时回退到 `OPENAI_API_KEY` / `QWEN_API_KEY`。
- **测试**：`python -m rag.test_rag`（需 MinIO、PostgreSQL、Milvus 与 .env）。
- **导出 Markdown**：`python -m rag.export_markdown`，按 document_id 从 chunk 还原到 `rag/exports/`。
- **清空 RAG 数据**：`RAG_CLEAR_CONFIRM=yes python -m rag.clear_rag_data`（清空 Postgres 相关表、Milvus collection、MinIO rag/）。

---

## 🗺 数据流概览

```
上传 → MinIO 存储 → 解析（外部 API ZIP / 本地 MinerU JSON）
    → 图片注入（ZIP 内文件 / return_images 的 base64）
    → Block 统一规范化 → 图片预处理（上传 MinIO + 可选 VLM）
    → 版面感知切块（Parent-Child）
    → PostgreSQL 全量切片 + 仅 Child 做 Dense/Sparse 向量化 → Milvus

检索：Query → Dense Top60 + Sparse Top60 + 精确 Top10
    → RRF Top20 → Reranker 精排 → Parent-Child 溯源 → 返回
```

