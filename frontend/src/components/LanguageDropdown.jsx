import React, { useState, useRef, useEffect } from 'react';
import { useLocale, useTranslation } from '../context/LocaleContext';

/**
 * 语言切换下拉菜单，样式与 header__model-menu / 应用菜单一致。
 * @param {React.ReactElement} children - 触发按钮（会注入 onClick、aria-haspopup、aria-expanded）
 * @param {'below'|'above'} [placement] - 下拉相对触发按钮的位置，默认 'below'
 * @param {string} [menuClassName] - 下拉菜单额外类名，如 header__apps-menu 用于右对齐
 */
export function LanguageDropdown({ children, placement = 'below', menuClassName = '' }) {
  const { locale, setLocale } = useLocale();
  const t = useTranslation();
  const [open, setOpen] = useState(false);
  const ref = useRef(null);

  useEffect(() => {
    if (!open) return;
    const handleClickOutside = (e) => {
      if (ref.current && !ref.current.contains(e.target)) setOpen(false);
    };
    document.addEventListener('mousedown', handleClickOutside);
    document.addEventListener('touchstart', handleClickOutside);
    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
      document.removeEventListener('touchstart', handleClickOutside);
    };
  }, [open]);

  const handleSelect = (value) => {
    setLocale(value);
    setOpen(false);
  };

  const menuStyle =
    placement === 'above'
      ? { bottom: '100%', marginBottom: '0.25rem', top: 'auto', marginTop: 0 }
      : { top: '100%', marginTop: '0.25rem' };

  return (
    <div className="header__model" ref={ref} style={{ position: 'relative' }}>
      {React.cloneElement(children, {
        onClick: () => setOpen((v) => !v),
        'aria-haspopup': 'menu',
        'aria-expanded': open,
      })}
      {open && (
        <div
          className={`header__model-menu header__apps-menu language-dropdown ${menuClassName}`.trim()}
          role="menu"
          aria-label={t('chooseLanguage')}
          style={menuStyle}
        >
          <button
            type="button"
            className={`header__model-menu-item language-dropdown__item${locale === 'zh' ? ' header__model-menu-item--active' : ''}`}
            role="menuitem"
            onClick={() => handleSelect('zh')}
          >
            {t('chinese')}
          </button>
          <button
            type="button"
            className={`header__model-menu-item language-dropdown__item${locale === 'en' ? ' header__model-menu-item--active' : ''}`}
            role="menuitem"
            onClick={() => handleSelect('en')}
          >
            {t('english')}
          </button>
        </div>
      )}
    </div>
  );
}
