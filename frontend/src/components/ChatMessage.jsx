import React, { useMemo, useEffect, useRef, useState, lazy, Suspense } from 'react';
import { createPortal } from 'react-dom';
import { parseMarkdown, processMarkdownHtml, copyToClipboard } from '../utils/markdown';
import { useTranslation } from '../context/LocaleContext';
import pdfIcon from '../../img/file type icon/PDF (1).png';
import wordIcon from '../../img/file type icon/DOCX.png';
import sheetIcon from '../../img/file type icon/XLS.png';
import textIcon from '../../img/file type icon/DOCX.png';
import genericFileIcon from '../../img/file type icon/DOCX.png';

const EChartsRenderer = lazy(() => import('./EChartsRenderer'));
const TableRendererLazy = lazy(() =>
  import('./EChartsRenderer').then((m) => ({ default: m.TableRenderer }))
);

const CHART_PLACEHOLDER_RE = /<!--CHART_(\d+)-->/g;

/**
 * 将带占位符的 HTML 拆分为 [html0, html1, ...]，图表作为独立 React 节点穿插渲染，
 * 流式更新时仅替换各 html 段，图表 DOM 保持稳定，避免屏闪。
 */
function splitHtmlByCharts(html, charts) {
  if (!html || charts.length === 0) return null;
  const parts = html.split(/<!--CHART_\d+-->/);
  if (parts.length !== charts.length + 1) return null;
  return { parts, charts };
}

function tryParseChartJson(text) {
  try {
    const obj = JSON.parse(text);
    if (obj && typeof obj === 'object' && (obj.echarts_option || obj.type === 'table')) {
      return obj;
    }
  } catch { /* not chart json */ }
  return null;
}

/**
 * 在 markdown HTML 中查找 ```chart 代码块（marked 会转为 <pre><code class="language-chart">），
 * 以及任何包含 echarts_option 的 JSON 代码块，替换为占位符。
 */
function extractChartBlocks(html) {
  if (!html) return { html, charts: [] };

  const div = document.createElement('div');
  div.innerHTML = html;
  const charts = [];

  div.querySelectorAll('pre').forEach((pre) => {
    const codeEl = pre.querySelector('code');
    if (!codeEl) return;

    const isChartLang =
      codeEl.className.includes('language-chart') ||
      codeEl.className.includes('language-echart');
    const raw = codeEl.textContent || '';
    const parsed = tryParseChartJson(raw.trim());

    if (isChartLang || parsed) {
      if (parsed) {
        const idx = charts.length;
        charts.push(parsed);
        const placeholder = document.createComment(`CHART_${idx}`);
        pre.replaceWith(placeholder);
      }
    }
  });

  return { html: div.innerHTML, charts };
}

function ChartPortals({ containerRef, charts }) {
  const [targets, setTargets] = useState([]);

  useEffect(() => {
    if (!containerRef.current || charts.length === 0) return;

    const nodes = [];
    const walker = document.createTreeWalker(
      containerRef.current,
      NodeFilter.SHOW_COMMENT,
      null
    );
    while (walker.nextNode()) {
      const comment = walker.currentNode;
      const match = comment.nodeValue?.match(/^CHART_(\d+)$/);
      if (match) {
        const idx = parseInt(match[1], 10);
        let wrapper = comment.nextElementSibling;
        if (!wrapper || !wrapper.classList?.contains('echart-portal')) {
          wrapper = document.createElement('div');
          wrapper.className = 'echart-portal';
          comment.parentNode.insertBefore(wrapper, comment.nextSibling);
        }
        nodes.push({ idx, el: wrapper });
      }
    }
    setTargets(nodes);
  }, [containerRef, charts]);

  return targets.map(({ idx, el }) => {
    const config = charts[idx];
    if (!config) return null;
    const isTable = config.type === 'table';
    return createPortal(
      <Suspense fallback={<div className="echart-loading">加载图表中...</div>}>
        {isTable ? <TableRendererLazy config={config} /> : <EChartsRenderer config={config} />}
      </Suspense>,
      el,
      `chart-${idx}`
    );
  });
}

export function ChatMessage({ role, content, isMarkdown, files, isFiles, isQuickParseNotice }) {
  const isUser = role === 'user';
  const containerRef = useRef(null);
  const t = useTranslation();

  const { processedHtml, charts, segments } = useMemo(() => {
    if (isUser || !content || !isMarkdown) return { processedHtml: null, charts: [], segments: null };
    const rawHtml = parseMarkdown(content);
    const { html: withPlaceholders, charts: extracted } = extractChartBlocks(rawHtml);
    const finalHtml = processMarkdownHtml(withPlaceholders);
    const seg = splitHtmlByCharts(finalHtml, extracted);
    return { processedHtml: finalHtml, charts: extracted, segments: seg };
  }, [content, isUser, isMarkdown]);

  useEffect(() => {
    if (!containerRef.current || !processedHtml) return;
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
  }, [processedHtml]);

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

  if (processedHtml) {
    // 有图表时使用拆分渲染：图表作为独立 React 节点，流式更新仅替换文字段，避免屏闪
    if (segments) {
      const { parts, charts: chartConfigs } = segments;
      return (
        <div
          ref={containerRef}
          className="chat__message chat__message--assistant chat__message--markdown"
        >
          {parts.map((html, i) => (
            <React.Fragment key={i}>
              {html ? (
                <div
                  className="chat__message-segment"
                  dangerouslySetInnerHTML={{ __html: html }}
                />
              ) : null}
              {i < chartConfigs.length && chartConfigs[i] && (
                <div className="echart-portal echart-portal--inline">
                  <Suspense fallback={<div className="echart-loading">加载图表中...</div>}>
                    {chartConfigs[i].type === 'table' ? (
                      <TableRendererLazy config={chartConfigs[i]} />
                    ) : (
                      <EChartsRenderer config={chartConfigs[i]} />
                    )}
                  </Suspense>
                </div>
              )}
            </React.Fragment>
          ))}
        </div>
      );
    }
    return (
      <>
        <div
          ref={containerRef}
          className="chat__message chat__message--assistant chat__message--markdown"
          dangerouslySetInnerHTML={{ __html: processedHtml }}
        />
        {charts.length > 0 && (
          <ChartPortals containerRef={containerRef} charts={charts} />
        )}
      </>
    );
  }

  return (
    <div className="chat__message chat__message--assistant">
      {content}
    </div>
  );
}
