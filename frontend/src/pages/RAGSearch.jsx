import React, { useState, useRef, useEffect } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { useTheme } from '../hooks/useTheme';
import { getStoredUser } from '../utils/auth';
import { useTranslation } from '../context/LocaleContext';
import { LanguageDropdown } from '../components/LanguageDropdown';
import { Chat } from '../components/Chat';
import { InputArea } from '../components/InputArea';
import { ProviderLogo } from '../components/ProviderLogo';
import logoImg from '../../img/Ling_Flowing_Logo.png';
import logoImgDark from '../../img/Image.png';

const KNOWLEDGE_SOURCES = [
  { id: 's1', label: 'Market Analysis Report', checked: true },
  { id: 's2', label: 'Internal Policy FAQ', checked: false },
  { id: 's3', label: 'Product Roadmap 2024', checked: true },
];

const RETRIEVED_DOCS = [
  { id: 'd1', name: 'Q4_Market_Trends.pdf', snippet: '"...the steady increase in cloud infrastructure adoption across the EMEA region has led to a 14% growth in related service revenue compared to the previous fiscal year..."', page: 'Page 24', relevancy: '98%', iconColor: 'blue' },
  { id: 'd2', name: 'Project_Zephyr_Specs.docx', snippet: '"Compliance guidelines for API versioning specify that all legacy endpoints must remain active for a minimum of 18 months following a major release..."', page: 'Page 12', relevancy: '92%', iconColor: 'emerald' },
  { id: 'd3', name: 'Internal_Security_FAQ.pdf', snippet: '"Data retention policies state that all customer-related metadata is anonymized after 30 days of inactivity and purged after 90 days..."', page: 'Page 5', relevancy: '85%', iconColor: 'amber' },
];

