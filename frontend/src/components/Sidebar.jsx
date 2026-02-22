import React, { useState, useEffect, useRef } from 'react';
import { Link } from 'react-router-dom';
import { getStoredUser } from '../utils/auth';
import { useTranslation } from '../context/LocaleContext';
import { LanguageDropdown } from './LanguageDropdown';
import logoImg from '../../img/Ling_Flowing_Logo.png';
import logoImgDark from '../../img/Image.png';

export function Sidebar({
  isOpen,
  onToggle,
  onNewChat,
  onLogout,
  onOpenProfile,
  conversations = [],
  currentConversationId = null,
  onSelectConversation,
  onRenameConversation,
  onDeleteConversation,
  loadingConversations = false,
}) {
  const t = useTranslation();
  const user = getStoredUser();
  const displayName = user?.nickname || user?.username || user?.email || t('user');
  const planLabel = user?.plan ?? t('freePlan');
  const avatarUrl = user?.avatar_url;

  const sidebarClass = `sidebar${isOpen ? ' sidebar--open' : ' sidebar--collapsed'}`;
  const menuAriaLabel = isOpen ? t('closeSidebar') : t('openSidebar');
  const [userMenuOpen, setUserMenuOpen] = useState(false);
  const [showLogoutConfirm, setShowLogoutConfirm] = useState(false);
  const [openMenuId, setOpenMenuId] = useState(null);
  const [renameTarget, setRenameTarget] = useState(null);
  const [renameInput, setRenameInput] = useState('');
  const [deleteTargetId, setDeleteTargetId] = useState(null);
  const userMenuRef = useRef(null);
  const convMenuRef = useRef(null);

  const toggleUserMenu = () => {
    setUserMenuOpen((prev) => !prev);
  };

  // 点击头像外部区域时自动关闭浮窗
  useEffect(() => {
    if (!userMenuOpen) return;

    const handleClickOutside = (event) => {
      if (userMenuRef.current && !userMenuRef.current.contains(event.target)) {
        setUserMenuOpen(false);
      }
    };

    document.addEventListener('mousedown', handleClickOutside);
    document.addEventListener('touchstart', handleClickOutside);

    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
      document.removeEventListener('touchstart', handleClickOutside);
    };
  }, [userMenuOpen]);

  // 点击会话菜单外部时关闭
  useEffect(() => {
    if (openMenuId == null) return;
    const handleClickOutside = (event) => {
      if (convMenuRef.current && !convMenuRef.current.contains(event.target)) {
        setOpenMenuId(null);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    document.addEventListener('touchstart', handleClickOutside);
    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
      document.removeEventListener('touchstart', handleClickOutside);
    };
  }, [openMenuId]);

  const handleRenameSubmit = () => {
    const t = renameInput.trim();
    if (renameTarget && t) {
      onRenameConversation?.(renameTarget.id, t);
    }
    setRenameTarget(null);
    setRenameInput('');
  };

  const handleDeleteConfirm = () => {
    if (deleteTargetId) {
      onDeleteConversation?.(deleteTargetId);
    }
    setDeleteTargetId(null);
  };

  return (
    <aside className={sidebarClass} id="sidebar" aria-label="主导航">
      <div className="sidebar__top">
        <div className="sidebar__menu-row">
          <button
            type="button"
            className="sidebar__menu-btn"
            aria-label={menuAriaLabel}
            title={menuAriaLabel}
            onClick={onToggle}
          >
            <span className="material-symbols-outlined">
              {isOpen ? 'menu_open' : 'menu'}
            </span>
          </button>
          <Link to="/" className="sidebar__logo" aria-label="首页">
            <img src={logoImg} alt="" className="sidebar__logo-img logo-img--light" />
            <img src={logoImgDark} alt="" className="sidebar__logo-img logo-img--dark" />
          </Link>
        </div>
        <button type="button" className="sidebar__new-chat" onClick={onNewChat}>
          <span className="material-symbols-outlined">add</span>
          <span>{t('newChat')}</span>
        </button>
      </div>
      <div className="sidebar__recent">
        <p className="sidebar__recent-title">{t('recent')}</p>
        {loadingConversations ? (
          <p className="sidebar__recent-placeholder">{t('loading')}</p>
        ) : conversations.length === 0 ? (
          <p className="sidebar__recent-placeholder">{t('noConversations')}</p>
        ) : (
          conversations.map((item) => (
            <div
              key={item.id}
              className="sidebar__recent-row"
              ref={openMenuId === item.id ? convMenuRef : null}
            >
              <button
                type="button"
                className={`sidebar__recent-btn${currentConversationId === item.id ? ' is-active' : ''}`}
                onClick={() => onSelectConversation?.(item.id)}
              >
                <span className="material-symbols-outlined">chat_bubble</span>
                <span className="sidebar__recent-btn-text">{item.title || t('newConversation')}</span>
                <span
                  role="button"
                  tabIndex={0}
                  className="sidebar__recent-action"
                  aria-label={t('conversationOptions')}
                  onClick={(e) => {
                    e.preventDefault();
                    e.stopPropagation();
                    setOpenMenuId((prev) => (prev === item.id ? null : item.id));
                  }}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' || e.key === ' ') {
                      e.preventDefault();
                      e.stopPropagation();
                      setOpenMenuId((prev) => (prev === item.id ? null : item.id));
                    }
                  }}
                >
                  <span className="material-symbols-outlined">more_horiz</span>
                </span>
              </button>
              {openMenuId === item.id && (
                <div className="sidebar__recent-menu" role="menu">
                  <button
                    type="button"
                    className="sidebar__recent-menu-item"
                    role="menuitem"
                    onClick={() => {
                      setRenameTarget({ id: item.id, title: item.title || t('newConversation') });
                      setRenameInput(item.title || t('newConversation'));
                      setOpenMenuId(null);
                    }}
                  >
                    <span className="material-symbols-outlined sidebar__recent-menu-icon">edit</span>
                    <span>{t('rename')}</span>
                  </button>
                  <button
                    type="button"
                    className="sidebar__recent-menu-item sidebar__recent-menu-item--danger"
                    role="menuitem"
                    onClick={() => {
                      setDeleteTargetId(item.id);
                      setOpenMenuId(null);
                    }}
                  >
                    <span className="material-symbols-outlined sidebar__recent-menu-icon">delete</span>
                    <span>{t('delete')}</span>
                  </button>
                </div>
              )}
            </div>
          ))
        )}
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
            onClick={toggleUserMenu}
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
      {renameTarget && (
        <div className="sidebar__rename-overlay" role="dialog" aria-modal="true" aria-labelledby="sidebar-rename-title">
          <div className="sidebar__rename-backdrop" onClick={() => { setRenameTarget(null); setRenameInput(''); }} />
          <div className="sidebar__rename-card">
            <h2 id="sidebar-rename-title" className="sidebar__rename-title">{t('renameConversation')}</h2>
            <input
              type="text"
              className="sidebar__rename-input"
              value={renameInput}
              onChange={(e) => setRenameInput(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && handleRenameSubmit()}
              placeholder={t('inputNewName')}
              autoFocus
            />
            <div className="sidebar__rename-actions">
              <button type="button" className="sidebar__rename-btn sidebar__rename-btn--cancel" onClick={() => { setRenameTarget(null); setRenameInput(''); }}>
                {t('cancel')}
              </button>
              <button type="button" className="sidebar__rename-btn sidebar__rename-btn--confirm" onClick={handleRenameSubmit}>
                {t('confirm')}
              </button>
            </div>
          </div>
        </div>
      )}
      {deleteTargetId && (
        <div className="sidebar__rename-overlay" role="dialog" aria-modal="true" aria-labelledby="sidebar-delete-title">
          <div className="sidebar__rename-backdrop" onClick={() => setDeleteTargetId(null)} />
          <div className="sidebar__rename-card">
            <h2 id="sidebar-delete-title" className="sidebar__rename-title">{t('deleteConversation')}</h2>
            <p className="sidebar__rename-desc">{t('deleteConfirmDesc')}</p>
            <div className="sidebar__rename-actions">
              <button type="button" className="sidebar__rename-btn sidebar__rename-btn--cancel" onClick={() => setDeleteTargetId(null)}>
                {t('cancel')}
              </button>
              <button type="button" className="sidebar__rename-btn sidebar__rename-btn--danger" onClick={handleDeleteConfirm}>
                {t('delete')}
              </button>
            </div>
          </div>
        </div>
      )}
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
    </aside>
  );
}
