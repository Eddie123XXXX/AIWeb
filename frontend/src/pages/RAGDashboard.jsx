import React, { useState, useRef, useEffect } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { useTheme } from '../hooks/useTheme';
import { useTranslation } from '../context/LocaleContext';
import { LanguageDropdown } from '../components/LanguageDropdown';
import { getStoredUser } from '../utils/auth';
import logoImg from '../../img/Ling_Flowing_Logo.png';
import logoImgDark from '../../img/Image.png';

const NOTEBOOKS = [
  { id: 'n1', title: 'Market Research 2024', sources: 12, updated: '2 days ago', icon: 'query_stats', iconBg: 'rgba(59, 130, 246, 0.15)', iconColor: '#60a5fa' },
  { id: 'n2', title: 'Project Zephyr', sources: 8, updated: '5 hours ago', icon: 'bolt', iconBg: 'rgba(168, 85, 247, 0.15)', iconColor: '#a78bfa' },
  { id: 'n3', title: 'Compliance Audit', sources: 24, updated: 'Oct 12, 2023', icon: 'shield_lock', iconBg: 'rgba(16, 185, 129, 0.15)', iconColor: '#34d399' },
  { id: 'n4', title: 'AI Learning Lab', sources: 42, updated: 'Sept 30, 2023', icon: 'school', iconBg: 'rgba(245, 158, 11, 0.15)', iconColor: '#fbbf24' },
];

export function RAGDashboard() {
  const t = useTranslation();
  const user = getStoredUser();
  const displayName = user?.nickname || user?.username || user?.email || t('user');

  const { toggleTheme } = useTheme();
  const location = useLocation();
  const appsMenuRef = useRef(null);
  const [appsMenuOpen, setAppsMenuOpen] = useState(false);

  useEffect(() => {
    if (!appsMenuOpen) return;
    const handleClickOutside = (e) => {
      if (appsMenuRef.current && !appsMenuRef.current.contains(e.target)) setAppsMenuOpen(false);
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

  return (
    <div className="rag-root">
      <main className="main">
        <header className="header">
          <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
            <Link to="/" className="rag-header__logo" aria-label={t('home')}>
              <img src={logoImg} alt="" className="rag-header__logo-img logo-img--light" />
              <img src={logoImgDark} alt="" className="rag-header__logo-img logo-img--dark" />
            </Link>
            <div className="rag-header__breadcrumb">
              <span>{t('knowledgeBase')}</span>
              <span style={{ color: 'var(--color-card-border)' }}>/</span>
              <span style={{ color: 'var(--color-charcoal)' }}>{t('myNotebooks')}</span>
            </div>
          </div>
          <div className="header__actions">
            <LanguageDropdown placement="below" menuClassName="header__apps-menu">
              <button
                type="button"
                className="header__icon-btn"
                title={t('language')}
                aria-label={t('language')}
              >
                <span className="material-symbols-outlined">language</span>
              </button>
            </LanguageDropdown>
            <button
              type="button"
              className="header__icon-btn"
              title={t('theme')}
              aria-label={t('theme')}
              onClick={toggleTheme}
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
                title={t('apps')}
                aria-label={t('apps')}
                aria-haspopup="menu"
                aria-expanded={appsMenuOpen}
                onClick={() => setAppsMenuOpen((v) => !v)}
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
                    <span>{t('aiChat')}</span>
                  </Link>
                  <Link
                    to="/wiki"
                    className={'header__model-menu-item' + (location.pathname === '/wiki' ? ' header__model-menu-item--active' : '')}
                    role="menuitem"
                    onClick={() => setAppsMenuOpen(false)}
                  >
                    <span className="material-symbols-outlined header__model-menu-emoji">dashboard</span>
                    <span>{t('knowledgeBase')}</span>
                  </Link>
                  <Link
                    to="/wiki/search"
                    className={'header__model-menu-item' + (location.pathname === '/wiki/search' ? ' header__model-menu-item--active' : '')}
                    role="menuitem"
                    onClick={() => setAppsMenuOpen(false)}
                  >
                    <span className="material-symbols-outlined header__model-menu-emoji">search</span>
                    <span>{t('ragSearch')}</span>
                  </Link>
                </div>
              )}
            </div>
          </div>
        </header>

        <div className="welcome" style={{ paddingTop: 0, justifyContent: 'flex-start' }}>
          <div className="welcome__inner animate-fade-in" style={{ maxWidth: '72rem' }}>
            <div className="welcome__head">
              <h1 className="welcome__title">
                <span className="welcome__title-logo-wrap">
                  <img src={logoImg} alt="" className="welcome__title-logo logo-img--light" />
                  <img src={logoImgDark} alt="" className="welcome__title-logo logo-img--dark" />
                </span>
                <span className="welcome__greeting">{t('welcomeBack')}{displayName}</span>
              </h1>
              <p className="welcome__subtitle">{t('dashboardSubtitle')}</p>
            </div>

            <div className="rag-notebook-grid">
              <Link to="/wiki/search" className="rag-notebook-card rag-notebook-card--new" style={{ textDecoration: 'none', color: 'inherit' }}>
                <div className="rag-notebook-card__icon-wrap">
                  <span className="material-symbols-outlined" style={{ fontSize: 24, color: 'var(--color-charcoal-light)' }}>add</span>
                </div>
                <span className="rag-notebook-card__title">{t('newNotebook')}</span>
                <span className="welcome__subtitle" style={{ fontSize: '0.875rem', marginTop: 0 }}>{t('startFromNewSource')}</span>
              </Link>
              {NOTEBOOKS.map((n) => (
                <div key={n.id} className="rag-notebook-card" role="button" tabIndex={0} onClick={() => {}} onKeyDown={(e) => e.key === 'Enter' && {}}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 'auto' }}>
                    <div
                      className="rag-notebook-card__icon-wrap"
                      style={{ background: n.iconBg, border: `1px solid ${n.iconColor}40` }}
                    >
                      <span className="material-symbols-outlined" style={{ color: n.iconColor, fontSize: 24 }}>{n.icon}</span>
                    </div>
                    <button type="button" className="header__icon-btn" style={{ padding: '0.25rem', width: '2rem', height: '2rem' }} aria-label={t('more')}>
                      <span className="material-symbols-outlined">more_vert</span>
                    </button>
                  </div>
                  <h3 className="rag-notebook-card__title">{n.title}</h3>
                  <div className="rag-notebook-card__meta">
                    <span style={{ display: 'flex', alignItems: 'center', gap: '0.375rem' }}>
                      <span className="material-symbols-outlined" style={{ fontSize: 14 }}>article</span>
                      {n.sources} 个知识源
                    </span>
                    <span style={{ display: 'flex', alignItems: 'center', gap: '0.375rem' }}>
                      <span className="material-symbols-outlined" style={{ fontSize: 14 }}>schedule</span>
                      {n.updated}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </main>
    </div>
  );
}
