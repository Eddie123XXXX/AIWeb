/**
 * 个人页面 - 前端交互
 * - 亮/暗主题切换
 * - 移动端侧边栏开关
 * - 本地存储主题偏好
 */

(function () {
  'use strict';

  const THEME_KEY = 'app-theme';
  const THEME_LIGHT = 'light';
  const THEME_DARK = 'dark';

  function getStoredTheme() {
    try {
      return localStorage.getItem(THEME_KEY) || THEME_LIGHT;
    } catch {
      return THEME_LIGHT;
    }
  }

  function setStoredTheme(theme) {
    try {
      localStorage.setItem(THEME_KEY, theme);
    } catch (_) {}
  }

  function applyTheme(theme) {
    const root = document.documentElement;
    root.setAttribute('data-theme', theme);
    setStoredTheme(theme);
  }

  function toggleTheme() {
    const current = document.documentElement.getAttribute('data-theme') || THEME_LIGHT;
    const next = current === THEME_LIGHT ? THEME_DARK : THEME_LIGHT;
    applyTheme(next);
  }

  function initTheme() {
    const saved = getStoredTheme();
    applyTheme(saved);
  }

  function initSidebar() {
    const sidebar = document.getElementById('sidebar');
    const mobileBtn = document.getElementById('mobileMenuBtn');
    if (!sidebar || !mobileBtn) return;

    mobileBtn.addEventListener('click', function () {
      sidebar.classList.toggle('sidebar--open');
      const isOpen = sidebar.classList.contains('sidebar--open');
      mobileBtn.setAttribute('aria-label', isOpen ? '关闭菜单' : '打开菜单');
    });
  }

  function initChat() {
    const textarea = document.querySelector('.input-box__textarea');
    const sendBtn = document.querySelector('.input-box__send');
    const chatContainer = document.getElementById('chatMessages');
    const welcomeSection = document.querySelector('.welcome');

    if (!textarea || !sendBtn || !chatContainer) return;

    // 注意：需要先通过 /api/models 接口创建一个模型配置，ID 要和这里一致
    const DEFAULT_MODEL_ID = 'default';

    let ws = null;
    let wsReady = null;
    let messages = [];
    let pendingAssistant = null;
    let pendingAssistantText = '';
    let isStreaming = false;

    function appendMessage(text, role) {
      const el = document.createElement('div');
      el.className = 'chat__message ' + (role === 'user' ? 'chat__message--user' : 'chat__message--assistant');
      el.textContent = text;
      chatContainer.appendChild(el);
      chatContainer.scrollTop = chatContainer.scrollHeight;
      return el;
    }

    function updateSendButtonState() {
      if (!sendBtn) return;
      var icon = sendBtn.querySelector('.material-symbols-outlined');
      if (!icon) return;

      if (isStreaming) {
        icon.textContent = 'pause';
        sendBtn.setAttribute('aria-label', '暂停生成');
        sendBtn.title = '暂停生成';
      } else {
        icon.textContent = 'send';
        sendBtn.setAttribute('aria-label', '发送');
        sendBtn.title = '发送';
      }
    }

    function cancelStream() {
      if (!isStreaming) return;

      // 把当前已经生成的部分当作「完成的回答」写入对话历史，避免下一次请求继续补完它
      if (pendingAssistant && pendingAssistantText) {
        messages.push({
          role: 'assistant',
          content: pendingAssistantText
        });
        pendingAssistant = null;
        pendingAssistantText = '';
      }

      isStreaming = false;
      updateSendButtonState();

      try {
        if (ws && ws.readyState === WebSocket.OPEN) {
          ws.close();
        }
      } catch (_) {}
    }

    function simpleHighlightCode(codeEl) {
      if (!codeEl) return;

      var raw = codeEl.textContent;
      if (!raw) return;

      // 先做 HTML 转义，避免后续插入 span 时被当作标签解析
      var html = raw
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;');

      // 1) 字符串："..." 和 '...'（尽量覆盖转义场景）
      html = html.replace(/"([^"\\]|\\.)*"/g, '<span class="code-token-string">$&<\/span>');
      html = html.replace(/'([^'\\]|\\.)*'/g, '<span class="code-token-string">$&<\/span>');

      // 2) 数字
      html = html.replace(/\b\d+(\.\d+)?\b/g, '<span class="code-token-number">$&<\/span>');

      // 3) 关键字（简单支持 Python + MATLAB 常见关键字）
      var keywordPattern = '\\b(' + [
        'def', 'return', 'for', 'while', 'if', 'elif', 'else',
        'class', 'import', 'from', 'as', 'try', 'except', 'finally',
        'with', 'lambda', 'function', 'end', 'switch', 'case',
        'break', 'continue', 'global', 'persistent'
      ].join('|') + ')\\b';
      var keywordRegex = new RegExp(keywordPattern, 'g');
      html = html.replace(keywordRegex, '<span class="code-token-keyword">$1<\/span>');

      // 4) 注释（最后处理，整行盖住前面所有颜色）Python #、MATLAB %
      html = html.replace(/^(\s*#.*)$/gm, '<span class="code-token-comment">$1<\/span>');
      html = html.replace(/^(\s*%.*)$/gm, '<span class="code-token-comment">$1<\/span>');

      codeEl.innerHTML = html;
    }

    function renderAssistantMarkdown(el, text) {
      if (!el) return;

      // 如果没有引入 marked，则退回到纯文本
      if (typeof window.marked === 'undefined') {
        el.textContent = text;
        return;
      }

      try {
        // 兼容不同版本的 marked：有的用 marked.parse，有的直接调用 marked()
        var html;
        if (typeof window.marked.parse === 'function') {
          html = window.marked.parse(text);
        } else if (typeof window.marked === 'function') {
          html = window.marked(text);
        } else {
          el.textContent = text;
          return;
        }

        el.innerHTML = html;
        el.classList.add('chat__message--markdown');

        // 代码高亮：先交给 highlight.js（如果有），再做一层简单自定义高亮（确保至少有字符串/关键字等颜色）
        el.querySelectorAll('pre code').forEach(function (block) {
          if (typeof window.hljs !== 'undefined' && window.hljs.highlightElement) {
            try {
              window.hljs.highlightElement(block);
            } catch (_) {}
          }
          simpleHighlightCode(block);
        });

        // 为每个代码块添加复制按钮
        el.querySelectorAll('pre').forEach(function (preEl) {
          if (preEl.querySelector('.code-copy-btn')) return;

          var btn = document.createElement('button');
          btn.type = 'button';
          btn.className = 'code-copy-btn';
          btn.setAttribute('aria-label', '复制代码');
          btn.title = '复制代码';
          btn.innerHTML = '<span class="material-symbols-outlined code-copy-icon">content_copy</span>';

          btn.addEventListener('click', function () {
            var codeEl = preEl.querySelector('code');
            var textToCopy = codeEl ? codeEl.innerText : preEl.innerText;

            if (navigator.clipboard && navigator.clipboard.writeText) {
              navigator.clipboard.writeText(textToCopy).catch(function () {});
            } else {
              var ta = document.createElement('textarea');
              ta.value = textToCopy;
              ta.style.position = 'fixed';
              ta.style.opacity = '0';
              document.body.appendChild(ta);
              ta.select();
              try {
                document.execCommand('copy');
              } catch (_) {}
              document.body.removeChild(ta);
            }
          });

          preEl.insertBefore(btn, preEl.firstChild);
        });
      } catch (e) {
        console.error(e);
        el.textContent = text;
      }
    }

    function ensureWebSocket() {
      if (ws && ws.readyState === WebSocket.OPEN) {
        return Promise.resolve();
      }

      if (wsReady) {
        return wsReady;
      }

      const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
      const host = window.location.host || 'localhost:8000';
      const url = protocol + '//' + host + '/api/chat/ws';

      ws = new WebSocket(url);

      wsReady = new Promise(function (resolve, reject) {
        ws.onopen = function () {
          resolve();
        };
        ws.onerror = function (event) {
          reject(new Error('WebSocket 连接失败'));
        };
      });

      ws.onclose = function () {
        wsReady = null;
        ws = null;
        if (isStreaming) {
          isStreaming = false;
          updateSendButtonState();
        }
      };

      ws.onmessage = function (event) {
        try {
          const data = JSON.parse(event.data);

          if (data.error) {
            pendingAssistantText = '';
            pendingAssistant = appendMessage('错误：' + data.error, 'assistant');
            isStreaming = false;
            updateSendButtonState();
            sendBtn.disabled = false;
            return;
          }

          if (!pendingAssistant) {
            pendingAssistant = appendMessage('', 'assistant');
            pendingAssistantText = '';
          }

          if (typeof data.content === 'string') {
            pendingAssistantText += data.content;
            // 实时按 Markdown + 代码块渲染
            renderAssistantMarkdown(pendingAssistant, pendingAssistantText || '...');
          }

          if (data.done) {
            if (pendingAssistantText) {
              messages.push({
                role: 'assistant',
                content: pendingAssistantText
              });

              // 完整接收后再做一次 Markdown 渲染，支持代码块/列表等样式
              renderAssistantMarkdown(pendingAssistant, pendingAssistantText);
            }
            pendingAssistant = null;
            pendingAssistantText = '';
            isStreaming = false;
            updateSendButtonState();
            sendBtn.disabled = false;
          }
        } catch (e) {
          console.error(e);
          isStreaming = false;
          updateSendButtonState();
          sendBtn.disabled = false;
        }
      };

      return wsReady;
    }

    function sendMessage() {
      // 正在流式生成时，不再触发新的发送
      if (isStreaming) return;

      const text = textarea.value.trim();
      if (!text) return;

      // 首次发送消息时，隐藏顶部欢迎文案，让对话占据中间区域
      if (welcomeSection && !welcomeSection.classList.contains('welcome--has-chat')) {
        welcomeSection.classList.add('welcome--has-chat');
      }

      appendMessage(text, 'user');
      messages.push({ role: 'user', content: text });

      textarea.value = '';

      // 进入流式生成状态
      isStreaming = true;
      updateSendButtonState();

      ensureWebSocket()
        .then(function () {
          if (!ws || ws.readyState !== WebSocket.OPEN) {
            throw new Error('WebSocket 未连接');
          }

          // 如果在连接建立前用户已经点击了暂停，则不再发送本次请求
          if (!isStreaming) {
            return;
          }

          const payload = {
            model_id: DEFAULT_MODEL_ID,
            messages: messages,
            stream: true,
            temperature: 0.7,
            max_tokens: 1024
          };

          ws.send(JSON.stringify(payload));
        })
        .catch(function (err) {
          console.error(err);
          appendMessage('错误：' + err.message, 'assistant');
          isStreaming = false;
          updateSendButtonState();
          sendBtn.disabled = false;
        });
    }

    sendBtn.addEventListener('click', function () {
      if (isStreaming) {
        cancelStream();
      } else {
        sendMessage();
      }
    });

    textarea.addEventListener('keydown', function (event) {
      if (event.key === 'Enter' && !event.shiftKey) {
        event.preventDefault();
        sendMessage();
      }
    });
  }

  function init() {
    initTheme();

    var themeBtn = document.getElementById('themeToggle');
    if (themeBtn) {
      themeBtn.addEventListener('click', toggleTheme);
    }

    initSidebar();
    initChat();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
