import React, { useState, useRef, useEffect, useCallback } from 'react';
import { Link, useLocation, useSearchParams } from 'react-router-dom';
import { useTheme } from '../hooks/useTheme';
import { getStoredUser } from '../utils/auth';
import { useTranslation } from '../context/LocaleContext';
import { LanguageDropdown } from '../components/LanguageDropdown';
import { Chat } from '../components/Chat';
import { InputArea } from '../components/InputArea';
import { ProviderLogo } from '../components/ProviderLogo';
import { useChat } from '../hooks/useChat';
import { ragSearch, listRAGDocuments, buildRAGContextFromHits, uploadRAGDocument, processRAGDocument, deleteRAGDocument, getDocumentMarkdown, DEFAULT_NOTEBOOK_ID } from '../utils/ragApi';
import { parseMarkdownWithLatex, processMarkdownHtml } from '../utils/markdown';
import logoImg from '../../img/Ling_Flowing_Logo.png';
import logoImgDark from '../../img/Image.png';

const ICON_COLORS = ['blue', 'emerald', 'amber'];

/** 将单独一行的图片 URL 转为 Markdown 图片语法，便于卡片内渲染为小图 */
function ensureImageUrlsInContent(text) {
  if (!text || typeof text !== 'string') return text;
  const imageUrlLine = /^(https?:\/\/[^\s]+\.(png|jpg|jpeg|gif|webp|bmp)(?:\?[^\s]*)?)$/im;
  return text
    .split('\n')
    .map((line) => {
      const trimmed = line.trim();
      return imageUrlLine.test(trimmed) ? `![image](${trimmed})` : line;
    })
    .join('\n');
}

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
  const [searchParams] = useSearchParams();
  const notebookId = searchParams.get('notebook_id') || DEFAULT_NOTEBOOK_ID;
  const [sources, setSources] = useState([]);
  const [sourcesLoading, setSourcesLoading] = useState(true);
  const [rightSidebarHidden, setRightSidebarHidden] = useState(false);
  const [retrievedDocs, setRetrievedDocs] = useState([]);
  const [appsMenuOpen, setAppsMenuOpen] = useState(false);
  const [userMenuOpen, setUserMenuOpen] = useState(false);
  const [showLogoutConfirm, setShowLogoutConfirm] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(() =>
    typeof window !== 'undefined' ? window.innerWidth >= 768 : true
  );
  const [modelMenuOpen, setModelMenuOpen] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [sourceMenuId, setSourceMenuId] = useState(null);
  const [hasSearchedForRefs, setHasSearchedForRefs] = useState(false);
  const [expandDoc, setExpandDoc] = useState({ docId: null, filename: '', segments: [], summary: '', loading: false, chunkId: null, chunkSnippet: null });
  const fileInputRef = useRef(null);
  const sourceMenuRef = useRef(null);
  const expandDocContentRef = useRef(null);
  const expandDocBodyRef = useRef(null);

  const { messages, streamingContent, isStreaming, sendMessage, cancelStream } = useChat(null);

  const loadSources = useCallback(async () => {
    setSourcesLoading(true);
    try {
      const docs = await listRAGDocuments(notebookId);
      setSources(docs.map((d) => ({ id: d.id, label: d.filename, checked: true, status: d.status })));
    } catch {
      setSources([]);
    } finally {
      setSourcesLoading(false);
    }
  }, [notebookId]);

  useEffect(() => {
    loadSources();
  }, [loadSources]);

  const handleAddSource = useCallback(() => {
    fileInputRef.current?.click();
  }, []);

  const handleFileSelect = useCallback(
    async (e) => {
      const file = e.target?.files?.[0];
      e.target.value = '';
      if (!file || uploading) return;
      setUploading(true);
      try {
        const doc = await uploadRAGDocument({ file, notebook_id: notebookId });
        await processRAGDocument(doc.id);
        await loadSources();
      } catch (err) {
        console.error('上传失败:', err);
        alert(err?.message || '上传失败');
      } finally {
        setUploading(false);
      }
    },
    [notebookId, uploading, loadSources]
  );

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

  useEffect(() => {
    if (sourceMenuId == null) return;
    const handleClickOutside = (e) => {
      if (sourceMenuRef.current && !sourceMenuRef.current.contains(e.target)) setSourceMenuId(null);
    };
    document.addEventListener('mousedown', handleClickOutside);
    document.addEventListener('touchstart', handleClickOutside);
    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
      document.removeEventListener('touchstart', handleClickOutside);
    };
  }, [sourceMenuId]);

  const handleDeleteSource = useCallback(
    async (docId) => {
      setSourceMenuId(null);
      try {
        await deleteRAGDocument(docId);
        await loadSources();
      } catch (err) {
        console.error('删除失败:', err);
        alert(err?.message || '删除失败');
      }
    },
    [loadSources]
  );

  useEffect(() => {
    if (!expandDoc.docId || !expandDoc.loading) return;
    let cancelled = false;
    getDocumentMarkdown(expandDoc.docId)
      .then((data) => {
        if (!cancelled) setExpandDoc((prev) => ({ ...prev, segments: data.segments || [], summary: data.summary || '', loading: false }));
      })
      .catch((err) => {
        if (!cancelled) {
          console.error('获取文档失败:', err);
          setExpandDoc((prev) => ({ ...prev, segments: [], summary: '', loading: false }));
          alert(err?.message || '获取文档失败');
        }
      });
    return () => { cancelled = true; };
  }, [expandDoc.docId, expandDoc.loading]);

  // 定位并高亮检索到的 chunk（从右侧卡片点「展开文件」时，等 DOM 渲染后再滚动）
  useEffect(() => {
    if (!expandDoc.segments?.length || expandDoc.loading) return;
    const chunkId = expandDoc.chunkId;
    const chunkSnippet = expandDoc.chunkSnippet;
    const segments = expandDoc.segments;

    // 调试：在控制台查看首条 segment 的字段，确认是否有 chunk_id（F12 打开控制台）
    if (segments.length > 0) {
      const first = segments[0];
      console.log('[RAG 展开] segments 首条字段:', Object.keys(first), 'chunk_id' in first ? '有 chunk_id' : '无 chunk_id', '当前要定位的 chunkId:', chunkId);
    }

    const scrollToChunk = () => {
      const container = expandDocContentRef.current;
      const scrollParent = expandDocBodyRef.current;
      if (!scrollParent) {
        if (chunkId && process.env.NODE_ENV === 'development') console.log('[RAG 展开] scrollParent 为空');
        return;
      }
      if (!container) {
        if (chunkId && process.env.NODE_ENV === 'development') console.log('[RAG 展开] container 为空');
        return;
      }

      let el = null;
      if (chunkId) {
        el = container.querySelector(`[data-chunk-id="${chunkId}"]`);
      }
      if (!el && chunkSnippet) {
        const idx = segments.findIndex((seg) => {
          const raw = (seg.content || '').replace(/\s+/g, ' ').trim();
          const snippet = chunkSnippet.replace(/\s+/g, ' ').trim().slice(0, 80);
          return raw.includes(snippet) || snippet.length > 20 && raw.slice(0, 120).includes(snippet.slice(0, 40));
        });
        if (idx !== -1) el = container.querySelector(`[data-segment-index="${idx}"]`);
        if (process.env.NODE_ENV === 'development') console.log('[RAG 展开] 按内容匹配 segment 下标:', idx, el ? '找到' : '未找到');
      }
      if (!el) {
        if (chunkId && process.env.NODE_ENV === 'development') console.log('[RAG 展开] 未找到目标段落 element');
        return;
      }
      el.classList.add('rag-expand-doc-segment--highlight');

      const padding = 24;
      const elRect = el.getBoundingClientRect();
      const parentRect = scrollParent.getBoundingClientRect();
      const relativeTop = elRect.top - parentRect.top + scrollParent.scrollTop;
      const targetScroll = Math.max(0, relativeTop - padding);
      scrollParent.scrollTo({ top: targetScroll, behavior: 'smooth' });
    };

    const id = setTimeout(scrollToChunk, 200);
    return () => clearTimeout(id);
  }, [expandDoc.chunkId, expandDoc.chunkSnippet, expandDoc.segments, expandDoc.loading]);

  const handleToggleAllSources = (checked) => {
    setSources((prev) => prev.map((s) => ({ ...s, checked })));
  };

  const handleSend = useCallback(
    async (text) => {
      const trimmed = text?.trim();
      if (!trimmed || isStreaming) return;
      const selectedDocIds = sources.filter((s) => s.checked).map((s) => s.id);
      let ragContext = '未检索到相关知识库内容。';
      try {
        const searchResult = await ragSearch({
          notebook_id: notebookId,
          query: trimmed,
          document_ids: selectedDocIds,
        });
        ragContext = buildRAGContextFromHits(searchResult);
        const hits = searchResult?.hits || [];
        const docIdToName = Object.fromEntries(sources.map((s) => [s.id, s.label]));
        setRetrievedDocs(
          hits.map((h, i) => ({
            id: h.chunk_id || `h${i}`,
            document_id: h.document_id,
            name: docIdToName[h.document_id] || h.document_id,
            content: h.content || '',
            snippet: (h.content || '').slice(0, 280) + (h.content?.length > 280 ? '...' : ''),
            relevancy: h.rerank_score != null ? `${Math.round(h.rerank_score * 100)}%` : `${Math.round((h.score || 0) * 100)}%`,
            iconColor: ICON_COLORS[i % ICON_COLORS.length],
          }))
        );
      } catch (err) {
        console.error('RAG 检索失败:', err);
        setRetrievedDocs([]);
      }
      setHasSearchedForRefs(true);
      sendMessage(trimmed, currentModel?.id || 'default', null, null, ragContext);
    },
    [notebookId, sources, isStreaming, currentModel?.id, sendMessage]
  );

  const iconColorMap = { blue: 'var(--color-primary)', emerald: '#34d399', amber: '#fbbf24' };
  const sidebarMenuLabel = sidebarOpen ? t('closeSidebar') : t('openSidebar');
  const hasChat = messages.length > 0 || !!streamingContent;
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
            <Link to="/wiki" className="sidebar__logo" aria-label={t('myNotebooks')}>
              <img src={logoImg} alt="" className="sidebar__logo-img logo-img--light" />
              <img src={logoImgDark} alt="" className="sidebar__logo-img logo-img--dark" />
            </Link>
          </div>
          <input
            ref={fileInputRef}
            type="file"
            accept=".pdf,.docx,.xlsx,.xls,.csv,.txt,.md"
            style={{ display: 'none' }}
            onChange={handleFileSelect}
          />
          <button
            type="button"
            className={`sidebar__new-chat${uploading ? ' sidebar__new-chat--uploading' : ''}`}
            onClick={handleAddSource}
            disabled={uploading}
          >
            {uploading ? (
              <span className="material-symbols-outlined sidebar__new-chat__spinner" aria-hidden>progress_activity</span>
            ) : (
              <span className="material-symbols-outlined">add</span>
            )}
            <span>{uploading ? t('uploading') : t('addKnowledgeSource')}</span>
          </button>
        </div>
        <div className="rag-sidebar__sources">
          <p className="rag-sidebar__sources-title">{t('knowledgeSourcesTitle')}</p>

          {sources.length > 0 && (
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
          )}

          {sourcesLoading ? (
            <p style={{ fontSize: '0.875rem', color: 'var(--color-charcoal-light)', padding: '0.5rem 0' }}>{t('loading') || '加载中...'}</p>
          ) : null}

          {sources.map((s) => (
            <div
              key={s.id}
              className={`rag-source-item-row${s.checked ? ' is-active' : ''}`}
              ref={sourceMenuId === s.id ? sourceMenuRef : null}
            >
              <label className="rag-source-item">
                <input
                  type="checkbox"
                  checked={s.checked}
                  onChange={() => toggleSource(s.id)}
                  style={{ accentColor: 'var(--color-primary)' }}
                />
                <span className="material-symbols-outlined rag-source-item__icon">description</span>
                <span className="rag-source-item__label" style={{ fontWeight: s.checked ? 600 : 500 }} title={s.label}>{s.label}</span>
              </label>
              <button
                type="button"
                className="rag-source-item__more"
                aria-label={t('more')}
                title={t('more')}
                onClick={(e) => {
                  e.preventDefault();
                  e.stopPropagation();
                  setSourceMenuId((prev) => (prev === s.id ? null : s.id));
                }}
              >
                <span className="material-symbols-outlined">more_vert</span>
              </button>
              {sourceMenuId === s.id && (
                <div className="rag-source-menu" role="menu">
                  <button
                    type="button"
                    className="rag-source-menu-item"
                    role="menuitem"
                    onClick={() => {
                      setSourceMenuId(null);
                      setRightSidebarHidden(false);
                      setExpandDoc({ docId: s.id, filename: s.label, segments: [], summary: '', loading: true, chunkId: null, chunkSnippet: null });
                    }}
                  >
                    <span className="material-symbols-outlined rag-source-menu-icon">open_in_new</span>
                    <span>{t('expandFile')}</span>
                  </button>
                  <button
                    type="button"
                    className="rag-source-menu-item rag-source-menu-item--danger"
                    role="menuitem"
                    onClick={() => handleDeleteSource(s.id)}
                  >
                    <span className="material-symbols-outlined rag-source-menu-icon">delete</span>
                    <span>{t('deleteThisSource')}</span>
                  </button>
                </div>
              )}
            </div>
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
                isStreaming={isStreaming}
                onCancelStream={cancelStream}
                hasChat={false}
                showAttach={false}
                showMore={false}
              />
            )}

            <Chat messages={messages} streamingContent={streamingContent} isStreaming={isStreaming} />
          </div>
        </section>

        {/* 有对话后，输入框固定在底部，行为与主界面 InputArea 一致 */}
        {hasChat && (
          <InputArea
            onSend={handleSend}
            isStreaming={isStreaming}
            onCancelStream={cancelStream}
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
              {retrievedDocs.length}
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
          {retrievedDocs.length === 0 && !hasSearchedForRefs ? null : retrievedDocs.length === 0 ? (
            <p style={{ fontSize: '0.875rem', color: 'var(--color-charcoal-light)', padding: '1rem' }}>
              {t('noReferencesYet') || '发送问题后，检索到的文档将显示在此'}
            </p>
          ) : (
            retrievedDocs.map((d) => (
              <div key={d.id} className="rag-doc-card">
                <div className="rag-doc-card__from">
                  <span className="material-symbols-outlined" style={{ color: iconColorMap[d.iconColor] || 'var(--color-primary)', fontSize: 16 }}>description</span>
                  <span className="rag-doc-card__doc-name" title={d.name}>{d.name}</span>
                </div>
                <div
                  className="rag-doc-card__content"
                  dangerouslySetInnerHTML={{
                    __html: processMarkdownHtml(parseMarkdownWithLatex(ensureImageUrlsInContent(d.content || ''))),
                  }}
                />
                <div className="rag-doc-card__meta">
                  <span>{t('relevancy')}: {d.relevancy}</span>
                  {d.document_id && (
                    <button
                      type="button"
                      className="rag-doc-card__expand-btn"
                      onClick={(e) => {
                        e.stopPropagation();
                        setExpandDoc({ docId: d.document_id, filename: d.name, segments: [], summary: '', loading: true, chunkId: d.id, chunkSnippet: (d.content || '').slice(0, 150) });
                      }}
                      title={t('expandFile')}
                    >
                      <span className="material-symbols-outlined" style={{ fontSize: 14 }}>open_in_new</span>
                      <span>{t('expandFile')}</span>
                    </button>
                  )}
                </div>
              </div>
            ))
          )}
        </div>
      </aside>

      {expandDoc.docId != null && (
        <div
          className="profile-modal-overlay"
          role="dialog"
          aria-modal="true"
          aria-labelledby="rag-expand-doc-title"
        >
          <div
            className="profile-modal-backdrop"
            onClick={() => setExpandDoc({ docId: null, filename: '', segments: [], summary: '', loading: false, chunkId: null, chunkSnippet: null })}
          />
          <div className="profile-modal-panel rag-expand-doc-panel" onClick={(e) => e.stopPropagation()}>
            <div className="profile-modal-head">
              <div className="profile-modal-head__left">
                <span className="material-symbols-outlined" style={{ fontSize: 24, color: 'var(--color-primary)' }}>description</span>
                <h2 id="rag-expand-doc-title" className="profile-modal-title" style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  {expandDoc.filename || t('expandFile')}
                </h2>
              </div>
              <button
                type="button"
                className="profile-modal-close"
                aria-label={t('cancel')}
                onClick={() => setExpandDoc({ docId: null, filename: '', segments: [], summary: '', loading: false, chunkId: null, chunkSnippet: null })}
              >
                <span className="material-symbols-outlined">close</span>
              </button>
            </div>
            <div ref={expandDocBodyRef} className="rag-expand-doc-body">
              <div className="rag-expand-doc-source-guide">
                <div className="rag-expand-doc-source-guide__title">{t('sourceGuide')}</div>
                <div className="rag-expand-doc-source-guide__content">
                  {expandDoc.loading
                    ? (t('sourceGuideGenerating'))
                    : (expandDoc.summary && expandDoc.summary.trim())
                      ? expandDoc.summary.trim()
                      : (t('sourceGuideSummaryEmpty'))}
                </div>
              </div>
              {expandDoc.loading ? (
                <p style={{ padding: '2rem', textAlign: 'center', color: 'var(--color-charcoal-light)' }}>{t('loading') || '加载中…'}</p>
              ) : expandDoc.segments && expandDoc.segments.length > 0 ? (
                <div ref={expandDocContentRef} className="rag-expand-doc-content">
                  {expandDoc.segments.map((seg, idx) => (
                    <div
                      key={seg.chunk_id || idx}
                      data-chunk-id={seg.chunk_id || undefined}
                      data-segment-index={idx}
                      className={`rag-expand-doc-segment rag-expand-doc-segment--${seg.type || 'standalone'}${expandDoc.chunkId && seg.chunk_id === expandDoc.chunkId ? ' rag-expand-doc-segment--highlight' : ''}`}
                      dangerouslySetInnerHTML={{ __html: processMarkdownHtml(parseMarkdownWithLatex(seg.content || '')) }}
                    />
                  ))}
                </div>
              ) : (
                <p style={{ padding: '2rem', color: 'var(--color-charcoal-light)' }}>{t('noReferencesYet') || '暂无内容'}</p>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
