# AI 聊天平台后端

基于 FastAPI 构建的多模型 LLM 聊天服务后端。

## 功能特性

- 🤖 支持多种 LLM 提供商
  - OpenAI (GPT-4, GPT-3.5-turbo)
  - Anthropic (Claude 3)
  - DeepSeek
  - 通义千问 (Qwen)
  - Moonshot (Kimi)
  - 智谱 AI (GLM)
  - 自定义 OpenAI 兼容接口
- 🔑 灵活的 API Key 管理
- 💬 支持流式/非流式对话
- 🔌 OpenAI 兼容接口设计

## 快速开始

### 1. 安装依赖

```bash
cd backend
pip install -r requirements.txt
```

### 2. 启动服务

**Windows 推荐不用 `--reload`**（否则 uvicorn 父子进程可能导致请求到不了应用，出现 404/无响应、终端无日志）：

```bash
python main.py
# 或
uvicorn main:app --host 0.0.0.0 --port 8000
```

也可在 backend 目录执行 `.\run.ps1`。

需要热重载时再使用 `--reload`（若出现访问无响应，请改回上述方式）。

### 3. 访问 API 文档

启动后访问 http://localhost:8000/docs 查看完整的 API 文档。

## API 接口

### 模型管理

#### 获取支持的提供商
```http
GET /api/models/providers
```

#### 添加模型配置
```http
POST /api/models
Content-Type: application/json

{
  "id": "gpt4",
  "name": "GPT-4",
  "provider": "openai",
  "model_name": "gpt-4",
  "api_key": "sk-xxx",
  "max_tokens": 4096,
  "temperature": 0.7
}
```

#### 获取所有模型配置
```http
GET /api/models
```

#### 删除模型配置
```http
DELETE /api/models/{model_id}
```

### 聊天

#### 发送消息（流式）
```http
POST /api/chat
Content-Type: application/json

{
  "model_id": "gpt4",
  "messages": [
    {"role": "system", "content": "你是一个有帮助的助手"},
    {"role": "user", "content": "你好"}
  ],
  "stream": true
}
```

响应为 SSE 流：
```
data: {"content": "你", "done": false}
data: {"content": "好", "done": false}
data: {"content": "！", "done": false}
data: {"content": "", "done": true}
```

#### 发送消息（非流式）
```http
POST /api/chat
Content-Type: application/json

{
  "model_id": "gpt4",
  "messages": [
    {"role": "user", "content": "你好"}
  ],
  "stream": false
}
```

响应：
```json
{
  "content": "你好！有什么我可以帮助你的吗？",
  "model": "gpt-4"
}
```

## 使用示例

### Python 示例

```python
import requests
import json

BASE_URL = "http://localhost:8000/api"

# 1. 添加模型配置
model_config = {
    "id": "deepseek",
    "name": "DeepSeek Chat",
    "provider": "deepseek",
    "model_name": "deepseek-chat",
    "api_key": "your-api-key"
}
requests.post(f"{BASE_URL}/models", json=model_config)

# 2. 发送聊天消息（流式）
chat_request = {
    "model_id": "deepseek",
    "messages": [
        {"role": "user", "content": "用Python写一个快速排序"}
    ],
    "stream": True
}

response = requests.post(f"{BASE_URL}/chat", json=chat_request, stream=True)
for line in response.iter_lines():
    if line:
        data = line.decode('utf-8')
        if data.startswith('data: '):
            content = json.loads(data[6:])
            if not content.get('done'):
                print(content['content'], end='', flush=True)
```

### JavaScript 示例

```javascript
const BASE_URL = 'http://localhost:8000/api';

// 添加模型配置
await fetch(`${BASE_URL}/models`, {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    id: 'gpt4',
    name: 'GPT-4',
    provider: 'openai',
    model_name: 'gpt-4',
    api_key: 'sk-xxx'
  })
});

// 流式聊天
const response = await fetch(`${BASE_URL}/chat`, {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    model_id: 'gpt4',
    messages: [{ role: 'user', content: '你好' }],
    stream: true
  })
});

const reader = response.body.getReader();
const decoder = new TextDecoder();

while (true) {
  const { done, value } = await reader.read();
  if (done) break;
  
  const lines = decoder.decode(value).split('\n');
  for (const line of lines) {
    if (line.startsWith('data: ')) {
      const data = JSON.parse(line.slice(6));
      if (!data.done) {
        process.stdout.write(data.content);
      }
    }
  }
}
```

## 项目结构

```
backend/
├── main.py              # FastAPI 应用入口
├── config.py            # 配置管理
├── models.py            # Pydantic 数据模型
├── requirements.txt     # 依赖
├── .env.example         # 环境变量示例
├── routers/
│   ├── __init__.py
│   ├── chat.py          # 聊天路由
│   └── models.py        # 模型配置路由
└── services/
    ├── __init__.py
    └── llm_service.py   # LLM 服务封装
```

## 后续规划

- [ ] RAG 支持（向量数据库集成）
- [ ] 对话历史持久化
- [ ] 文件上传与解析
- [ ] 用户认证
- [ ] 使用统计
