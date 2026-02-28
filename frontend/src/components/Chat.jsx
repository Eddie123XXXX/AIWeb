import React, { useEffect, useRef } from 'react';
import { ChatMessage } from './ChatMessage';

/** 找到第一个可滚动的祖先，在其内部滚到底部，避免滚动整页导致「界面翻上去」 */
function scrollChatContainerToBottom(endEl) {
  if (!endEl) return;
  let el = endEl.parentElement;
  while (el) {
    const style = window.getComputedStyle(el);
    const overflowY = style.overflowY;
    const canScroll = overflowY === 'auto' || overflowY === 'scroll' || overflowY === 'overlay';
    if (canScroll && el.scrollHeight > el.clientHeight) {
      el.scrollTo({ top: el.scrollHeight, behavior: 'smooth' });
      return;
    }
    el = el.parentElement;
  }
}

export function Chat({ messages, streamingContent, isStreaming }) {
  const endRef = useRef(null);

  useEffect(() => {
    const endEl = endRef.current;
    if (!endEl) return;
    requestAnimationFrame(() => {
      requestAnimationFrame(() => {
        scrollChatContainerToBottom(endEl);
      });
    });
  }, [messages, streamingContent]);

  return (
    <div className="chat" id="chatMessages" aria-live="polite">
      {messages.map((msg, i) => (
        <ChatMessage
          key={i}
          role={msg.role}
          content={msg.content}
          isMarkdown={msg.role === 'assistant'}
          files={msg.files}
          isFiles={msg.isFiles}
          isQuickParseNotice={msg.isQuickParseNotice}
        />
      ))}
      {streamingContent ? (
        <ChatMessage
          role="assistant"
          content={streamingContent || '...'}
          isMarkdown
        />
      ) : null}
      <div ref={endRef} />
    </div>
  );
}
