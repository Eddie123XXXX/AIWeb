# AIWeb Frontend 💻

## 快速导航

- 技术栈：React 18 + Vite
- 页面与路由：聊天、知识库、登录注册
- 联调方式：本地代理 `/api` 与 WebSocket
- 重点模块：`components/`、`hooks/useChat.js`、`utils/`

这里是 AIWeb 的前端界面：  
用 React + Vite 写的一个「多模型聊天 + 知识库 + 记忆面板」小控制台。😎

和原来的静态 HTML/CSS/JS 相比，这里多了：

- 组件化布局（Sidebar / Header / Chat / Input）
- WebSocket 流式消息管理
- Markdown + 代码高亮 + 复制按钮
- 国际化（中英文切换）

## 🧰 技术栈

- ⚛️ **React 18** + **Vite 5**
- 📝 **marked**：Markdown 渲染
- 🌈 **highlight.js**：代码高亮

## 📁 项目结构（前端）

```
frontend/
├── index.html          # Vite 入口页
├── package.json
├── vite.config.js      # 开发时代理 /api 到后端 8000 端口
├── src/
│   ├── main.jsx        # React 入口
│   ├── App.jsx         # 根组件（布局、主题、聊天状态）
│   ├── index.css       # 全局样式（与原 main.css 一致）
│   ├── components/
│   │   ├── Sidebar.jsx   # 侧边栏
│   │   ├── Header.jsx    # 顶栏（主题切换、模型选择等）
│   │   ├── Welcome.jsx   # 欢迎区 + 聊天列表容器
│   │   ├── Chat.jsx      # 消息列表
│   │   ├── ChatMessage.jsx   # 单条消息（支持 Markdown/代码高亮/复制）
│   │   ├── InputArea.jsx     # 输入框与发送（含附件、语音）
│   │   ├── MemoryManageModal.jsx      # 记忆管理浮窗（列表/新增/编辑/删除）
│   │   ├── AgenticReasoningPanel.jsx  # Agentic 推理过程面板（展示 Thought/Action/Observation 事件流）
│   │   ├── AddMCPServerModal.jsx      # 添加 MCP Server 弹窗（一键发现并勾选 MCP 工具）
│   │   └── SnakeGame.jsx              # 贪吃蛇小游戏（解析等待弹窗内）
│   ├── hooks/
│   │   ├── useTheme.js   # 亮/暗主题与 localStorage
│   │   └── useChat.js    # WebSocket 聊天与流式输出
│   └── utils/
│       └── markdown.js   # Markdown 解析、代码高亮、复制
├── css/main.css        # 原静态版样式（保留）
└── js/main.js          # 原静态版逻辑（保留）
```

## 🚀 开发与构建

```bash
# 安装依赖
npm install

# 开发（默认 http://localhost:5173，/api 代理到后端 8000）
npm run dev

# 构建
npm run build

# 预览构建结果
npm run preview
```

## 🧭 当前界面与路由（开发环境 base: http://localhost:5173）

| 路径 | 说明 |
|------|------|
| `/login` | 登录页（未登录时入口，邮箱+密码登录） |
| `/register` | 注册页（邮箱、密码、用户名、手机号，对应后端 users 表） |
| `/` | 主聊天页（首页，需登录） |
| `/wiki` | RAG 知识库 / 仪表盘（需登录，笔记本 emoji、解析等待+贪吃蛇） |
| `/wiki/search` | RAG 搜索页（需登录） |

未登录访问 `/`、`/wiki`、`/wiki/search` 会重定向到 `/login`；已登录访问 `/login` 或 `/register` 会重定向到 `/`，  
保证「先登录，再玩 AI」，体验和安全感都在线。🔐

## 🔌 与后端联调

1. 启动后端：`cd backend && uvicorn main:app --host 0.0.0.0 --port 8000`
2. 启动前端：`cd frontend && npm run dev`
3. 浏览器访问 `http://localhost:5173`，前端通过 Vite 代理将 `/api` 和 WebSocket 请求转发到 8000 端口。

## 🎤 语音输入与「不安全」提示

浏览器要求**麦克风**仅在**安全上下文**下使用，否则会显示 “Not secure” 并拒绝权限。

- **视为安全**：`https://` 任意域名、`http://localhost`、`http://127.0.0.1`
- **视为不安全**：`http://192.168.x.x`、`http://你的电脑名` 等非 localhost 的 HTTP

**可用做法：**

| 场景 | 做法 |
|------|------|
| 本机访问 | 用 **http://localhost:5173** 或 **http://127.0.0.1:5173**，不要用 `http://本机IP:5173` |
| 手机/其他设备访问 | 用 **ngrok** 等暴露为 **https** 地址后再访问（如 `ngrok http 5173` 得到 https 链接） |
| 正式部署 | 使用 **HTTPS**（反向代理配置 SSL 证书） |

