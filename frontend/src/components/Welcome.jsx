import React from 'react';
import { Chat } from './Chat';
import { InputArea } from './InputArea';
import { getStoredUser } from '../utils/auth';
import logoImg from '../../img/Ling_Flowing_Logo.png';

export function Welcome({
  messages,
  streamingContent,
  isStreaming,
  onSend,
  onCancelStream,
}) {
  const user = getStoredUser();
  const displayName = user?.nickname || user?.username || user?.email || '用户';

  const hasChat = messages.length > 0 || !!streamingContent;
  const welcomeClass = `welcome${hasChat ? ' welcome--has-chat' : ''}`;

  return (
    <section className={welcomeClass}>
      <div className="welcome__inner animate-fade-in">
        <div className="welcome__head">
          <h1 className="welcome__title">
            <img src={logoImg} alt="" className="welcome__title-logo" />
            <span className="welcome__greeting">你好，{displayName}</span>
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
