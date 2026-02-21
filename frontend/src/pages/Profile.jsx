import React, { useState, useEffect, useCallback } from 'react';
import { getAuthHeaders, getStoredUser, setStoredUser } from '../utils/auth';
import { apiUrl } from '../utils/api';
import logoImg from '../../img/Ling_Flowing_Logo.png';

const GENDER_OPTIONS = [
  { value: 0, label: '保密' },
  { value: 1, label: '男' },
  { value: 2, label: '女' },
  { value: 9, label: '其他' },
];

export function Profile({ onClose }) {
  const [me, setMe] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  // 基本信息（users 表）
  const [username, setUsername] = useState('');
  const [phoneCode, setPhoneCode] = useState('');
  const [phoneNumber, setPhoneNumber] = useState('');
  const [savingBasic, setSavingBasic] = useState(false);
  const [basicMessage, setBasicMessage] = useState('');

  // 扩展资料（user_profiles）
  const [nickname, setNickname] = useState('');
  const [avatarUrl, setAvatarUrl] = useState('');
  const [bio, setBio] = useState('');
  const [gender, setGender] = useState(0);
  const [birthday, setBirthday] = useState('');
  const [locationVal, setLocationVal] = useState('');
  const [website, setWebsite] = useState('');
  const [savingProfile, setSavingProfile] = useState(false);
  const [profileMessage, setProfileMessage] = useState('');

  // 个人配置（preferences）
  const [prefTheme, setPrefTheme] = useState('light');
  const [prefLanguage, setPrefLanguage] = useState('zh');
  const [prefDefaultModelId, setPrefDefaultModelId] = useState('');
  const [savingPrefs, setSavingPrefs] = useState(false);
  const [prefsMessage, setPrefsMessage] = useState('');

  const fetchMe = useCallback(async () => {
    try {
      const res = await fetch(apiUrl('/api/user/me'), { headers: getAuthHeaders() });
      if (!res.ok) {
        if (res.status === 401) setError('请重新登录');
        else setError('获取用户信息失败');
        return null;
      }
      const data = await res.json();
      setMe(data);
      setUsername(data.username ?? '');
      setPhoneCode(data.phone_code ?? '');
      setPhoneNumber(data.phone_number ?? '');
      const p = data.profile;
      if (p) {
        setNickname(p.nickname ?? '');
        setAvatarUrl(p.avatar_url ?? '');
        setBio(p.bio ?? '');
        setGender(p.gender ?? 0);
        setBirthday(p.birthday ? p.birthday.slice(0, 10) : '');
        setLocationVal(p.location ?? '');
        setWebsite(p.website ?? '');
        const prefs = p.preferences || {};
        setPrefTheme(prefs.theme ?? 'light');
        setPrefLanguage(prefs.language ?? 'zh');
        setPrefDefaultModelId(prefs.default_model_id ?? '');
      }
      return data;
    } catch (e) {
      setError('网络错误，请稍后重试');
      return null;
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchMe();
  }, [fetchMe]);

  const handleSaveBasic = async (e) => {
    e.preventDefault();
    setBasicMessage('');
    setSavingBasic(true);
    try {
      const res = await fetch(apiUrl('/api/user/me'), {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json', ...getAuthHeaders() },
        body: JSON.stringify({
          username: username.trim() || null,
          phone_code: phoneCode.trim() || null,
          phone_number: phoneNumber.trim() || null,
        }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        const msg = Array.isArray(data.detail) ? data.detail[0]?.msg ?? data.detail?.[0] : data.detail;
        setBasicMessage(typeof msg === 'string' ? msg : '保存失败');
        return;
      }
      setBasicMessage('保存成功');
      const updated = await fetchMe();
      if (updated) {
        setStoredUser({
          ...getStoredUser(),
          id: updated.id,
          email: updated.email,
          username: updated.username,
          phone_code: updated.phone_code,
          phone_number: updated.phone_number,
          nickname: updated.profile?.nickname,
          avatar_url: updated.profile?.avatar_url,
        });
      }
    } catch {
      setBasicMessage('网络错误');
    } finally {
      setSavingBasic(false);
    }
  };

  const handleSaveProfile = async (e) => {
    e.preventDefault();
    setProfileMessage('');
    setSavingProfile(true);
    try {
      const res = await fetch(apiUrl('/api/user/me/profile'), {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json', ...getAuthHeaders() },
        body: JSON.stringify({
          nickname: nickname.trim() || null,
          avatar_url: avatarUrl.trim() || null,
          bio: bio.trim() || null,
          gender,
          birthday: birthday.trim() || null,
          location: locationVal.trim() || null,
          website: website.trim() || null,
        }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        const msg = Array.isArray(data.detail) ? data.detail[0]?.msg ?? data.detail?.[0] : data.detail;
        setProfileMessage(typeof msg === 'string' ? msg : '保存失败');
        return;
      }
      setProfileMessage('保存成功');
      const updated = await fetchMe();
      if (updated?.profile) {
        setStoredUser({
          ...getStoredUser(),
          nickname: updated.profile.nickname,
          avatar_url: updated.profile.avatar_url,
        });
      }
    } catch {
      setProfileMessage('网络错误');
    } finally {
      setSavingProfile(false);
    }
  };

  const handleSavePrefs = async (e) => {
    e.preventDefault();
    setPrefsMessage('');
    setSavingPrefs(true);
    try {
      const prefs = {
        theme: prefTheme,
        language: prefLanguage,
        default_model_id: prefDefaultModelId.trim() || null,
      };
      const res = await fetch(apiUrl('/api/user/me/profile'), {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json', ...getAuthHeaders() },
        body: JSON.stringify({
          preferences: prefs,
        }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        const msg = Array.isArray(data.detail) ? data.detail[0]?.msg ?? data.detail?.[0] : data.detail;
        setPrefsMessage(typeof msg === 'string' ? msg : '保存失败');
        return;
      }
      setPrefsMessage('保存成功');
    } catch {
      setPrefsMessage('网络错误');
    } finally {
      setSavingPrefs(false);
    }
  };

  if (loading) {
    return (
      <div className="profile-page">
        <div className="profile-loading">加载中…</div>
      </div>
    );
  }

  if (error && !me) {
    return (
      <div className="profile-page">
        <div className="profile-error">{error}</div>
        {onClose ? (
          <button type="button" className="login-submit profile-submit" onClick={onClose}>
            关闭
          </button>
        ) : null}
      </div>
    );
  }

  return (
    <div className={onClose ? 'profile-modal-inner' : 'profile-page-wrap'}>
      {onClose && (
        <div className="profile-modal-head">
          <div className="profile-modal-head__left">
            <img src={logoImg} alt="" className="profile-modal-head__logo" />
            <h2 id="profile-modal-title" className="profile-modal-title">个人中心</h2>
          </div>
          <button
            type="button"
            className="profile-modal-close"
            aria-label="关闭"
            onClick={onClose}
          >
            <span className="material-symbols-outlined">close</span>
          </button>
        </div>
      )}
      <div className="profile-page">
        <div className="profile-grid">
          {/* 基本信息 */}
          <section className="profile-card">
            <h2 className="profile-card-title">
              <span className="material-symbols-outlined profile-card-icon">person</span>
              基本信息
            </h2>
            <p className="profile-card-desc">账号用户名与手机号（不包含邮箱与密码）</p>
            <form className="profile-form" onSubmit={handleSaveBasic}>
              <div className="login-field">
                <label className="login-label" htmlFor="profile-username">用户名</label>
                <input
                  id="profile-username"
                  type="text"
                  className="login-input"
                  placeholder="选填"
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  maxLength={64}
                />
              </div>
              <div className="login-field-row">
                <div className="login-field login-field-half">
                  <label className="login-label" htmlFor="profile-phone-code">区号</label>
                  <input
                    id="profile-phone-code"
                    type="text"
                    className="login-input"
                    placeholder="+86"
                    value={phoneCode}
                    onChange={(e) => setPhoneCode(e.target.value)}
                    maxLength={10}
                  />
                </div>
                <div className="login-field login-field-flex">
                  <label className="login-label" htmlFor="profile-phone-number">手机号</label>
                  <input
                    id="profile-phone-number"
                    type="text"
                    className="login-input"
                    placeholder="选填"
                    value={phoneNumber}
                    onChange={(e) => setPhoneNumber(e.target.value)}
                    maxLength={20}
                  />
                </div>
              </div>
              {me?.email && (
                <p className="profile-readonly">邮箱：{me.email}（不可修改）</p>
              )}
              {basicMessage && (
                <p className={basicMessage === '保存成功' ? 'profile-msg profile-msg--ok' : 'profile-msg profile-msg--err'}>
                  {basicMessage}
                </p>
              )}
              <button type="submit" className="login-submit profile-submit" disabled={savingBasic}>
                {savingBasic ? '保存中…' : '保存基本信息'}
              </button>
            </form>
          </section>

          {/* 扩展资料 */}
          <section className="profile-card">
            <h2 className="profile-card-title">
              <span className="material-symbols-outlined profile-card-icon">badge</span>
              扩展资料
            </h2>
            <p className="profile-card-desc">昵称、头像、简介、性别、生日、地区、个人网站</p>
            <form className="profile-form" onSubmit={handleSaveProfile}>
              <div className="login-field">
                <label className="login-label" htmlFor="profile-nickname">昵称</label>
                <input
                  id="profile-nickname"
                  type="text"
                  className="login-input"
                  placeholder="选填"
                  value={nickname}
                  onChange={(e) => setNickname(e.target.value)}
                  maxLength={64}
                />
              </div>
              <div className="login-field">
                <label className="login-label" htmlFor="profile-avatar">头像 URL</label>
                <input
                  id="profile-avatar"
                  type="url"
                  className="login-input"
                  placeholder="https://..."
                  value={avatarUrl}
                  onChange={(e) => setAvatarUrl(e.target.value)}
                  maxLength={255}
                />
                {avatarUrl && (
                  <div className="profile-avatar-preview">
                    <img src={avatarUrl} alt="" onError={(e) => { e.target.style.display = 'none'; }} />
                  </div>
                )}
              </div>
              <div className="login-field">
                <label className="login-label" htmlFor="profile-bio">个人简介</label>
                <textarea
                  id="profile-bio"
                  className="login-input profile-textarea"
                  placeholder="选填，最多 500 字"
                  value={bio}
                  onChange={(e) => setBio(e.target.value)}
                  maxLength={500}
                  rows={3}
                />
              </div>
              <div className="login-field">
                <label className="login-label">性别</label>
                <select
                  className="login-input"
                  value={gender}
                  onChange={(e) => setGender(Number(e.target.value))}
                >
                  {GENDER_OPTIONS.map((o) => (
                    <option key={o.value} value={o.value}>{o.label}</option>
                  ))}
                </select>
              </div>
              <div className="login-field">
                <label className="login-label" htmlFor="profile-birthday">生日</label>
                <input
                  id="profile-birthday"
                  type="date"
                  className="login-input"
                  value={birthday}
                  onChange={(e) => setBirthday(e.target.value)}
                />
              </div>
              <div className="login-field">
                <label className="login-label" htmlFor="profile-location">地区</label>
                <input
                  id="profile-location"
                  type="text"
                  className="login-input"
                  placeholder="选填"
                  value={locationVal}
                  onChange={(e) => setLocationVal(e.target.value)}
                  maxLength={100}
                />
              </div>
              <div className="login-field">
                <label className="login-label" htmlFor="profile-website">个人网站</label>
                <input
                  id="profile-website"
                  type="url"
                  className="login-input"
                  placeholder="https://..."
                  value={website}
                  onChange={(e) => setWebsite(e.target.value)}
                  maxLength={255}
                />
              </div>
              {profileMessage && (
                <p className={profileMessage === '保存成功' ? 'profile-msg profile-msg--ok' : 'profile-msg profile-msg--err'}>
                  {profileMessage}
                </p>
              )}
              <button type="submit" className="login-submit profile-submit" disabled={savingProfile}>
                {savingProfile ? '保存中…' : '保存扩展资料'}
              </button>
            </form>
          </section>

          {/* 个人配置 */}
          <section className="profile-card">
            <h2 className="profile-card-title">
              <span className="material-symbols-outlined profile-card-icon">tune</span>
              个人配置
            </h2>
            <p className="profile-card-desc">主题、语言、默认模型等偏好（仅保存到账号，不立即生效）</p>
            <form className="profile-form" onSubmit={handleSavePrefs}>
              <div className="login-field">
                <label className="login-label" htmlFor="profile-pref-theme">偏好主题</label>
                <select
                  id="profile-pref-theme"
                  className="login-input"
                  value={prefTheme}
                  onChange={(e) => setPrefTheme(e.target.value)}
                >
                  <option value="light">浅色</option>
                  <option value="dark">深色</option>
                </select>
              </div>
              <div className="login-field">
                <label className="login-label" htmlFor="profile-pref-language">偏好语言</label>
                <select
                  id="profile-pref-language"
                  className="login-input"
                  value={prefLanguage}
                  onChange={(e) => setPrefLanguage(e.target.value)}
                >
                  <option value="zh">简体中文</option>
                  <option value="en">English</option>
                </select>
              </div>
              <div className="login-field">
                <label className="login-label" htmlFor="profile-pref-model">默认模型 ID</label>
                <input
                  id="profile-pref-model"
                  type="text"
                  className="login-input"
                  placeholder="如 default，选填"
                  value={prefDefaultModelId}
                  onChange={(e) => setPrefDefaultModelId(e.target.value)}
                />
              </div>
              {prefsMessage && (
                <p className={prefsMessage === '保存成功' ? 'profile-msg profile-msg--ok' : 'profile-msg profile-msg--err'}>
                  {prefsMessage}
                </p>
              )}
              <button type="submit" className="login-submit profile-submit" disabled={savingPrefs}>
                {savingPrefs ? '保存中…' : '保存个人配置'}
              </button>
            </form>
          </section>
        </div>
      </div>
    </div>
  );
}
