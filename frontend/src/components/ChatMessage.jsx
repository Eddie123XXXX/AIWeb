import React, { useMemo, useEffect, useRef } from 'react';
import { parseMarkdown, processMarkdownHtml, copyToClipboard } from '../utils/markdown';
import { useTranslation } from '../context/LocaleContext';
import pdfIcon from '../../img/file type icon/PDF (1).png';
import wordIcon from '../../img/file type icon/DOCX.png';
import sheetIcon from '../../img/file type icon/XLS.png';
import textIcon from '../../img/file type icon/DOCX.png';
import genericFileIcon from '../../img/file type icon/DOCX.png';

export function ChatMessage({ role, content, isMarkdown, files, isFiles, isQuickParseNotice }) {
  const isUser = role === 'user';
  const containerRef = useRef(null);
  const t = useTranslation();

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

  // 文件预览消息：作为用户消息的一部分展示附件
  if (isFiles && Array.isArray(files) && files.length > 0) {
    return (
      <div className="chat__file-message">
        <div className="chat__file-list">
          {files.map((file, index) => {
            const name = file.filename || file.name || '未命名文件';
            const ext = name.includes('.') ? name.split('.').pop().toLowerCase() : '';
            let typeLabel = '文件';
            let typeClass = 'other';
            let iconSrc = genericFileIcon;
            if (ext === 'pdf') {
              typeLabel = 'PDF';
              typeClass = 'pdf';
              iconSrc = pdfIcon;
            } else if (ext === 'doc' || ext === 'docx') {
              typeLabel = 'Word';
              typeClass = 'word';
              iconSrc = wordIcon;
            } else if (ext === 'xls' || ext === 'xlsx' || ext === 'csv') {
              typeLabel = '表格';
              typeClass = 'sheet';
              iconSrc = sheetIcon;
            } else if (ext === 'txt') {
              typeLabel = '文本';
              typeClass = 'text';
              iconSrc = textIcon;
            }
            const shortName =
              name.length > 24 ? `${name.slice(0, 10)}...${name.slice(-8)}` : name;

            return (
              <button
                key={`${name}-${index}`}
                type="button"
                className="chat__file-pill"
                aria-label={name}
              >
                <img
                  className={`chat__file-icon-img chat__file-icon-img--${typeClass}`}
                  src={iconSrc}
                  alt={`${typeLabel} icon`}
                />
                <div className="chat__file-meta">
                  <div className="chat__file-name" title={name}>
                    {shortName}
                  </div>
                  <div className="chat__file-type">{typeLabel}</div>
                </div>
              </button>
            );
          })}
        </div>
        <div className="chat__file-notice">
          {t('quickParseNotice')}
        </div>
      </div>
    );
  }

  // Quick Parse 提示消息：弱提示样式
  if (isQuickParseNotice && !isUser) {
    return (
      <div className="chat__message chat__message--assistant chat__message--notice">
        {content}
      </div>
    );
  }

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