export function RAGSearch({ models, currentModel, defaultModelId, onModelChange, onLogout, onOpenProfile }) {
  const t = useTranslation();
  const user = getStoredUser();
  const displayName = user?.nickname || user?.username || user?.email || t('user');
  const planLabel = user?.plan ?? t('freePlan');
  const avatarUrl = user?.avatar_url;

  const { toggleTheme } = useTheme();
  const location = useLocation();
  const appsMenuRef = useRef(null);
  const modelMenuRef = useRef(null);
  const userMenuRef = useRef(null);
  const [sources, setSources] = useState(KNOWLEDGE_SOURCES);
  const [rightSidebarHidden, setRightSidebarHidden] = useState(false);
  const [appsMenuOpen, setAppsMenuOpen] = useState(false);
  const [userMenuOpen, setUserMenuOpen] = useState(false);
  const [showLogoutConfirm, setShowLogoutConfirm] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(() =>
    typeof window !== 'undefined' ? window.innerWidth >= 768 : true
  );
  const [messages, setMessages] = useState([]);

  const [modelMenuOpen, setModelMenuOpen] = useState(false);

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
    if (!userMenuOpen) return;
    const handleClickOutside = (e) => {
      if (userMenuRef.current && !userMenuRef.current.contains(e.target)) setUserMenuOpen(false);
    };
    document.addEventListener('mousedown', handleClickOutside);
    document.addEventListener('touchstart', handleClickOutside);
    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
      document.removeEventListener('touchstart', handleClickOutside);
    };
  }, [userMenuOpen]);

  useEffect(() => {
    setAppsMenuOpen(false);
    setModelMenuOpen(false);
  }, [location.pathname]);

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

  const toggleSource = (id) => {
    setSources((prev) =>
      prev.map((s) => (s.id === id ? { ...s, checked: !s.checked } : s))
    );
  };

  const handleToggleAllSources = (checked) => {
    setSources((prev) => prev.map((s) => ({ ...s, checked })));
  };

  const handleSend = (text) => {
    if (!text.trim()) return;
    setMessages((prev) => [...prev, { role: 'user', content: text.trim() }]);
    // TODO: 在此调用 RAG 检索接口并将 AI 回复追加到 messages
  };

  const iconColorMap = { blue: 'var(--color-primary)', emerald: '#34d399', amber: '#fbbf24' };
  const sidebarMenuLabel = sidebarOpen ? t('closeSidebar') : t('openSidebar');
  const hasChat = messages.length > 0;
  const allSourcesChecked =
    sources.length > 0 && sources.every((s) => s.checked);

  const handleSelectModel = (id) => {
    onModelChange?.(id, false);
    setModelMenuOpen(false);
  };

  const isDefaultModel = !!currentModel && currentModel.id === defaultModelId;

  return (
    <div className="rag-root">
      <aside
        className={`rag-sidebar${
          sidebarOpen ? ' rag-sidebar--open' : ' rag-sidebar--collapsed'
        }`}
      >
        <div className="rag-sidebar__top">
          <div className="sidebar__menu-row">
            <button
              type="button"
              className="sidebar__menu-btn"
              aria-label={sidebarMenuLabel}
              title={sidebarMenuLabel}
              onClick={() => setSidebarOpen((prev) => !prev)}
            >
              <span className="material-symbols-outlined">
                {sidebarOpen ? 'menu_open' : 'menu'}
              </span>
            </button>
            <Link to="/" className="sidebar__logo" aria-label={t('home')}>
              <img src={logoImg} alt="" className="sidebar__logo-img logo-img--light" />
              <img src={logoImgDark} alt="" className="sidebar__logo-img logo-img--dark" />
            </Link>
          </div>
          <button type="button" className="sidebar__new-chat">
            <span className="material-symbols-outlined">add</span>
            <span>{t('addKnowledgeSource')}</span>
          </button>
        </div>
        <div className="rag-sidebar__sources">
          <p className="rag-sidebar__sources-title">{t('knowledgeSourcesTitle')}</p>

          <label
            className="rag-source-item"
            style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', cursor: 'pointer' }}
          >
            <input
              type="checkbox"
              checked={allSourcesChecked}
              onChange={(e) => handleToggleAllSources(e.target.checked)}
              style={{ accentColor: 'var(--color-primary)' }}
            />
            <span className="material-symbols-outlined" style={{ fontSize: 20 }}>done_all</span>
            <span style={{ flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', fontSize: '0.875rem', fontWeight: allSourcesChecked ? 600 : 500 }}>
              {t('selectAllSources')}
            </span>
          </label>

          {sources.map((s) => (
            <label
              key={s.id}
              className={`rag-source-item${s.checked ? ' is-active' : ''}`}
              style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', cursor: 'pointer' }}
            >
              <input
                type="checkbox"
                checked={s.checked}
                onChange={() => toggleSource(s.id)}
                style={{ accentColor: 'var(--color-primary)' }}
              />
              <span className="material-symbols-outlined" style={{ fontSize: 20 }}>description</span>
              <span style={{ flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', fontSize: '0.875rem', fontWeight: s.checked ? 600 : 500 }}>{s.label}</span>
            </label>
          ))}
        </div>
        <div className="sidebar__bottom">
          <button type="button" className="sidebar__nav-btn">
            <span className="material-symbols-outlined">help</span>
            <span>{t('helpAndFaq')}</span>
          </button>
          <LanguageDropdown placement="above">
            <button type="button" className="sidebar__nav-btn" aria-label={t('language')}>
              <span className="material-symbols-outlined">language</span>
              <span>{t('language')}</span>
            </button>
          </LanguageDropdown>
          <button type="button" className="sidebar__nav-btn">
            <span className="material-symbols-outlined">settings</span>
            <span>{t('settings')}</span>
          </button>
          <div className="sidebar__user" ref={userMenuRef}>
            <button
              type="button"
              className="sidebar__user-trigger"
              aria-label={t('openUserMenu')}
              onClick={() => setUserMenuOpen((prev) => !prev)}
            >
              <div className="sidebar__avatar" aria-hidden="true">
                {avatarUrl ? (
                  <img src={avatarUrl} alt="" className="sidebar__avatar-img" />
                ) : null}
              </div>
              <div className="sidebar__user-info">
                <p className="sidebar__user-name">{displayName}</p>
                <p className="sidebar__user-plan">{planLabel}</p>
              </div>
            </button>
            {userMenuOpen && (
              <div className="sidebar__user-menu" role="menu">
                <button
                  type="button"
                  className="sidebar__user-menu-item"
                  role="menuitem"
                  onClick={() => {
                    setUserMenuOpen(false);
                    onOpenProfile?.();
                  }}
                >
                  <span className="material-symbols-outlined sidebar__user-menu-icon" aria-hidden="true">
                    person
                  </span>
                  <span>{t('profile')}</span>
                </button>
                <button type="button" className="sidebar__user-menu-item" role="menuitem">
                  <span className="material-symbols-outlined sidebar__user-menu-icon" aria-hidden="true">
                    credit_card
                  </span>
                  <span>{t('subscription')}</span>
                </button>
                <button
                  type="button"
                  className="sidebar__user-menu-item"
                  role="menuitem"
                  onClick={() => {
                    setUserMenuOpen(false);
                    setShowLogoutConfirm(true);
                  }}
                >
                  <span className="material-symbols-outlined sidebar__user-menu-icon" aria-hidden="true">
                    logout
                  </span>
                  <span>{t('logout')}</span>
                </button>
              </div>
            )}
          </div>
        </div>
      </aside>
      {showLogoutConfirm && (
        <div
          className="logout-confirm-overlay"
          role="dialog"
          aria-modal="true"
          aria-labelledby="logout-confirm-title"
        >
          <div className="logout-confirm-backdrop" onClick={() => setShowLogoutConfirm(false)} />
          <div className="logout-confirm-card">
            <h2 id="logout-confirm-title" className="logout-confirm-title">{t('confirmLogout')}</h2>
            <p className="logout-confirm-desc">{t('confirmLogoutDesc')}</p>
            <div className="logout-confirm-actions">
              <button
                type="button"
                className="logout-confirm-btn logout-confirm-btn--cancel"
                onClick={() => setShowLogoutConfirm(false)}
              >
                {t('cancel')}
              </button>
              <button
                type="button"
                className="logout-confirm-btn logout-confirm-btn--confirm"
                onClick={() => {
                  setShowLogoutConfirm(false);
                  onLogout?.();
                }}
              >
                {t('confirmLogoutBtn')}
              </button>
            </div>
          </div>
        </div>
      )}

      <main className="rag-main">
        <header className="rag-header">
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'flex-end', gap: '0.5rem' }}>
            <div className="header__model" ref={modelMenuRef}>
              <button
                type="button"
                className="header__model-btn"
                aria-haspopup="listbox"
                aria-expanded={modelMenuOpen}
                onClick={() => setModelMenuOpen((prev) => !prev)}
              >
                <ProviderLogo provider={currentModel?.provider} className="header__model-logo" />
                <span className="gradient-text">
                  {currentModel?.label ?? 'RAG Assistant v2'}
                </span>
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
                      <ProviderLogo provider={m.provider} className="header__model-menu-logo" />
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
                    <span>{t('setAsDefault')}</span>
                  </button>
                </div>
              )}
            </div>
          </div>
          <div className="rag-header__actions">
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

        {/* 中央欢迎区 + 聊天区，与主界面 Welcome 一致 */}
        <section className={`welcome${hasChat ? ' welcome--has-chat' : ''}`}>
          <div className="welcome__inner animate-fade-in">
            <div className="welcome__head">
              <h1 className="welcome__title">
                <span className="welcome__title-logo-wrap">
                  <img src={logoImg} alt="" className="welcome__title-logo logo-img--light" />
                  <img src={logoImgDark} alt="" className="welcome__title-logo logo-img--dark" />
                </span>
                <span className="welcome__greeting">{t('hello')}{displayName}</span>
              </h1>
              <p className="welcome__subtitle">{t('ragWelcomeSubtitle')}</p>
            </div>

            {!hasChat && (
              <InputArea
                onSend={handleSend}
                isStreaming={false}
                onCancelStream={() => {}}
                hasChat={false}
                showAttach={false}
                showMore={false}
              />
            )}

            <Chat messages={messages} streamingContent={null} isStreaming={false} />
          </div>
        </section>

        {/* 有对话后，输入框固定在底部，行为与主界面 InputArea 一致 */}
        {hasChat && (
          <InputArea
            onSend={handleSend}
            isStreaming={false}
            onCancelStream={() => {}}
            hasChat={true}
            showAttach={false}
            showMore={false}
          />
        )}
      </main>

      <aside className={`rag-right-sidebar${rightSidebarHidden ? ' rag-right-sidebar--collapsed' : ''}`}>
        <div className="rag-right-sidebar__head">
          <h3 className="rag-right-sidebar__title">
            <span className="material-symbols-outlined" style={{ fontSize: 20 }}>
              source
            </span>
            {t('searchDocuments')}
          </h3>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <span
              className="rag-right-sidebar__badge"
              style={{
                fontSize: 10,
                background: 'var(--hover-bg-strong)',
                border: '1px solid var(--color-card-border)',
                padding: '0.125rem 0.5rem',
                borderRadius: 9999,
                fontWeight: 700,
                color: 'var(--color-charcoal-light)',
              }}
            >
              {t('referencesCount')}
            </span>
            <button
              type="button"
              className="sidebar__menu-btn"
              title={rightSidebarHidden ? t('expandDocPanel') : t('collapseDocPanel')}
              aria-label={rightSidebarHidden ? t('expandDocPanel') : t('collapseDocPanel')}
              onClick={() => setRightSidebarHidden((v) => !v)}
            >
              <span className="material-symbols-outlined">dock_to_left</span>
            </button>
          </div>
        </div>
        <div className="rag-right-sidebar__body">
          {RETRIEVED_DOCS.map((d) => (
            <div key={d.id} className="rag-doc-card">
              <div className="rag-doc-card__title">
                <span className="material-symbols-outlined" style={{ color: iconColorMap[d.iconColor] || 'var(--color-primary)', fontSize: 18 }}>description</span>
                <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{d.name}</span>
              </div>
              <p className="rag-doc-card__snippet">{d.snippet}</p>
              <div className="rag-doc-card__meta">
                <span>{d.page} · {t('relevancy')}: {d.relevancy}</span>
                <span className="material-symbols-outlined" style={{ fontSize: 12 }}>open_in_new</span>
              </div>
            </div>
          ))}
        </div>
        <div className="rag-right-sidebar__footer" style={{ padding: '1rem', borderTop: '1px solid var(--color-card-border)', background: 'var(--color-sidebar-bg)' }}>
          <button
            type="button"
            className="rag-sidebar__nav-btn"
            style={{ width: '100%', padding: '0.5rem', border: '1px solid var(--color-card-border)', borderRadius: '0.5rem', fontSize: '0.75rem', fontWeight: 700 }}
          >
            {t('viewAllReferences')}
          </button>
        </div>
      </aside>
    </div>
  );
}
