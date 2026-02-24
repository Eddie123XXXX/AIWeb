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

export function App() {
  const { toggleTheme } = useTheme();
  const [sidebarOpen, setSidebarOpen] = useState(() =>
    typeof window !== 'undefined' ? window.innerWidth >= 768 : true
  );

  const [conversationId, setConversationId] = useState(null);
  const [conversations, setConversations] = useState([]);
  const [loadingConversations, setLoadingConversations] = useState(false);

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

  const handleSelectConversation = useCallback(async (id) => {
    setSidebarOpen(false);
    try {
      const resp = await fetch(apiUrl(`/api/history/conversations/${id}`), {
        headers: getAuthHeaders(),
      });
      if (!resp.ok) return;
      const detail = await resp.json();
      setConversationId(detail.id);
      setMessages(
        (detail.messages || []).map((m) => ({
          role: m.role || 'user',
          content: m.content || '',
        }))
      );
    } catch {
      setConversationId(id);
      setMessages([]);
    }
  }, [setMessages]);

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
      let cid = conversationId;
      if (!cid) {
        const conv = await createConversation('新对话', modelId);
        if (conv) {
          cid = conv.id;
          setConversationId(cid);
          setConversations((prev) => [{ ...conv, title: conv.title || '新对话' }, ...prev]);
        }
        return sendMessage(text, modelId, cid ?? undefined);
      }
      return sendMessage(text, modelId);
    },
    [sendMessage, modelId, conversationId, createConversation]
  );

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
        />
        {hasChat && (
          <InputArea
            onSend={handleSendWithModel}
            isStreaming={isStreaming}
            onCancelStream={cancelStream}
            hasChat={hasChat}
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
