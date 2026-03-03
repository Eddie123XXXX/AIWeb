import React, { useEffect, useRef, useState } from 'react';
import { ChatMessage } from './ChatMessage';
import { AgenticReasoningPanel } from './AgenticReasoningPanel';

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

export function Chat({
  messages,
  streamingContent,
  isStreaming,
  agenticEnabled = false,
  agenticEvents = [],
  agenticStatus = null,
}) {
  const endRef = useRef(null);
  const [panelExpanded, setPanelExpanded] = useState(false);

  const getTraceForUserAt = (userIndex) => {
    for (let j = userIndex + 1; j < messages.length; j += 1) {
      // 到下一条 user 说明这一轮边界结束
      if (messages[j]?.role === 'user') break;
      const trace = messages[j]?.metadata?.agentic_trace;
      if (messages[j]?.role === 'assistant' && trace?.events?.length > 0) {
        return trace;
      }
    }
    return null;
  };

  const lastUserIndex = [...messages].map((m) => m.role).lastIndexOf('user');
  const hasHistoricalTraceForLastUser =
    lastUserIndex >= 0 && !!getTraceForUserAt(lastUserIndex);
  // 实时面板：用户发问后立刻显示“思考中”，不依赖是否已收到推理事件；
  // 若历史 trace 已可用，则优先展示历史面板避免重复。
  const shouldShowLiveAgenticPanel =
    agenticEnabled && isStreaming && lastUserIndex >= 0 && !hasHistoricalTraceForLastUser;
  const insertAfterUserIndex = shouldShowLiveAgenticPanel ? lastUserIndex : -1;

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
        <React.Fragment key={i}>
          <ChatMessage
            role={msg.role}
            content={msg.content}
            isMarkdown={msg.role === 'assistant'}
            files={msg.files}
            isFiles={msg.isFiles}
            isQuickParseNotice={msg.isQuickParseNotice}
          />
          {/* 历史面板：从紧随其后的 assistant.metadata.agentic_trace 恢复 */}
          {agenticEnabled &&
            msg.role === 'user' &&
            (() => {
              const trace = getTraceForUserAt(i);
              if (!trace) return null;
              return (
                <AgenticReasoningPanel
                  events={trace.events}
                  status={trace.status || 'done'}
                  isStreaming={false}
                  expanded={panelExpanded}
                  onToggle={() => setPanelExpanded((prev) => !prev)}
                />
              );
            })()}
          {/* 实时面板：当前轮尚未写入 assistant 前使用 */}
          {shouldShowLiveAgenticPanel && i === insertAfterUserIndex && (
            <AgenticReasoningPanel
              events={agenticEvents}
              status={agenticStatus}
              isStreaming={isStreaming}
              expanded={panelExpanded}
              onToggle={() => setPanelExpanded((prev) => !prev)}
            />
          )}
        </React.Fragment>
      ))}

      {shouldShowLiveAgenticPanel && insertAfterUserIndex < 0 && (
        <AgenticReasoningPanel
          events={agenticEvents}
          status={agenticStatus}
          isStreaming={isStreaming}
          expanded={panelExpanded}
          onToggle={() => setPanelExpanded((prev) => !prev)}
        />
      )}

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
