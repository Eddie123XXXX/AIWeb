import React, { useState, useEffect, useRef } from 'react';

const RECENT_ITEMS = [
  { id: '1', icon: 'chat_bubble', label: '项目头脑风暴', active: true },
  { id: '2', icon: 'history', label: 'React 组件帮助' },
  { id: '3', icon: 'history', label: '营销文案 V2' },
  { id: '4', icon: 'history', label: 'Python 脚本调试' },
];

export function Sidebar({ isOpen, onToggle, onNewChat }) {
  const sidebarClass = `sidebar${isOpen ? ' sidebar--open' : ' sidebar--collapsed'}`;
  const menuAriaLabel = isOpen ? '收起侧边栏' : '展开侧边栏';
  const [userMenuOpen, setUserMenuOpen] = useState(false);
  const userMenuRef = useRef(null);

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
        </div>
        <button type="button" className="sidebar__new-chat" onClick={onNewChat}>
          <span className="material-symbols-outlined">add</span>
          <span>新建对话</span>
        </button>
      </div>
      <div className="sidebar__recent">
        <p className="sidebar__recent-title">最近</p>
        {RECENT_ITEMS.map((item) => (
          <button
            key={item.id}
            type="button"
            className={`sidebar__recent-btn${item.active ? ' is-active' : ''}`}
          >
            <span className="material-symbols-outlined">{item.icon}</span>
            <span>{item.label}</span>
          </button>
        ))}
      </div>
      <div className="sidebar__bottom">
        <button type="button" className="sidebar__nav-btn">
          <span className="material-symbols-outlined">help</span>
          <span>帮助与常见问题</span>
        </button>
        <button type="button" className="sidebar__nav-btn">
          <span className="material-symbols-outlined">settings</span>
          <span>设置</span>
        </button>
        <div className="sidebar__user" ref={userMenuRef}>
          <button
            type="button"
            className="sidebar__user-trigger"
            aria-label="打开个人菜单"
            onClick={toggleUserMenu}
          >
            <div className="sidebar__avatar" aria-hidden="true" />
            <div className="sidebar__user-info">
              <p className="sidebar__user-name">Eddie Xing</p>
              <p className="sidebar__user-plan">免费版</p>
            </div>
          </button>

          {userMenuOpen && (
            <div className="sidebar__user-menu" role="menu">
              <button type="button" className="sidebar__user-menu-item" role="menuitem">
                <span className="material-symbols-outlined sidebar__user-menu-icon" aria-hidden="true">
                  person
                </span>
                <span>个人设置</span>
              </button>
              <button type="button" className="sidebar__user-menu-item" role="menuitem">
                <span className="material-symbols-outlined sidebar__user-menu-icon" aria-hidden="true">
                  credit_card
                </span>
                <span>订阅管理</span>
              </button>
              <button type="button" className="sidebar__user-menu-item" role="menuitem">
                <span className="material-symbols-outlined sidebar__user-menu-icon" aria-hidden="true">
                  logout
                </span>
                <span>退出登录</span>
              </button>
            </div>
          )}
        </div>
      </div>
    </aside>
  );
}
