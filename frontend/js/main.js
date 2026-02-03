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

    function appendMessage(text, role) {
      const el = document.createElement('div');
      el.className = 'chat__message ' + (role === 'user' ? 'chat__message--user' : 'chat__message--assistant');
      el.textContent = text;
      chatContainer.appendChild(el);
      chatContainer.scrollTop = chatContainer.scrollHeight;
      return el;
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
      };

      ws.onmessage = function (event) {
        try {
          const data = JSON.parse(event.data);

          if (data.error) {
            pendingAssistantText = '';
            pendingAssistant = appendMessage('错误：' + data.error, 'assistant');
            sendBtn.disabled = false;
            return;
          }

          if (!pendingAssistant) {
            pendingAssistant = appendMessage('', 'assistant');
            pendingAssistantText = '';
          }

          if (typeof data.content === 'string') {
            pendingAssistantText += data.content;
            pendingAssistant.textContent = pendingAssistantText || '...';
          }

          if (data.done) {
            if (pendingAssistantText) {
              messages.push({
                role: 'assistant',
                content: pendingAssistantText
              });
            }
            pendingAssistant = null;
            pendingAssistantText = '';
            sendBtn.disabled = false;
          }
        } catch (e) {
          console.error(e);
          sendBtn.disabled = false;
        }
      };

      return wsReady;
    }

    function sendMessage() {
      const text = textarea.value.trim();
      if (!text) return;

      // 首次发送消息时，隐藏顶部欢迎文案，让对话占据中间区域
      if (welcomeSection && !welcomeSection.classList.contains('welcome--has-chat')) {
        welcomeSection.classList.add('welcome--has-chat');
      }

      appendMessage(text, 'user');
      messages.push({ role: 'user', content: text });

      textarea.value = '';
      sendBtn.disabled = true;

      ensureWebSocket()
        .then(function () {
          if (!ws || ws.readyState !== WebSocket.OPEN) {
            throw new Error('WebSocket 未连接');
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
          sendBtn.disabled = false;
        });
    }

    sendBtn.addEventListener('click', sendMessage);

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
