import React, { useState, useRef, useEffect, useCallback } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { useTheme } from '../hooks/useTheme';
import { useTranslation } from '../context/LocaleContext';
import { LanguageDropdown } from '../components/LanguageDropdown';
import { getStoredUser } from '../utils/auth';
import { listNotebooks, createNotebook, updateNotebook, deleteNotebook, getEmojiForTitle, saveNotebookEmoji } from '../utils/ragApi';
import logoImg from '../../img/Ling_Flowing_Logo.png';
import logoImgDark from '../../img/Image.png';

const MAX_TITLE_CHARS = 15;

/** 格式化为仅年月日 YYYY-MM-DD */
function formatDateOnly(createdAt) {
  if (!createdAt) return '';
  const d = typeof createdAt === 'string' ? new Date(createdAt) : createdAt;
  if (Number.isNaN(d.getTime())) return '';
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${y}-${m}-${day}`;
}

/** 根据来源指南摘要生成展示标题，最多 15 字 */
function summaryToTitle(summary) {
  if (!summary || typeof summary !== 'string') return '';
  const text = summary.replace(/\s+/g, ' ').trim();
  const len = [...text].length;
  if (len <= MAX_TITLE_CHARS) return text;
  return [...text].slice(0, MAX_TITLE_CHARS).join('') + '…';
}

const EMOJI_RULES = [
  [/报告|分析|数据|统计|调研|研究/, '📊'],
  [/技术|代码|开发|编程|AI|人工智能/, '💻'],
  [/财务|金额|预算|投资|收入|成本/, '💰'],
  [/法律|合同|条款|法规/, '⚖️'],
  [/教育|学习|课程|培训/, '📚'],
  [/医疗|健康|医学|临床/, '🏥'],
  [/产品|设计|需求|方案/, '📋'],
  [/市场|营销|销售|客户/, '📈'],
  [/会议|纪要|记录/, '📝'],
  [/人工智能|AI|机器学习|深度学习/, '🤖'],
];

/** 根据来源指南摘要匹配一个 emoji（用于未重命名时展示标题生成） */
function summaryToEmoji(summary) {
  if (!summary || typeof summary !== 'string') return null;
  const s = summary.toLowerCase();
  for (const [re, emoji] of EMOJI_RULES) {
    if (re.test(s)) return emoji;
  }
  return '📄';
}

/** 根据笔记本名称匹配一个 emoji，名字变化（含重命名）后重新生成 */
function titleToEmoji(title) {
  if (!title || typeof title !== 'string') return '📄';
  const s = title.trim().toLowerCase();
  if (!s) return '📄';
  for (const [re, emoji] of EMOJI_RULES) {
    if (re.test(s)) return emoji;
  }
  return '📄';
}

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
  const [notebookEmojis, setNotebookEmojis] = useState({});
  const notebookMenuRef = useRef(null);

  const getDisplayTitle = useCallback((n) => {
    const defaultTitle = '未命名笔记本';
    const hasSummary = n.first_doc_summary && (n.source_count ?? 0) > 0;
    const isUnrenamed = !n.title || n.title.trim() === '' || n.title === defaultTitle;
    return (isUnrenamed && hasSummary)
      ? (summaryToTitle(n.first_doc_summary) || n.title || defaultTitle)
      : (n.title || defaultTitle);
  }, []);

  useEffect(() => {
    if (!notebooks.length) {
      setNotebookEmojis({});
      return;
    }
    const needFetch = notebooks.filter((n) => !n.emoji || n.emoji.trim() === '');
    if (needFetch.length === 0) return;
    let cancelled = false;
    const pairs = needFetch.map((n) => ({ id: n.id, displayTitle: getDisplayTitle(n) }));
    Promise.all(
      pairs.map(({ id, displayTitle }) =>
        getEmojiForTitle(displayTitle)
          .then((emoji) =>
            saveNotebookEmoji(id, emoji)
              .then(() => ({ id, emoji }))
              .catch(() => ({ id, emoji }))
          )
          .catch(() => ({ id, emoji: titleToEmoji(displayTitle) }))
      )
    ).then((results) => {
      if (!cancelled) {
        setNotebookEmojis((prev) => ({
          ...prev,
          ...Object.fromEntries(results.map((r) => [r.id, r.emoji])),
        }));
      }
    });
    return () => { cancelled = true; };
  }, [notebooks, getDisplayTitle]);

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
                    to="/deep-research"
                    className={'header__model-menu-item' + (location.pathname === '/deep-research' ? ' header__model-menu-item--active' : '')}
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
              {!loading && notebooks.map((n) => {
                  const hasSummary = n.first_doc_summary && (n.source_count ?? 0) > 0;
                  const defaultTitle = '未命名笔记本';
                  const isUnrenamed = !n.title || n.title.trim() === '' || n.title === defaultTitle;
                  const displayTitle = (isUnrenamed && hasSummary)
                    ? (summaryToTitle(n.first_doc_summary) || n.title || defaultTitle)
                    : (n.title || defaultTitle);
                  const emoji = (n.emoji?.trim() || notebookEmojis[n.id]) ?? titleToEmoji(displayTitle);
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
                        aria-label={displayTitle}
                      >
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 'auto' }}>
                          <div className="rag-notebook-card__icon-wrap rag-notebook-card__icon-wrap--emoji">
                            <span className="rag-notebook-card__emoji" aria-hidden>{emoji}</span>
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
                        <h3 className="rag-notebook-card__title">{displayTitle}</h3>
                        <div className="rag-notebook-card__meta">
                          {n.created_at && (
                            <span className="rag-notebook-card__meta-date">
                              {formatDateOnly(n.created_at)}
                            </span>
                          )}
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
