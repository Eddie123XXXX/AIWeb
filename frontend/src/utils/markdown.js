import { marked } from 'marked';
import hljs from 'highlight.js/lib/common';
import katex from 'katex';
import 'katex/dist/katex.min.css';

const KEYWORDS = [
  'def', 'return', 'for', 'while', 'if', 'elif', 'else',
  'class', 'import', 'from', 'as', 'try', 'except', 'finally',
  'with', 'lambda', 'function', 'end', 'switch', 'case',
  'break', 'continue', 'global', 'persistent',
  'const', 'let', 'var', 'new', 'this', 'typeof',
  'true', 'false', 'null', 'undefined', 'export', 'default',
  'interface', 'type', 'extends', 'implements', 'enum',
  'public', 'private', 'protected', 'static', 'void', 'int', 'long', 'float', 'double', 'boolean', 'char', 'byte',
  'async', 'await', 'throw', 'yield', 'of', 'in', 'instanceof', 'delete'
];
const keywordPattern = new RegExp(
  '\\b(' + KEYWORDS.join('|') + ')\\b',
  'g'
);

function escapeHtml(str) {
  return str
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');
}

export function simpleHighlightCode(html) {
  if (!html) return '';
  let out = escapeHtml(html);
  out = out.replace(/"([^"\\]|\\.)*"/g, '<span class="code-token-string">$&</span>');
  out = out.replace(/'([^'\\]|\\.)*'/g, '<span class="code-token-string">$&</span>');
  out = out.replace(/\b\d+(\.\d+)?\b/g, '<span class="code-token-number">$&</span>');
  out = out.replace(keywordPattern, '<span class="code-token-keyword">$1</span>');
  out = out.replace(/^(\s*#.*)$/gm, '<span class="code-token-comment">$1</span>');
  out = out.replace(/^(\s*%.*)$/gm, '<span class="code-token-comment">$1</span>');
  return out;
}

/**
 * 去掉 LaTeX 数学定界符 $ / $$，只保留内部内容（不渲染），避免未解析的 $ 影响阅读。
 */
export function stripLatexDelimiters(text) {
  if (!text || typeof text !== 'string') return text;
  let out = text;
  out = out.replace(/\$\$([^$]*?)\$\$/g, '$1');
  out = out.replace(/\$([^$\n]+?)\$/g, '$1');
  out = out.replace(/\\%/g, '%');
  return out;
}

const KATEX_OPTS = { throwOnError: false };

function renderLatexToHtml(tex, displayMode) {
  try {
    return katex.renderToString(tex.trim(), { ...KATEX_OPTS, displayMode });
  } catch (_) {
    return escapeHtml(tex);
  }
}

/**
 * 将文本中的 $$...$$ 和 $...$ 用 KaTeX 渲染为 HTML，再对整段做 Markdown 解析。
 * 先替换数学为占位符，marked 后再把占位符换成 KaTeX 输出的 HTML。
 */
export function parseMarkdownWithLatex(text) {
  if (!text || typeof text !== 'string') return '';
  const blockPlaceholders = [];
  const inlinePlaceholders = [];
  let out = text;

  // 块级 $$ ... $$（支持内部换行）
  out = out.replace(/\$\$([\s\S]*?)\$\$/g, (_, content) => {
    const i = blockPlaceholders.length;
    blockPlaceholders.push(content);
    return `\n\n<!--KATEX_BLOCK_${i}-->\n\n`;
  });

  // 行内 $ ... $（不跨行）
  out = out.replace(/\$([^$\n]+?)\$/g, (_, content) => {
    const i = inlinePlaceholders.length;
    inlinePlaceholders.push(content);
    return `<!--KATEX_INLINE_${i}-->`;
  });

  try {
    const raw = typeof marked.parse === 'function' ? marked.parse(out) : marked(out);
    out = String(raw);
  } catch {
    return text;
  }

  blockPlaceholders.forEach((tex, i) => {
    out = out.replace(new RegExp(`<!--KATEX_BLOCK_${i}-->`, 'g'), renderLatexToHtml(tex, true));
  });
  inlinePlaceholders.forEach((tex, i) => {
    out = out.replace(new RegExp(`<!--KATEX_INLINE_${i}-->`, 'g'), renderLatexToHtml(tex, false));
  });

  return out;
}

export function parseMarkdown(text) {
  if (!text) return '';
  try {
    const raw = typeof marked.parse === 'function' ? marked.parse(text) : marked(text);
    return String(raw);
  } catch {
    return text;
  }
}

export function processMarkdownHtml(html) {
  if (!html) return html;
  const div = document.createElement('div');
  div.innerHTML = html;
  div.querySelectorAll('pre').forEach((pre) => {
    const codeEl = pre.querySelector('code');
    const raw = codeEl ? codeEl.textContent || '' : pre.textContent || '';
    let highlighted;
    try {
      if (hljs && typeof hljs.highlightAuto === 'function') {
        const result = hljs.highlightAuto(raw);
        highlighted = result && result.value ? result.value : simpleHighlightCode(raw);
      } else {
        highlighted = simpleHighlightCode(raw);
      }
    } catch (_) {
      highlighted = simpleHighlightCode(raw);
    }
    // 若 highlight.js 返回的是未加 class 的纯文本，再跑一遍我们的高亮
    if (highlighted === raw || !/<span class="(code-token|hljs-)/.test(highlighted)) {
      highlighted = simpleHighlightCode(raw);
    }
    const copyBtn =
      '<button type="button" class="code-copy-btn" aria-label="复制代码" title="复制代码"><span class="material-symbols-outlined code-copy-icon">content_copy</span></button>';
    pre.innerHTML = copyBtn + '<code>' + highlighted + '</code>';
  });
  return div.innerHTML;
}

export function copyToClipboard(text) {
  if (navigator.clipboard?.writeText) {
    return navigator.clipboard.writeText(text);
  }
  const ta = document.createElement('textarea');
  ta.value = text;
  ta.style.position = 'fixed';
  ta.style.opacity = '0';
  document.body.appendChild(ta);
  ta.select();
  try {
    document.execCommand('copy');
  } catch (_) {}
  document.body.removeChild(ta);
  return Promise.resolve();
}
