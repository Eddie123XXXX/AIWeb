import React from 'react';
import { Chat } from './Chat';
import { InputArea } from './InputArea';

const USER_NAME = 'Eddie';

export function Welcome({
  messages,
  streamingContent,
  isStreaming,
  onSend,
  onCancelStream,
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

        {/* 还没有开始对话时，将输入框放在欢迎文案下方 */}
        {!hasChat && (
          <InputArea
            onSend={onSend}
            isStreaming={isStreaming}
            onCancelStream={onCancelStream}
            hasChat={false}
          />
        )}

        <Chat
          messages={messages}
          streamingContent={streamingContent}
          isStreaming={isStreaming}
        />
      </div>
    </section>
  );
}
