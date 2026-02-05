import React from 'react';
import { Chat } from './Chat';

const USER_NAME = 'Eddie';

export function Welcome({
  messages,
  streamingContent,
  isStreaming,
}) {
  const hasChat = messages.length > 0 || !!streamingContent;
  const welcomeClass = `welcome${hasChat ? ' welcome--has-chat' : ''}`;

  return (
    <section className={welcomeClass}>
      <div className="welcome__inner animate-fade-in">
        <div className="welcome__head">
          <h1 className="welcome__title">
            <span className="welcome__greeting">你好，{USER_NAME}</span>
          </h1>
          <p className="welcome__subtitle">今天想让我帮你做点什么？</p>
        </div>
        <Chat
          messages={messages}
          streamingContent={streamingContent}
          isStreaming={isStreaming}
        />
      </div>
    </section>
  );
}
