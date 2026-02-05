import React, { useMemo, useEffect, useRef } from 'react';
import { parseMarkdown, processMarkdownHtml, copyToClipboard } from '../utils/markdown';

export function ChatMessage({ role, content, isMarkdown }) {
  const isUser = role === 'user';
  const containerRef = useRef(null);

  const html = useMemo(() => {
    if (isUser || !content) return null;
    if (!isMarkdown) return null;
    const raw = parseMarkdown(content);
    return processMarkdownHtml(raw);
  }, [content, isUser, isMarkdown]);

  useEffect(() => {
    if (!containerRef.current || !html) return;
    const buttons = containerRef.current.querySelectorAll('.code-copy-btn');
    const cleanups = [];
    buttons.forEach((btn) => {
      const handler = () => {
        const pre = btn.closest('pre');
        const code = pre?.querySelector('code');
        const text = code ? code.textContent || '' : '';
        copyToClipboard(text).catch(() => {});
      };
      btn.addEventListener('click', handler);
      cleanups.push(() => btn.removeEventListener('click', handler));
    });
    return () => cleanups.forEach((fn) => fn());
  }, [html]);

  if (isUser) {
    return (
      <div className="chat__message chat__message--user">
        {content}
      </div>
    );
  }

  if (html) {
    return (
      <div
        ref={containerRef}
        className="chat__message chat__message--assistant chat__message--markdown"
        dangerouslySetInnerHTML={{ __html: html }}
      />
    );
  }

  return (
    <div className="chat__message chat__message--assistant">
      {content}
    </div>
  );
}

