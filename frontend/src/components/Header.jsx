import React from 'react';

export function Header({ onThemeToggle, onMobileMenuToggle }) {
  return (
    <header className="header">
      <div className="header__mobile-menu">
        <button
          type="button"
          className="header__mobile-menu-btn"
          aria-label="打开菜单"
          onClick={onMobileMenuToggle}
        >
          <span className="material-symbols-outlined">menu</span>
        </button>
      </div>
      <div className="header__model">
        <button type="button" className="header__model-btn">
          <span className="gradient-text">Gemini Advanced</span>
          <span className="material-symbols-outlined" aria-hidden="true">
            keyboard_arrow_down
          </span>
        </button>
      </div>
      <div className="header__actions">
        <button
          type="button"
          className="header__icon-btn"
          title="切换主题"
          aria-label="切换主题"
          onClick={onThemeToggle}
        >
          <span className="material-symbols-outlined theme-icon-light">light_mode</span>
          <span className="material-symbols-outlined theme-icon-dark" aria-hidden="true">
            dark_mode
          </span>
        </button>
        <button type="button" className="header__icon-btn" title="应用" aria-label="应用">
          <span className="material-symbols-outlined">apps</span>
        </button>
        <button type="button" className="header__logout">
          退出登录
        </button>
      </div>
    </header>
  );
}
