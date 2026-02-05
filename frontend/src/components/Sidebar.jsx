import React from 'react';

const RECENT_ITEMS = [
  { id: '1', icon: 'chat_bubble', label: '项目头脑风暴', active: true },
  { id: '2', icon: 'history', label: 'React 组件帮助' },
  { id: '3', icon: 'history', label: '营销文案 V2' },
  { id: '4', icon: 'history', label: 'Python 脚本调试' },
];

export function Sidebar({ isOpen, onToggle, onNewChat }) {
  const sidebarClass = `sidebar${isOpen ? ' sidebar--open' : ' sidebar--collapsed'}`;
  const menuAriaLabel = isOpen ? '收起侧边栏' : '展开侧边栏';

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
        <div className="sidebar__user">
          <div className="sidebar__avatar" role="img" aria-label="用户头像" />
          <div className="sidebar__user-info">
            <p className="sidebar__user-name">Eddie Xing</p>
            <p className="sidebar__user-plan">免费版</p>
          </div>
        </div>
      </div>
    </aside>
  );
}
