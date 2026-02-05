import { marked } from 'marked';
import hljs from 'highlight.js/lib/common';

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
