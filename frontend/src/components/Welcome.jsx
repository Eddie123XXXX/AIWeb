import React from 'react';
import { Chat } from './Chat';
import { InputArea } from './InputArea';
import { getStoredUser } from '../utils/auth';
import { useTranslation } from '../context/LocaleContext';
import logoImg from '../../img/Ling_Flowing_Logo.png';
import logoImgDark from '../../img/Image.png';

export function Welcome({
  messages,
  streamingContent,
  isStreaming,
  onSend,
  onCancelStream,
  onAttachFiles,
  attachedFiles = [],
  attachError = null,
  onRemoveAttachedFile,
}) {
  const t = useTranslation();
  const user = getStoredUser();
  const displayName = user?.nickname || user?.username || user?.email || t('user');

  const hasChat = messages.length > 0 || !!streamingContent;
  const welcomeClass = `welcome${hasChat ? ' welcome--has-chat' : ''}`;

  return (
    <section className={welcomeClass}>
      <div className="welcome__inner animate-fade-in">
        <div className="welcome__head">
          <h1 className="welcome__title">
            <span className="welcome__title-logo-wrap">
              <img src={logoImg} alt="" className="welcome__title-logo logo-img--light" />
              <img src={logoImgDark} alt="" className="welcome__title-logo logo-img--dark" />
            </span>
            <span className="welcome__greeting">{t('hello')}{displayName}</span>
          </h1>
          <p className="welcome__subtitle">{t('whatCanIDo')}</p>
        </div>

        {/* 还没有开始对话时，将输入框放在欢迎文案下方 */}
        {!hasChat && (
          <InputArea
            onSend={onSend}
            isStreaming={isStreaming}
            onCancelStream={onCancelStream}
            hasChat={false}
            onAttachFiles={onAttachFiles}
            attachedFiles={attachedFiles}
            attachError={attachError}
            onRemoveAttachedFile={onRemoveAttachedFile}
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
