import React, { useState, useRef, useEffect, useCallback } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { useTheme } from '../hooks/useTheme';
import { useTranslation } from '../context/LocaleContext';
import { LanguageDropdown } from '../components/LanguageDropdown';
import { getStoredUser } from '../utils/auth';
import { listNotebooks, createNotebook, updateNotebook, deleteNotebook } from '../utils/ragApi';
import logoImg from '../../img/Ling_Flowing_Logo.png';
import logoImgDark from '../../img/Image.png';

const ICON_PRESETS = [
  { icon: 'query_stats', iconBg: 'rgba(59, 130, 246, 0.15)', iconColor: '#60a5fa' },
  { icon: 'bolt', iconBg: 'rgba(168, 85, 247, 0.15)', iconColor: '#a78bfa' },
  { icon: 'shield_lock', iconBg: 'rgba(16, 185, 129, 0.15)', iconColor: '#34d399' },
  { icon: 'school', iconBg: 'rgba(245, 158, 11, 0.15)', iconColor: '#fbbf24' },
];

export function RAGDashboard() {
  const t = useTranslation();
  const user = getStoredUser();
  const displayName = user?.nickname || user?.username || user?.email || t('user');

  const { toggleTheme } = useTheme();
  const location = useLocation();
  const navigate = useNavigate();
  const appsMenuRef = useRef(null);
  const [notebooks, setNotebooks] = useState([]);
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [appsMenuOpen, setAppsMenuOpen] = useState(false);
  const [notebookMenuId, setNotebookMenuId] = useState(null);
  const [renameTarget, setRenameTarget] = useState(null);
  const [renameInput, setRenameInput] = useState('');
  const [deleteConfirmId, setDeleteConfirmId] = useState(null);
  const notebookMenuRef = useRef(null);

  const loadNotebooks = useCallback(async () => {
    setLoading(true);
    try {
      const list = await listNotebooks();
      setNotebooks(list);
    } catch {
      setNotebooks([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadNotebooks();
  }, [loadNotebooks]);

  const handleCreateNotebook = useCallback(async () => {
    if (creating) return;
    setCreating(true);
    try {
      const nb = await createNotebook({ title: '未命名笔记本' });
      navigate(`/wiki/search?notebook_id=${nb.id}`);
    } catch (err) {
      console.error('创建笔记本失败:', err);
      // 即使创建失败也跳转到 search 界面，使用默认笔记本（需确保后端 notebooks 表已创建）
      navigate('/wiki/search');
    } finally {
      setCreating(false);
    }
  }, [creating, navigate]);

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

  useEffect(() => {
    if (notebookMenuId == null) return;
    const handleClickOutside = (e) => {
      if (notebookMenuRef.current && !notebookMenuRef.current.contains(e.target)) setNotebookMenuId(null);
    };
    document.addEventListener('mousedown', handleClickOutside);
    document.addEventListener('touchstart', handleClickOutside);
    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
      document.removeEventListener('touchstart', handleClickOutside);
    };
  }, [notebookMenuId]);

  const handleRenameNotebook = useCallback(async () => {
    if (!renameTarget || !renameInput.trim()) {
      setRenameTarget(null);
      return;
    }
    try {
      await updateNotebook(renameTarget.id, { title: renameInput.trim() });
      await loadNotebooks();
      setRenameTarget(null);
    } catch (err) {
      console.error('重命名失败:', err);
      alert(err?.message || '重命名失败');
    }
  }, [renameTarget, renameInput, loadNotebooks]);

  const handleDeleteNotebook = useCallback(async () => {
    if (!deleteConfirmId) return;
    try {
      await deleteNotebook(deleteConfirmId);
      await loadNotebooks();
      setDeleteConfirmId(null);
      if (location.pathname === '/wiki' || new URLSearchParams(location.search).get('notebook_id') === deleteConfirmId) {
        navigate('/wiki');
      }
    } catch (err) {
      console.error('删除失败:', err);
      alert(err?.message || '删除失败');
    }
  }, [deleteConfirmId, loadNotebooks, location.pathname, location.search, navigate]);

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

        <div className="welcome welcome--dashboard">
          <div className="welcome__inner welcome__inner--dashboard animate-fade-in">
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
              <button
                type="button"
                className="rag-notebook-card rag-notebook-card--new"
                onClick={handleCreateNotebook}
                disabled={creating}
                style={{ textDecoration: 'none', color: 'inherit', cursor: creating ? 'wait' : 'pointer', font: 'inherit', textAlign: 'left' }}
              >
                <div className="rag-notebook-card__icon-wrap">
                  <span className="material-symbols-outlined" style={{ fontSize: 24, color: 'var(--color-charcoal-light)' }}>add</span>
                </div>
                <span className="rag-notebook-card__title">{creating ? (t('creating') || '创建中...') : t('newNotebook')}</span>
                <span className="welcome__subtitle" style={{ fontSize: '0.875rem', marginTop: 0 }}>{t('startFromNewSource')}</span>
              </button>
              {!loading && notebooks.map((n, idx) => {
                  const preset = ICON_PRESETS[idx % ICON_PRESETS.length];
                  return (
                    <div
                      key={n.id}
                      className="rag-notebook-card"
                      ref={notebookMenuId === n.id ? notebookMenuRef : null}
                      style={{ position: 'relative' }}
                    >
                      <div
                        style={{ flex: 1, cursor: 'pointer', display: 'flex', flexDirection: 'column', minHeight: 0 }}
                        onClick={() => navigate(`/wiki/search?notebook_id=${n.id}`)}
                        role="button"
                        tabIndex={0}
                        onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); navigate(`/wiki/search?notebook_id=${n.id}`); } }}
                        aria-label={n.title || t('newNotebook')}
                      >
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 'auto' }}>
                          <div
                            className="rag-notebook-card__icon-wrap"
                            style={{ background: preset.iconBg, border: `1px solid ${preset.iconColor}40` }}
                          >
                            <span className="material-symbols-outlined" style={{ color: preset.iconColor, fontSize: 24 }}>{preset.icon}</span>
                          </div>
                          <button
                            type="button"
                            className="rag-notebook-card__more header__icon-btn"
                            style={{ padding: '0.25rem', width: '2rem', height: '2rem' }}
                            aria-label={t('more')}
                            aria-haspopup="menu"
                            aria-expanded={notebookMenuId === n.id}
                            onClick={(e) => {
                              e.preventDefault();
                              e.stopPropagation();
                              setNotebookMenuId((prev) => (prev === n.id ? null : n.id));
                            }}
                          >
                            <span className="material-symbols-outlined">more_vert</span>
                          </button>
                        </div>
                        <h3 className="rag-notebook-card__title">{n.title || '未命名笔记本'}</h3>
                        <div className="rag-notebook-card__meta">
                          <span style={{ display: 'flex', alignItems: 'center', gap: '0.375rem' }}>
                            <span className="material-symbols-outlined" style={{ fontSize: 14 }}>article</span>
                            {n.source_count ?? 0} {t('sourcesCount') || '个知识源'}
                          </span>
                        </div>
                      </div>
                      {notebookMenuId === n.id && (
                        <div className="rag-notebook-card__menu" role="menu">
                          <button
                            type="button"
                            className="rag-notebook-card__menu-item"
                            role="menuitem"
                            onClick={(e) => {
                              e.preventDefault();
                              e.stopPropagation();
                              setRenameTarget({ id: n.id, title: n.title || '未命名笔记本' });
                              setRenameInput(n.title || '未命名笔记本');
                              setNotebookMenuId(null);
                            }}
                          >
                            <span className="material-symbols-outlined rag-notebook-card__menu-icon">edit</span>
                            <span>{t('renameNotebook')}</span>
                          </button>
                          <button
                            type="button"
                            className="rag-notebook-card__menu-item rag-notebook-card__menu-item--danger"
                            role="menuitem"
                            onClick={(e) => {
                              e.preventDefault();
                              e.stopPropagation();
                              setDeleteConfirmId(n.id);
                              setNotebookMenuId(null);
                            }}
                          >
                            <span className="material-symbols-outlined rag-notebook-card__menu-icon">delete</span>
                            <span>{t('deleteNotebook')}</span>
                          </button>
                        </div>
                      )}
                    </div>
                  );
                })}
            </div>
          </div>
        </div>
      </main>

      {renameTarget && (
        <div className="sidebar__rename-overlay" role="dialog" aria-modal="true" aria-labelledby="rag-rename-title">
          <div className="sidebar__rename-backdrop" onClick={() => setRenameTarget(null)} />
          <div className="sidebar__rename-card">
            <h2 id="rag-rename-title" className="sidebar__rename-title">{t('renameNotebook')}</h2>
            <p className="sidebar__rename-desc">{t('inputNewName')}</p>
            <input
              type="text"
              className="sidebar__rename-input"
              value={renameInput}
              onChange={(e) => setRenameInput(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter') handleRenameNotebook(); if (e.key === 'Escape') setRenameTarget(null); }}
              autoFocus
            />
            <div className="sidebar__rename-actions">
              <button type="button" className="sidebar__rename-btn sidebar__rename-btn--cancel" onClick={() => setRenameTarget(null)}>
                {t('cancel')}
              </button>
              <button type="button" className="sidebar__rename-btn sidebar__rename-btn--confirm" onClick={handleRenameNotebook}>
                {t('save')}
              </button>
            </div>
          </div>
        </div>
      )}

      {deleteConfirmId && (
        <div className="sidebar__rename-overlay" role="dialog" aria-modal="true" aria-labelledby="rag-delete-title">
          <div className="sidebar__rename-backdrop" onClick={() => setDeleteConfirmId(null)} />
          <div className="sidebar__rename-card">
            <h2 id="rag-delete-title" className="sidebar__rename-title">{t('deleteNotebook')}</h2>
            <p className="sidebar__rename-desc">{t('deleteNotebookConfirm')}</p>
            <div className="sidebar__rename-actions">
              <button type="button" className="sidebar__rename-btn sidebar__rename-btn--cancel" onClick={() => setDeleteConfirmId(null)}>
                {t('cancel')}
              </button>
              <button type="button" className="sidebar__rename-btn sidebar__rename-btn--danger" onClick={handleDeleteNotebook}>
                {t('delete')}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
