import React, { useState, useRef, useEffect } from 'react';

export function Header({
  onThemeToggle,
  onMobileMenuToggle,
  currentModel,
  models,
  onModelChange,
  defaultModelId,
}) {
  const [modelMenuOpen, setModelMenuOpen] = useState(false);
  const modelMenuRef = useRef(null);

  const toggleModelMenu = () => {
    setModelMenuOpen((prev) => !prev);
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
        <button type="button" className="header__icon-btn" title="应用" aria-label="应用">
          <span className="material-symbols-outlined">apps</span>
        </button>
      </div>
    </header>
  );
}
