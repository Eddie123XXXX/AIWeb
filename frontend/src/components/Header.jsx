import React, { useState, useRef, useEffect } from 'react';
import { Link, useLocation } from 'react-router-dom';

export function Header({
  onThemeToggle,
  onMobileMenuToggle,
  currentModel,
  models,
  onModelChange,
  defaultModelId,
}) {
  const [modelMenuOpen, setModelMenuOpen] = useState(false);
  const [appsMenuOpen, setAppsMenuOpen] = useState(false);
  const modelMenuRef = useRef(null);
  const appsMenuRef = useRef(null);
  const location = useLocation();

  const toggleModelMenu = () => {
    setModelMenuOpen((prev) => !prev);
    setAppsMenuOpen(false);
  };

  const toggleAppsMenu = () => {
    setAppsMenuOpen((prev) => !prev);
    setModelMenuOpen(false);
  };

  // 点击外部时收起模型下拉菜单
  useEffect(() => {
    if (!modelMenuOpen) return;

    const handleClickOutside = (event) => {
      if (modelMenuRef.current && !modelMenuRef.current.contains(event.target)) {
        setModelMenuOpen(false);
      }
    };

    document.addEventListener('mousedown', handleClickOutside);
    document.addEventListener('touchstart', handleClickOutside);

    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
      document.removeEventListener('touchstart', handleClickOutside);
    };
  }, [modelMenuOpen]);

  // 点击外部时收起应用下拉菜单；路由变化时也收起
  useEffect(() => {
    if (!appsMenuOpen) return;

    const handleClickOutside = (event) => {
      if (appsMenuRef.current && !appsMenuRef.current.contains(event.target)) {
        setAppsMenuOpen(false);
      }
    };

    document.addEventListener('mousedown', handleClickOutside);
    document.addEventListener('touchstart', handleClickOutside);

    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
      document.removeEventListener('touchstart', handleClickOutside);
    };
  }, [appsMenuOpen]);

  useEffect(() => {
    setAppsMenuOpen(false);
  }, [location.pathname]);

  const handleSelectModel = (id) => {
    onModelChange?.(id, false);
    setModelMenuOpen(false);
  };

  const isDefaultModel = !!currentModel && currentModel.id === defaultModelId;

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
      <div className="header__model" ref={modelMenuRef}>
        <button
          type="button"
          className="header__model-btn"
          aria-haspopup="listbox"
          aria-expanded={modelMenuOpen}
          onClick={toggleModelMenu}
        >
          <span className="gradient-text">{currentModel?.label ?? '模型'}</span>
          <span className="material-symbols-outlined" aria-hidden="true">
            {modelMenuOpen ? 'keyboard_arrow_up' : 'keyboard_arrow_down'}
          </span>
        </button>
        {modelMenuOpen && (
          <div className="header__model-menu" role="listbox">
            {models?.map((m) => (
              <button
                key={m.id}
                type="button"
                className={
                  'header__model-menu-item' +
                  (m.id === currentModel?.id ? ' header__model-menu-item--active' : '')
                }
                role="option"
                aria-selected={m.id === currentModel?.id}
                onClick={() => handleSelectModel(m.id)}
              >
                <span>{m.label}</span>
              </button>
            ))}
            <button
              type="button"
              className="header__model-menu-item header__model-menu-item--default"
              onClick={() => onModelChange?.(currentModel?.id, true)}
            >
              <span
                className={
                  'material-symbols-outlined header__model-menu-emoji' +
                  (isDefaultModel ? ' header__model-menu-emoji--filled' : '')
                }
                aria-hidden="true"
              >
                star
              </span>
              <span>设为默认</span>
            </button>
          </div>
        )}
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
        <div className="header__model" ref={appsMenuRef} style={{ position: 'relative' }}>
          <button
            type="button"
            className="header__icon-btn"
            title="应用"
            aria-label="应用"
            aria-haspopup="menu"
            aria-expanded={appsMenuOpen}
            onClick={toggleAppsMenu}
          >
            <span className="material-symbols-outlined">apps</span>
          </button>
          {appsMenuOpen && (
            <div className="header__model-menu header__apps-menu" role="menu">
              <Link
                to="/"
                className={'header__model-menu-item' + (location.pathname === '/' ? ' header__model-menu-item--active' : '')}
                role="menuitem"
                onClick={() => setAppsMenuOpen(false)}
              >
                <span className="material-symbols-outlined header__model-menu-emoji">chat</span>
                <span>AI 对话</span>
              </Link>
              <Link
                to="/wiki"
                className={'header__model-menu-item' + (location.pathname === '/wiki' ? ' header__model-menu-item--active' : '')}
                role="menuitem"
                onClick={() => setAppsMenuOpen(false)}
              >
                <span className="material-symbols-outlined header__model-menu-emoji">dashboard</span>
                <span>知识库</span>
              </Link>
              <Link
                to="/wiki/search"
                className={'header__model-menu-item' + (location.pathname === '/wiki/search' ? ' header__model-menu-item--active' : '')}
                role="menuitem"
                onClick={() => setAppsMenuOpen(false)}
              >
                <span className="material-symbols-outlined header__model-menu-emoji">search</span>
                <span>RAG 检索</span>
              </Link>
            </div>
          )}
        </div>
      </div>
    </header>
  );
}
