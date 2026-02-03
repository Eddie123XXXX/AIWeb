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

  function init() {
    initTheme();

    var themeBtn = document.getElementById('themeToggle');
    if (themeBtn) {
      themeBtn.addEventListener('click', toggleTheme);
    }

    initSidebar();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
