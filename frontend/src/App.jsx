import React, { useState, useCallback, useEffect, useMemo } from 'react';
import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { Sidebar } from './components/Sidebar';
import { Header } from './components/Header';
import { Welcome } from './components/Welcome';
import { InputArea } from './components/InputArea';
import { RAGDashboard } from './pages/RAGDashboard';
import { RAGSearch } from './pages/RAGSearch';
import { useTheme } from './hooks/useTheme';
import { useChat } from './hooks/useChat';

export function App() {
  const { toggleTheme } = useTheme();
  const [sidebarOpen, setSidebarOpen] = useState(() =>
    typeof window !== 'undefined' ? window.innerWidth >= 768 : true
  );

  const {
    messages,
    streamingContent,
    isStreaming,
    sendMessage,
    cancelStream,
  } = useChat();

  // 从后端动态加载模型列表，并与前端选择联动
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

  useEffect(() => {
    let cancelled = false;

    const loadModels = async () => {
      try {
        const resp = await fetch('/api/models');
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
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const currentModel = useMemo(
    () =>
      models.find((m) => m.id === modelId) ??
      (models.length > 0 ? models[0] : null),
    [models, modelId]
  );

  const handleToggleSidebar = useCallback(() => {
    setSidebarOpen((prev) => !prev);
  }, []);

  const handleNewChat = useCallback(() => {
    setSidebarOpen(false);
    // 可在此清空对话或跳转新会话
  }, []);

  const handleSendWithModel = useCallback(
    (text) => {
      return sendMessage(text, modelId);
    },
    [sendMessage, modelId]
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
    <BrowserRouter>
      <Routes>
        <Route path="/" element={chatPage} />
        <Route path="/wiki" element={<RAGDashboard />} />
        <Route
          path="/wiki/search"
          element={
            <RAGSearch
              models={models}
              currentModel={currentModel}
              defaultModelId={defaultModelId}
              onModelChange={handleModelChange}
            />
          }
        />
      </Routes>
    </BrowserRouter>
  );
}
