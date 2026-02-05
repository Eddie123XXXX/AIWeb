import React, { useState, useCallback } from 'react';
import { Sidebar } from './components/Sidebar';
import { Header } from './components/Header';
import { Welcome } from './components/Welcome';
import { InputArea } from './components/InputArea';
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

  const handleToggleSidebar = useCallback(() => {
    setSidebarOpen((prev) => !prev);
  }, []);

  const handleNewChat = useCallback(() => {
    setSidebarOpen(false);
    // 可在此清空对话或跳转新会话
  }, []);

  return (
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
        />
        <Welcome
          messages={messages}
          streamingContent={streamingContent}
          isStreaming={isStreaming}
        />
        <InputArea
          onSend={sendMessage}
          isStreaming={isStreaming}
          onCancelStream={cancelStream}
        />
      </main>
    </div>
  );
}
