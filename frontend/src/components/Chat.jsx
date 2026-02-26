import React, { useEffect, useRef } from 'react';
import { ChatMessage } from './ChatMessage';

export function Chat({ messages, streamingContent, isStreaming }) {
  const endRef = useRef(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth' });
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
