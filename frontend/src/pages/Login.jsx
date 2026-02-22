import React, { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import logoImg from '../../img/Ling_Flowing_Logo.png';
import logoImgDark from '../../img/Image.png';
import { getStoredToken, setStoredToken, setStoredUser } from '../utils/auth';
import { apiUrl } from '../utils/api';
import { useTranslation } from '../context/LocaleContext';
import { useTheme } from '../hooks/useTheme';
import { LanguageDropdown } from '../components/LanguageDropdown';

export { getStoredToken, setStoredToken } from '../utils/auth';

export function Login({ onLoginSuccess }) {
  const t = useTranslation();
  const { toggleTheme } = useTheme();
  const navigate = useNavigate();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    setLoading(true);
    try {
      const res = await fetch(apiUrl('/api/auth/login'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: email.trim(), password }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        const msg = Array.isArray(data.detail) ? data.detail[0]?.msg ?? data.detail[0] : data.detail;
        setError(msg || t('loginFailed'));
        return;
      }
      const token = data.access_token;
      if (token) {
        setStoredToken(token);
        if (data.user) setStoredUser(data.user);
        onLoginSuccess?.(token);
        navigate('/', { replace: true });
      } else {
        setError(t('loginResponseError'));
      }
    } catch (err) {
      setError(t('networkError'));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="login-page">
      <div className="login-page__top">
        <LanguageDropdown placement="below">
          <button
            type="button"
            className="login-page__lang-btn"
            aria-label={t('language')}
            title={t('language')}
          >
            <span className="material-symbols-outlined">language</span>
          </button>
        </LanguageDropdown>
        <button
          type="button"
          className="login-page__theme-btn"
          onClick={toggleTheme}
          title={t('theme')}
          aria-label={t('theme')}
        >
          <span className="material-symbols-outlined theme-icon-light">light_mode</span>
          <span className="material-symbols-outlined theme-icon-dark" aria-hidden="true">dark_mode</span>
        </button>
      </div>
      <div className="login-container">
        <div className="login-brand">
          <div className="login-logo-wrap">
            <img src={logoImg} alt="" className="login-logo-img logo-img--light" />
            <img src={logoImgDark} alt="" className="login-logo-img logo-img--dark" />
          </div>
     
        </div>

        <div className="login-card">
          <div className="login-card-head">
            <h2 className="login-card-title">{t('login')}</h2>
            <p className="login-card-desc">{t('loginCardDesc')}</p>
          </div>

          <form className="login-form" onSubmit={handleSubmit}>
            {error && (
              <div className="login-error" role="alert">
                {error}
              </div>
            )}
            <div className="login-field">
              <label className="login-label" htmlFor="login-email">
                {t('email')}
              </label>
              <input
                id="login-email"
                type="email"
                className="login-input"
                placeholder={t('emailPlaceholder')}
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                autoComplete="email"
                required
              />
            </div>
            <div className="login-field">
              <label className="login-label" htmlFor="login-password">
                {t('password')}
              </label>
              <input
                id="login-password"
                type="password"
                className="login-input"
                placeholder="••••••••"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                autoComplete="current-password"
                required
              />
            </div>
            <button type="submit" className="login-submit" disabled={loading}>
              {loading ? t('loginSubmitting') : t('login')}
            </button>
          </form>

          <div className="login-divider">
            <span className="login-divider-text">{t('loginDividerText')}</span>
          </div>

          <div className="login-social">
            <button type="button" className="login-social-btn" disabled>
              <svg className="login-social-icon" viewBox="0 0 24 24" aria-hidden>
                <path d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z" fill="#4285F4" />
                <path d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" fill="#34A853" />
                <path d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z" fill="#FBBC05" />
                <path d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 12-4.53z" fill="#EA4335" />
              </svg>
              {t('loginWithGoogle')}
            </button>
            <button type="button" className="login-social-btn" disabled>
              <svg className="login-social-icon login-social-icon-wechat" viewBox="0 0 24 24" fill="currentColor" aria-hidden>
                <path d="M8.36 11.23c-.45 0-.82-.35-.82-.79c0-.43.37-.78.82-.78c.45 0 .82.35.82.78c0 .44-.37.79-.82.79m4.84 0c-.45 0-.82-.35-.82-.79c0-.43.37-.78.82-.78s.82.35.82.78c0 .44-.37.79-.82.79M18.8 9.53c0-3.32-3.13-6.02-7-6.02C7.94 3.51 4.8 6.21 4.8 9.53c0 1.83.95 3.46 2.45 4.56l-.61 1.82l2.13-1.07c.4.11.81.16 1.23.16c.4 0 .78-.05 1.15-.12c-.11-.33-.17-.68-.17-1.05c0-2.48 2.37-4.49 5.3-4.49c.53 0 1.05.07 1.52.21m3.11 5.34c0-2.5-2.31-4.53-5.16-4.53c-2.85 0-5.16 2.03-5.16 4.53s2.31 4.53 5.16 4.53c.56 0 1.1-.08 1.6-.24l1.63.81l-.47-1.39c1.1-.81 1.8-2.03 1.8-3.41m-6.66 1.35c-.34 0-.61-.26-.61-.59c0-.33.27-.6.61-.6c.34 0 .61.27.61.6c0 .33-.27.59-.61.59m3.03 0c-.34 0-.61-.26-.61-.59c0-.33.27-.6.61-.6s.61.27.61.6c0 .33-.27.59-.61.59z" />
              </svg>
              {t('loginWithWechat')}
            </button>
          </div>
        </div>

        <p className="login-footer-text">
          {t('noAccountYet')}{' '}
          <Link className="login-link-bold" to="/register">
            {t('registerNow')}
          </Link>
        </p>
      </div>
    </div>
  );
}
