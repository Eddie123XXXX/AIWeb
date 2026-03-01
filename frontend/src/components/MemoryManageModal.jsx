import React, { useState, useEffect, useCallback, useRef } from 'react';
import { useTranslation } from '../context/LocaleContext';
import { apiUrl } from '../utils/api';
import { getAuthHeaders } from '../utils/auth';

const MEMORY_DOMAINS = [
  'general_chat',
  'user_preferences',
  'professional_and_academic',
  'lifestyle_and_interests',
  'social_and_relationships',
  'tasks_and_schedules',
];

const DOMAIN_LABEL_KEYS = {
  general_chat: 'memoryDomainGeneralChat',
  user_preferences: 'memoryDomainUserPreferences',
  professional_and_academic: 'memoryDomainProfessionalAndAcademic',
  lifestyle_and_interests: 'memoryDomainLifestyleAndInterests',
  social_and_relationships: 'memoryDomainSocialAndRelationships',
  tasks_and_schedules: 'memoryDomainTasksAndSchedules',
};

function getDomainLabel(domain, t) {
  return t(DOMAIN_LABEL_KEYS[domain] || domain);
}

export function MemoryManageModal({ onClose }) {
  const t = useTranslation();
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [menuOpenId, setMenuOpenId] = useState(null);
  const [addModalOpen, setAddModalOpen] = useState(false);
  const [editModalOpen, setEditModalOpen] = useState(false);
  const [editingMemory, setEditingMemory] = useState(null);
  const [editContent, setEditContent] = useState('');
  const [editDomain, setEditDomain] = useState('general_chat');
  const [editImportance, setEditImportance] = useState(0.5);
  const [addContent, setAddContent] = useState('');
  const [addDomain, setAddDomain] = useState('general_chat');
  const [addImportance, setAddImportance] = useState(0.5);
  const [submitting, setSubmitting] = useState(false);
  const [deleteConfirmId, setDeleteConfirmId] = useState(null);
  const menuRef = useRef(null);

  const fetchList = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(apiUrl('/api/memory/list?limit=200&offset=0'), {
        headers: getAuthHeaders(),
      });
      if (!res.ok) throw new Error(await res.text());
      const data = await res.json();
      setItems(data.items || []);
    } catch (e) {
      setError(e?.message || '加载失败');
      setItems([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchList();
  }, [fetchList]);

  useEffect(() => {
    if (!menuOpenId) return;
    const handleClickOutside = (e) => {
      if (menuRef.current && !menuRef.current.contains(e.target)) setMenuOpenId(null);
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [menuOpenId]);

  const handleAdd = async () => {
    const content = addContent.trim();
    if (!content) return;
    setSubmitting(true);
    try {
      const res = await fetch(apiUrl('/api/memory/create'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...getAuthHeaders() },
        body: JSON.stringify({
          content,
          domain: addDomain,
          memory_type: 'fact',
          importance_score: addImportance,
        }),
      });
      if (!res.ok) throw new Error((await res.json()).detail || '新增失败');
      setAddContent('');
      setAddDomain('general_chat');
      setAddImportance(0.5);
      setAddModalOpen(false);
      await fetchList();
    } catch (e) {
      setError(e?.message || '新增失败');
    } finally {
      setSubmitting(false);
    }
  };

  const closeAddModal = () => {
    setAddModalOpen(false);
    setAddContent('');
    setAddDomain('general_chat');
    setAddImportance(0.5);
  };

  const openEditModal = (m) => {
    setMenuOpenId(null);
    setEditingMemory(m);
    setEditContent(m.content || '');
    setEditDomain(m.domain || 'general_chat');
    setEditImportance(m.importance_score ?? 0.5);
    setEditModalOpen(true);
  };

  const closeEditModal = () => {
    setEditModalOpen(false);
    setEditingMemory(null);
  };

  const handleSaveEdit = async () => {
    if (!editingMemory) return;
    const content = editContent.trim();
    if (!content) return;
    setSubmitting(true);
    try {
      const res = await fetch(apiUrl(`/api/memory/${editingMemory.id}`), {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json', ...getAuthHeaders() },
        body: JSON.stringify({
          content,
          domain: editDomain,
          importance_score: editImportance,
        }),
      });
      if (!res.ok) throw new Error((await res.json()).detail || '保存失败');
      closeEditModal();
      await fetchList();
    } catch (e) {
      setError(e?.message || '保存失败');
    } finally {
      setSubmitting(false);
    }
  };

  const handleDelete = async (id) => {
    setSubmitting(true);
    try {
      const res = await fetch(apiUrl(`/api/memory/${id}`), {
        method: 'DELETE',
        headers: getAuthHeaders(),
      });
      if (!res.ok) throw new Error((await res.json()).detail || '删除失败');
      setDeleteConfirmId(null);
      await fetchList();
    } catch (e) {
      setError(e?.message || '删除失败');
    } finally {
      setSubmitting(false);
    }
  };

  const formatDate = (d) => {
    if (!d) return '';
    const date = new Date(d);
    return date.toLocaleString();
  };

  return (
    <div className="profile-modal-overlay" role="dialog" aria-modal="true" aria-labelledby="memory-manage-title">
      <div className="profile-modal-backdrop" onClick={onClose} />
      <div className="profile-modal-panel memory-manage-panel" onClick={(e) => e.stopPropagation()}>
        <div className="profile-modal-head">
          <div className="profile-modal-head__left">
            <span className="material-symbols-outlined" style={{ fontSize: 24, color: 'var(--color-primary)' }}>
              psychology
            </span>
            <h2 id="memory-manage-title" className="profile-modal-title">
              {t('memoryManageTitle')}
            </h2>
          </div>
          <div className="profile-modal-head__right">
            <button
              type="button"
              className="memory-manage-head-add-btn"
              onClick={() => setAddModalOpen(true)}
            >
              <span className="material-symbols-outlined">add</span>
              {t('memoryAdd')}
            </button>
            <button type="button" className="profile-modal-close" aria-label={t('cancel')} onClick={onClose}>
              <span className="material-symbols-outlined">close</span>
            </button>
          </div>
        </div>

        <div className="memory-manage-body">
          {error && (
            <p className="memory-manage-error" role="alert">
              {error}
            </p>
          )}

          <section className="memory-manage-list">
            {loading ? (
              <p className="memory-manage-loading">{t('loading')}</p>
            ) : items.length === 0 ? (
              <p className="memory-manage-empty">{t('memoryNoItems')}</p>
            ) : (
              <ul className="memory-manage-items">
                {items.map((m) => (
                  <li key={m.id} className="memory-manage-item">
                    <div className="memory-manage-item-main">
                      <div className="memory-manage-item-content">{m.content}</div>
                      <div className="memory-manage-item-meta">
                        <span>{getDomainLabel(m.domain, t)}</span>
                      </div>
                    </div>
                    <div className="memory-manage-item-menu-wrap" ref={menuOpenId === m.id ? menuRef : null}>
                      <button
                        type="button"
                        className="memory-manage-item-menu-btn"
                        aria-label={t('memoryEdit')}
                        aria-expanded={menuOpenId === m.id}
                        onClick={() => setMenuOpenId(menuOpenId === m.id ? null : m.id)}
                      >
                        <span className="material-symbols-outlined">more_vert</span>
                      </button>
                      {menuOpenId === m.id && (
                        <div className="memory-manage-item-dropdown" role="menu">
                          <button
                            type="button"
                            className="memory-manage-item-dropdown-btn"
                            role="menuitem"
                            onClick={() => openEditModal(m)}
                          >
                            <span className="material-symbols-outlined">edit</span>
                            {t('memoryEditLabel')}
                          </button>
                          <button
                            type="button"
                            className="memory-manage-item-dropdown-btn"
                            role="menuitem"
                            onClick={() => {
                              setMenuOpenId(null);
                              setDeleteConfirmId(m.id);
                            }}
                          >
                            <span className="material-symbols-outlined">delete</span>
                            {t('memoryDeleteLabel')}
                          </button>
                        </div>
                      )}
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </section>
        </div>
      </div>

      {/* 添加记忆弹窗 */}
      {addModalOpen && (
        <div className="profile-modal-overlay memory-edit-modal-overlay" role="dialog" aria-modal="true" aria-labelledby="memory-add-title">
          <div className="profile-modal-backdrop" onClick={closeAddModal} />
          <div className="profile-modal-panel memory-manage-panel memory-edit-modal" onClick={(e) => e.stopPropagation()}>
            <div className="profile-modal-head">
              <h2 id="memory-add-title" className="profile-modal-title">
                {t('memoryAdd')}
              </h2>
              <button type="button" className="profile-modal-close" aria-label={t('cancel')} onClick={closeAddModal}>
                <span className="material-symbols-outlined">close</span>
              </button>
            </div>
            <div className="memory-manage-body">
              <label className="memory-edit-field">
                <span>{t('memoryContent')}</span>
                <textarea
                  className="memory-manage-input"
                  placeholder={t('memoryContent')}
                  value={addContent}
                  onChange={(e) => setAddContent(e.target.value)}
                  rows={4}
                />
              </label>
              <div className="memory-edit-meta">
                <label>
                  <span>{t('memoryDomain')}</span>
                  <select value={addDomain} onChange={(e) => setAddDomain(e.target.value)}>
                    {MEMORY_DOMAINS.map((d) => (
                      <option key={d} value={d}>
                        {getDomainLabel(d, t)}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  <span>{t('memoryImportance')}</span>
                  <input
                    type="number"
                    min="0"
                    max="1"
                    step="0.1"
                    value={addImportance}
                    onChange={(e) => setAddImportance(Number(e.target.value))}
                  />
                </label>
              </div>
              <div className="memory-edit-actions">
                <button
                  type="button"
                  className="memory-manage-btn memory-manage-btn--primary"
                  onClick={handleAdd}
                  disabled={submitting || !addContent.trim()}
                >
                  {t('memoryAdd')}
                </button>
                <button type="button" className="memory-manage-btn" onClick={closeAddModal}>
                  {t('cancel')}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* 编辑记忆弹窗 */}
      {editModalOpen && editingMemory && (
        <div className="profile-modal-overlay memory-edit-modal-overlay" role="dialog" aria-modal="true" aria-labelledby="memory-edit-title">
          <div className="profile-modal-backdrop" onClick={closeEditModal} />
          <div className="profile-modal-panel memory-manage-panel memory-edit-modal" onClick={(e) => e.stopPropagation()}>
            <div className="profile-modal-head">
              <h2 id="memory-edit-title" className="profile-modal-title">
                {t('memoryEditTitle')}
              </h2>
              <button type="button" className="profile-modal-close" aria-label={t('cancel')} onClick={closeEditModal}>
                <span className="material-symbols-outlined">close</span>
              </button>
            </div>
            <div className="memory-manage-body">
              <label className="memory-edit-field">
                <span>{t('memoryContent')}</span>
                <textarea
                  className="memory-manage-input"
                  value={editContent}
                  onChange={(e) => setEditContent(e.target.value)}
                  rows={4}
                />
              </label>
              <div className="memory-edit-meta">
                <label>
                  <span>{t('memoryDomain')}</span>
                  <select value={editDomain} onChange={(e) => setEditDomain(e.target.value)}>
                    {MEMORY_DOMAINS.map((d) => (
                      <option key={d} value={d}>
                        {getDomainLabel(d, t)}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  <span>{t('memoryImportance')}</span>
                  <input
                    type="number"
                    min="0"
                    max="1"
                    step="0.1"
                    value={editImportance}
                    onChange={(e) => setEditImportance(Number(e.target.value))}
                  />
                </label>
              </div>
              <div className="memory-edit-actions">
                <button
                  type="button"
                  className="memory-manage-btn memory-manage-btn--primary"
                  onClick={handleSaveEdit}
                  disabled={submitting || !editContent.trim()}
                >
                  {t('memorySave')}
                </button>
                <button type="button" className="memory-manage-btn" onClick={closeEditModal}>
                  {t('cancel')}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* 删除确认弹窗（与退出登录确认弹窗风格一致） */}
      {deleteConfirmId && (
        <div
          className="logout-confirm-overlay"
          role="dialog"
          aria-modal="true"
          aria-labelledby="memory-delete-confirm-title"
        >
          <div className="logout-confirm-backdrop" onClick={() => setDeleteConfirmId(null)} />
          <div className="logout-confirm-card" onClick={(e) => e.stopPropagation()}>
            <h2 id="memory-delete-confirm-title" className="logout-confirm-title">
              {t('memoryDeleteLabel')}
            </h2>
            <p className="logout-confirm-desc">{t('memoryDeleteConfirm')}</p>
            <div className="logout-confirm-actions">
              <button
                type="button"
                className="logout-confirm-btn logout-confirm-btn--cancel"
                onClick={() => setDeleteConfirmId(null)}
              >
                {t('cancel')}
              </button>
              <button
                type="button"
                className="logout-confirm-btn logout-confirm-btn--confirm"
                onClick={() => handleDelete(deleteConfirmId)}
                disabled={submitting}
              >
                {t('confirm')}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
