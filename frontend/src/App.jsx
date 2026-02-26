import React, { useState, useCallback, useEffect, useMemo } from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';

const routerFuture = { v7_startTransition: true, v7_relativeSplatPath: true };
import { Sidebar } from './components/Sidebar';
import { Header } from './components/Header';
import { Welcome } from './components/Welcome';
import { InputArea } from './components/InputArea';
import { getStoredToken, setStoredToken, getAuthHeaders, clearAuth } from './utils/auth';
import { apiUrl } from './utils/api';
import { Login } from './pages/Login';
import { Register } from './pages/Register';
import { RAGDashboard } from './pages/RAGDashboard';
import { RAGSearch } from './pages/RAGSearch';
import { Profile } from './pages/Profile';
import { useTheme } from './hooks/useTheme';
import { useChat } from './hooks/useChat';
import { useTranslation } from './context/LocaleContext';

const ATTACHMENTS_STORAGE_KEY = 'chat-file-attachments';

function loadAttachmentsMap() {
  if (typeof window === 'undefined') return {};
  try {
    const raw = window.localStorage.getItem(ATTACHMENTS_STORAGE_KEY);
    if (!raw) return {};
    const parsed = JSON.parse(raw);
    return parsed && typeof parsed === 'object' ? parsed : {};
  } catch {
    return {};
  }
}

function saveAttachmentsMap(map) {
  if (typeof window === 'undefined') return;
  try {
    window.localStorage.setItem(ATTACHMENTS_STORAGE_KEY, JSON.stringify(map));
  } catch {
    // ignore
  }
}

function getConversationAttachments(conversationId) {
  if (!conversationId) return [];
  const map = loadAttachmentsMap();
  const list = map[conversationId];
  return Array.isArray(list) ? list : [];
}

function addConversationAttachment(conversationId, entry) {
  if (!conversationId) return;
  const map = loadAttachmentsMap();
  const list = Array.isArray(map[conversationId]) ? map[conversationId] : [];
  list.push(entry);
  map[conversationId] = list;
  saveAttachmentsMap(map);
}