若在非安全上下文中点击麦克风，页面会提示：「请用 https 或 http://localhost 访问本页」。

## 🧠 前端功能说明

- 🎨 **主题**：`useTheme` 管理亮/暗主题，写入 `data-theme` 与 localStorage。
- 📚 **侧边栏**：`Sidebar` 负责会话列表与导航，支持移动端展开/收起。
- 💬 **聊天流**：`useChat` 维护消息列表、流式内容与 WebSocket，支持暂停生成。
- 📝 **消息渲染**：`ChatMessage` 对 assistant 消息做 Markdown 渲染、代码高亮与一键复制。
- 📎 **Quick Parse 文件预览**：`InputArea` 支持附件上传与校验；`ChatMessage` 以文件卡片展示并提示不进入长期记忆。
- 🧠 **记忆管理**：侧栏/用户菜单提供「记忆管理」入口，`MemoryManageModal` 浮窗内可列表、新增、编辑、删除记忆；编辑会触发后端重新向量化。
- 🎤 **语音输入**：`InputArea` 支持麦克风录音；安全上下文（localhost/https）下使用 Web Speech API，否则上传 webm 走后端 ASR（Qwen3-ASR-Flash）。
- 🧩 **Agentic 推理与工具调用**：`Header` 提供 Agentic 模式开关；开启后 `useChat` 在后台切换使用 Agentic 后端接口（`/api/agentic/*`），`AgenticReasoningPanel` 在聊天区顶部展示 Thought / Action / Observation 事件流；`Welcome` 与 `InputArea` 右下「更多」区域展示可用工具列表，并可通过 `AddMCPServerModal` 一键添加 MCP Server。
- 📚 **RAG 页**：知识源勾选、检索文档卡片（表格/图片/公式富文本）、展开文件定位高亮、来源指南展示；笔记本 **emoji** 优先用列表返回的 `emoji`，无则请求 `POST /api/rag/emoji-from-title` 后通过 `PATCH /api/rag/notebooks/{id}/emoji` 保存；上传失败时解析 409/400 展示「重复上传」「不支持格式」等提示；解析中可打开「解析等待」弹窗（内含贪吃蛇小游戏）。

---

## 🔄 实现流程与技术流程

### 实现流程（关键路径）

1. **主聊天页发送消息**
   - 用户输入 → `InputArea` 触发 `onSend` → `useChat.sendMessage(text, modelId, conversationId?, quickParseFiles?, ragContext?)`。
   - `sendMessage` 建立/复用 WebSocket，发送 `{ message, model_id, conversation_id?, rag_context?, quick_parse_files? }`。
   - 服务端流式返回 content 与 done；`useChat` 将 content 累加到 `streamingContent`，done 后追加到 `messages` 并清空流。
   - **滚动**：`Chat` 组件在消息/流更新后，在**可滚动祖先容器**内执行 `scrollTo({ top: scrollHeight })`，避免整页滚动导致「界面翻上去」。

2. **RAG 搜索页（wiki/search）**
   - 左侧知识源列表来自 `GET /api/rag/documents?notebook_id=...`，每项带 checkbox，仅勾选参与检索。
   - 用户发送问题时：先 `POST /api/rag/search`（body 含 `document_ids` 为勾选 id 列表，可为空）→ 用 `buildRAGContextFromHits` 拼成 `rag_context` 字符串 → 再 `sendMessage(text, modelId, null, null, rag_context)`。
   - 右侧「检索文档」展示 hits 为卡片：内容区用 `processMarkdownHtml(parseMarkdownWithLatex(ensureImageUrlsInContent(content)))` 渲染（表格/图片/公式）；卡片上「展开文件」打开弹窗，传入 `chunkId`/`chunkSnippet`，加载 markdown 接口后定位到对应 segment 并高亮。

3. **布局与滚动约束**
   - 主对话与 RAG 页均对中央 `.welcome` 使用 `min-height: 0` + `flex: 1 1 0`，保证对话区在视口内独立滚动；RAG 右侧栏 `min-height: 0` + `overflow-y: auto`，卡片再多也只右侧内部滚动。

### 技术流程（分层）

| 层级 | 说明 |
|------|------|
| 路由 | React Router：`/` 主聊天，`/wiki` 知识库仪表盘，`/wiki/search` RAG 检索与对话，`/login`、`/register` |
| 状态 | `useChat`（消息、流、WebSocket）、RAG 页（sources、retrievedDocs、expandDoc）、主题与侧栏开关 |
| 请求 | `fetch` / WebSocket；Vite 代理 `/api` 与 ws 到后端 8000；`ragApi.js` 封装 RAG 相关 API |
| 渲染 | Markdown+LaTeX（marked + KaTeX）、代码高亮（highlight.js）、RAG 卡片富文本与展开弹窗 |

> 原静态页面仍保留在 `index.html` 中被 Vite 接管；样式备份在 `css/main.css`，逻辑在 `js/main.js`。🧪
