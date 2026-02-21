# AI Workspace 前端（React 组件化）

本目录为 React + Vite 组件化前端，与原有静态 HTML/CSS/JS 功能一致。

## 技术栈

- **React 18** + **Vite 5**
- **marked**：Markdown 渲染
- **highlight.js**：代码高亮

## 项目结构

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
│   │   ├── ChatMessage.jsx # 单条消息（支持 Markdown/代码高亮/复制）
│   │   └── InputArea.jsx # 输入框与发送
│   ├── hooks/
│   │   ├── useTheme.js   # 亮/暗主题与 localStorage
│   │   └── useChat.js    # WebSocket 聊天与流式输出
│   └── utils/
│       └── markdown.js   # Markdown 解析、代码高亮、复制
├── css/main.css        # 原静态版样式（保留）
└── js/main.js          # 原静态版逻辑（保留）
```

## 开发与构建

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

## 当前界面与路由（开发环境 base: http://localhost:5173）

| 路径 | 说明 |
|------|------|
| `/login` | 登录页（未登录时入口，邮箱+密码登录） |
| `/register` | 注册页（邮箱、密码、用户名、手机号，对应后端 users 表） |
| `/` | 主聊天页（首页，需登录） |
| `/wiki` | RAG 知识库 / 仪表盘（需登录） |
| `/wiki/search` | RAG 搜索页（需登录） |

未登录访问 `/`、`/wiki`、`/wiki/search` 会重定向到 `/login`；已登录访问 `/login` 或 `/register` 会重定向到 `/`。

## 与后端联调

1. 启动后端：`cd backend && uvicorn main:app --reload`
2. 启动前端：`cd frontend && npm run dev`
3. 浏览器访问 http://localhost:5173，前端会通过 Vite 代理将 `/api` 和 WebSocket 请求转发到 8000 端口。

## 功能说明

- **主题**：`useTheme` 管理亮/暗主题并写入 `data-theme` 与 localStorage。
- **侧边栏**：移动端通过 Header 菜单按钮展开/收起，`Sidebar` 受控于 `sidebarOpen` 状态。
- **聊天**：`useChat` 维护消息列表、流式内容与 WebSocket，发送/暂停与原有逻辑一致；`ChatMessage` 对 assistant 消息做 Markdown 渲染与代码块复制。

原静态页面仍保留在 `index.html` 被替换为 Vite 入口；样式备份在 `css/main.css`，逻辑备份在 `js/main.js`。