export function App() {
  const { toggleTheme } = useTheme();
  const t = useTranslation();
  const [sidebarOpen, setSidebarOpen] = useState(() =>
    typeof window !== 'undefined' ? window.innerWidth >= 768 : true
  );

  const [conversationId, setConversationId] = useState(null);
  const [conversations, setConversations] = useState([]);
  const [loadingConversations, setLoadingConversations] = useState(false);

  // Quick Parse：当前轮附加文件（已上传到 MinIO 并拿到可访问 URL）
  const [quickParseFiles, setQuickParseFiles] = useState([]);
  // Quick Parse 上传错误提示（如格式不支持、文件过大），仅存错误类型与文件名，实际文案由多语言渲染
  const [attachError, setAttachError] = useState(null);

  const [models, setModels] = useState([]);
  const [modelId, setModelId] = useState(() =>
    typeof window !== 'undefined'
      ? window.localStorage.getItem('default-model-id') || null
      : null
  );
  // 单独维护一个“默认模型 ID”，用于控制前端的默认标记与实心星图标
  // 说明：
  // - 如果 localStorage 里没有记录，则认为当前暂时没有默认模型（null）
  // - 只有在用户点击“设为默认”时，才会把某个模型 id 写入 default-model-id
  const [defaultModelId, setDefaultModelId] = useState(() =>
    typeof window !== 'undefined'
      ? window.localStorage.getItem('default-model-id')
      : null
  );

  // 个人中心弹窗（不占用路由）
  const [profileModalOpen, setProfileModalOpen] = useState(false);

  // 用 state 存 token，登录成功后 setToken 触发重渲染，才能正确从登录页跳转到首页
  const [token, setTokenState] = useState(() => getStoredToken());
  const setToken = useCallback((newToken) => {
    if (newToken) setStoredToken(newToken);
    else clearAuth();
    setTokenState(newToken);
  }, []);

  // 从后端动态加载模型列表，并与前端选择联动
  useEffect(() => {
    if (!token) return;
    let cancelled = false;

    const loadModels = async () => {
      try {
        const resp = await fetch(apiUrl('/api/models'), { headers: getAuthHeaders() });
        if (!resp.ok) return;
        const data = await resp.json();
        if (cancelled) return;

        const mapped = (Array.isArray(data) ? data : []).map((m) => ({
          id: m.id,
          label: m.display_name ?? m.name ?? m.id,
          provider: m.provider,
        }));
        setModels(mapped);

        if (mapped.length > 0) {
          const exists = mapped.some((m) => m.id === modelId);
          if (!exists) {
            const defaultModel =
              mapped.find((m) => m.id === 'default') || mapped[0];
            setModelId(defaultModel.id);
          }
        }
      } catch {
        // ignore load errors
      }
    };

    loadModels();

    return () => {
      cancelled = true;
    };
  }, [token]);

  const loadConversations = useCallback(
    async (onUnauthorized) => {
      const headers = getAuthHeaders();
      if (!headers.Authorization) {
        if (onUnauthorized) onUnauthorized();
        return;
      }
      setLoadingConversations(true);
      try {
        const resp = await fetch(apiUrl('/api/history/conversations?page=1&page_size=50'), {
          headers,
        });
        if (resp.status === 401) {
          if (onUnauthorized) onUnauthorized();
          return;
        }
        if (!resp.ok) return;
        const data = await resp.json();
        setConversations(Array.isArray(data) ? data : []);
      } catch {
        setConversations([]);
      } finally {
        setLoadingConversations(false);
      }
    },
    []
  );

  useEffect(() => {
    if (!token) return;
    loadConversations(() => setToken(null));
  }, [token, loadConversations, setToken]);

  const handleRoundComplete = useCallback(
    (completedConversationId) => {
      if (completedConversationId) setConversationId(completedConversationId);
      // 首轮结束后后端会异步生成标题，延迟刷新侧栏列表以显示新标题
      setTimeout(() => loadConversations(() => setToken(null)), 2500);
    },
    [loadConversations, setToken]
  );

  const {
    messages,
    setMessages,
    streamingContent,
    isStreaming,
    sendMessage,
    cancelStream,
  } = useChat(conversationId, { onRoundComplete: handleRoundComplete });

  const currentModel = useMemo(
    () =>
      models.find((m) => m.id === modelId) ??
      (models.length > 0 ? models[0] : null),
    [models, modelId]
  );

  const handleToggleSidebar = useCallback(() => {
    setSidebarOpen((prev) => !prev);
  }, []);

  const createConversation = useCallback(
    async (title = '新对话', modelId = null) => {
      const body = { title };
      if (modelId) body.model_id = modelId;
      const resp = await fetch(apiUrl('/api/history/conversations'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...getAuthHeaders() },
        body: JSON.stringify(body),
      });
      if (!resp.ok) return null;
      return resp.json();
    },
    []
  );

  const handleNewChat = useCallback(async () => {
    setSidebarOpen(false);
    try {
      const conv = await createConversation('新对话', modelId);
      if (!conv) return;
      setConversationId(conv.id);
      setMessages([]);
      setConversations((prev) => [{ ...conv, title: conv.title || '新对话' }, ...prev]);
    } catch {
      setConversationId(null);
      setMessages([]);
    }
  }, [setMessages, createConversation, modelId]);

  const handleSelectConversation = useCallback(
    async (id) => {
      setSidebarOpen(false);
      try {
        const resp = await fetch(apiUrl(`/api/history/conversations/${id}`), {
          headers: getAuthHeaders(),
        });
        if (!resp.ok) return;
        const detail = await resp.json();
        setConversationId(detail.id);

        const baseMessages = (detail.messages || []).map((m) => ({
          role: m.role || 'user',
          content: m.content || '',
        }));

        const attachments = getConversationAttachments(detail.id).slice().sort((a, b) => {
          return (a.textIndex || 0) - (b.textIndex || 0);
        });

        if (!attachments.length) {
          setMessages(baseMessages);
          return;
        }

        const enhanced = [];
        let textIndex = 0;
        let attIdx = 0;

        for (const msg of baseMessages) {
          while (attIdx < attachments.length && textIndex === (attachments[attIdx].textIndex || 0)) {
            const att = attachments[attIdx];
            if (att.files && att.files.length) {
              enhanced.push({
                role: 'user',
                content: '',
                files: att.files,
                isFiles: true,
              });
            }
            attIdx += 1;
          }
          enhanced.push(msg);
          textIndex += 1;
        }

        setMessages(enhanced);
      } catch {
        setConversationId(id);
        setMessages([]);
      }
    },
    [setMessages]
  );

  const handleRenameConversation = useCallback(async (id, newTitle) => {
    try {
      const resp = await fetch(apiUrl(`/api/history/conversations/${id}`), {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json', ...getAuthHeaders() },
        body: JSON.stringify({ title: newTitle }),
      });
      if (!resp.ok) return;
      setConversations((prev) =>
        prev.map((c) => (c.id === id ? { ...c, title: newTitle } : c))
      );
    } catch {
      loadConversations(() => setToken(null));
    }
  }, [loadConversations, setToken]);

  const handleDeleteConversation = useCallback(
    async (id) => {
      try {
        const resp = await fetch(apiUrl(`/api/history/conversations/${id}`), {
          method: 'DELETE',
          headers: getAuthHeaders(),
        });
        if (!resp.ok) return;
        setConversations((prev) => prev.filter((c) => c.id !== id));
        if (conversationId === id) {
          setConversationId(null);
          setMessages([]);
        }
      } catch {
        loadConversations(() => setToken(null));
      }
    },
    [conversationId, setMessages, loadConversations, setToken]
  );

  const handleSendWithModel = useCallback(
    async (text) => {
      const filesForThisRound = quickParseFiles;
      const hasFiles = filesForThisRound.length > 0;
      // 当前已有的纯文本消息数量（不含前端文件预览消息）
      const textIndexBefore = messages.filter((m) => !m.isFiles).length;

      let cid = conversationId;
      if (!cid) {
        const conv = await createConversation('新对话', modelId);
        if (conv) {
          cid = conv.id;
          setConversationId(cid);
          setConversations((prev) => [{ ...conv, title: conv.title || '新对话' }, ...prev]);
        }
        if (hasFiles && cid) {
          addConversationAttachment(cid, { textIndex: textIndexBefore, files: filesForThisRound });
        }
        if (hasFiles) {
          setQuickParseFiles([]);
          setAttachError(null);
        }
        return sendMessage(text, modelId, cid ?? undefined, filesForThisRound);
      }

      if (hasFiles && cid) {
        addConversationAttachment(cid, { textIndex: textIndexBefore, files: filesForThisRound });
      }
      if (hasFiles) {
        setQuickParseFiles([]);
        setAttachError(null);
      }
      return sendMessage(text, modelId, null, filesForThisRound);
    },
    [sendMessage, modelId, conversationId, createConversation, quickParseFiles, messages]
  );

  const handleAttachFiles = useCallback(
    async (fileList) => {
      if (!token) return;
      const headers = getAuthHeaders();
      const files = Array.isArray(fileList) ? fileList : [];
      if (files.length === 0) return;

       // 前端快速校验：类型与大小
      const MAX_SIZE = 20 * 1024 * 1024; // 20MB 单文件大小上限
      const SUPPORTED_EXTS = ['pdf', 'docx', 'xlsx', 'xls', 'csv', 'txt'];
      // 仅记录错误类型和文件名，具体文案交给多语言渲染
      let lastError = null;

      const validFiles = files.filter((file) => {
        const name = file.name || '';
        const ext = name.includes('.') ? name.split('.').pop().toLowerCase() : '';
        if (!SUPPORTED_EXTS.includes(ext)) {
          lastError = { type: 'unsupported', filename: name };
          return false;
        }
        if (typeof file.size === 'number' && file.size > MAX_SIZE) {
          lastError = { type: 'tooLarge', filename: name };
          return false;
        }
        return true;
      });

      // 去重：不允许重复附加同名且大小相同的文件
      const existingKeys = new Set(
        quickParseFiles.map((f) =>
          `${(f.filename || '').toLowerCase()}::${typeof f.size === 'number' ? f.size : 0}`
        )
      );
      const dedupedFiles = [];
      for (const file of validFiles) {
        const key = `${(file.name || '').toLowerCase()}::${typeof file.size === 'number' ? file.size : 0}`;
        if (existingKeys.has(key)) {
          lastError = { type: 'duplicated', filename: file.name };
          continue;
        }
        existingKeys.add(key);
        dedupedFiles.push(file);
      }

      setAttachError(lastError);

      if (dedupedFiles.length === 0) {
        return;
      }

      try {
        const uploaded = [];
        for (const file of dedupedFiles) {
          const formData = new FormData();
          formData.append('file', file);
          const uploadResp = await fetch(apiUrl('/api/infra/minio/upload'), {
            method: 'POST',
            headers: {
              ...headers,
              // 不手动设置 Content-Type，交由浏览器生成 multipart 边界
            },
            body: formData,
          });
          if (!uploadResp.ok) {
            // eslint-disable-next-line no-console
            console.error('上传失败', await uploadResp.text());
            continue;
          }
          const uploadData = await uploadResp.json();
          // 优先使用上传接口直接返回的预签名 URL
          let fileUrl = uploadData.url;
          const objectName = uploadData.object_name;
          // 兼容老版本：如 upload 未返回 url，则回退调用 /url 接口
          if (!fileUrl && objectName) {
            const urlResp = await fetch(
              apiUrl(`/api/infra/minio/url/${encodeURIComponent(objectName)}`),
              { headers }
            );
            if (!urlResp.ok) {
              // eslint-disable-next-line no-console
              console.error('预签名 URL 获取失败', await urlResp.text());
              continue;
            }
            const urlData = await urlResp.json();
            if (!urlData.url) continue;
            fileUrl = urlData.url;
          }
          if (!fileUrl) continue;
          uploaded.push({
            url: fileUrl,
            filename: file.name,
            mime_type: file.type || uploadData.content_type || 'application/octet-stream',
            size: typeof file.size === 'number' ? file.size : uploadData.size,
          });
        }
        if (uploaded.length > 0) {
          setQuickParseFiles((prev) => [...prev, ...uploaded]);
        }
      } catch (e) {
        // eslint-disable-next-line no-console
        console.error('附加文件失败', e);
      }
    },
    [token, quickParseFiles]
  );

  const handleRemoveAttachedFile = useCallback((index) => {
    setQuickParseFiles((prev) => prev.filter((_, i) => i !== index));
  }, []);

  // 切换模型时，同时支持“设为默认”持久化到 localStorage，并更新默认模型 ID
  // 行为：
  // - setAsDefault === false：只切换当前使用的模型，不影响默认模型
  // - setAsDefault === true 且当前不是默认：将该模型设为默认（写入 defaultModelId + localStorage）
  // - setAsDefault === true 且当前已经是默认：取消默认（defaultModelId 置为 null，并写入 special 标记）
  const handleModelChange = useCallback(
    (id, setAsDefault = false) => {
      setModelId(id);
      if (setAsDefault) {
        // 如果当前就是默认模型，则再次点击视为“取消默认”
        if (defaultModelId && id === defaultModelId) {
          setDefaultModelId(null);
          if (typeof window !== 'undefined') {
            window.localStorage.setItem('default-model-id', '__none__');
          }
          return;
        }

        // 否则将该模型设为默认
        setDefaultModelId(id);
        if (typeof window !== 'undefined') {
          window.localStorage.setItem('default-model-id', id);
        }
      }
    },
    [defaultModelId]
  );

  const hasChat = messages.length > 0 || !!streamingContent;

  const chatPage = (
    <div className="app-root">
      <Sidebar
        isOpen={sidebarOpen}
        onToggle={handleToggleSidebar}
        onNewChat={handleNewChat}
        onLogout={() => setToken(null)}
        onOpenProfile={() => setProfileModalOpen(true)}
        conversations={conversations}
        currentConversationId={conversationId}
        onSelectConversation={handleSelectConversation}
        onRenameConversation={handleRenameConversation}
        onDeleteConversation={handleDeleteConversation}
        loadingConversations={loadingConversations}
      />
      <main className="main">
        <Header
          onThemeToggle={toggleTheme}
          onMobileMenuToggle={handleToggleSidebar}
          currentModel={currentModel}
          models={models}
          defaultModelId={defaultModelId}
          onModelChange={handleModelChange}
        />
        <Welcome
          messages={messages}
          streamingContent={streamingContent}
          isStreaming={isStreaming}
          onSend={handleSendWithModel}
          onCancelStream={cancelStream}
          onAttachFiles={handleAttachFiles}
          attachedFiles={quickParseFiles}
          attachError={attachError}
          onRemoveAttachedFile={handleRemoveAttachedFile}
        />
        {hasChat && (
          <InputArea
            onSend={handleSendWithModel}
            isStreaming={isStreaming}
            onCancelStream={cancelStream}
            hasChat={hasChat}
            onAttachFiles={handleAttachFiles}
            attachedFiles={quickParseFiles}
            attachError={attachError}
            onRemoveAttachedFile={handleRemoveAttachedFile}
          />
        )}
      </main>
    </div>
  );

  return (
    <BrowserRouter future={routerFuture}>
      <Routes>
        <Route
          path="/login"
          element={token ? <Navigate to="/" replace /> : <Login onLoginSuccess={setToken} />}
        />
        <Route
          path="/register"
          element={token ? <Navigate to="/" replace /> : <Register />}
        />
        <Route
          path="/"
          element={!token ? <Navigate to="/login" replace /> : chatPage}
        />
        <Route
          path="/wiki"
          element={!token ? <Navigate to="/login" replace /> : <RAGDashboard />}
        />
        <Route
          path="/wiki/search"
          element={
            !token ? (
              <Navigate to="/login" replace />
            ) : (
              <RAGSearch
                models={models}
                currentModel={currentModel}
                defaultModelId={defaultModelId}
                onModelChange={handleModelChange}
                onLogout={() => setToken(null)}
                onOpenProfile={() => setProfileModalOpen(true)}
              />
            )
          }
        />
      </Routes>
      {token && profileModalOpen && (
        <div
          className="profile-modal-overlay"
          role="dialog"
          aria-modal="true"
          aria-labelledby="profile-modal-title"
        >
          <div
            className="profile-modal-backdrop"
            onClick={() => setProfileModalOpen(false)}
          />
          <div className="profile-modal-panel" onClick={(e) => e.stopPropagation()}>
            <Profile onClose={() => setProfileModalOpen(false)} />
          </div>
        </div>
      )}
    </BrowserRouter>
  );
}
