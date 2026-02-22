import React, { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import logoImg from '../../img/Ling_Flowing_Logo.png';
import logoImgDark from '../../img/Image.png';
import { apiUrl, API_BASE } from '../utils/api';
import { useTranslation } from '../context/LocaleContext';
import { useTheme } from '../hooks/useTheme';
import { LanguageDropdown } from '../components/LanguageDropdown';

export function Register() {
  const t = useTranslation();
  const { toggleTheme } = useTheme();
  const navigate = useNavigate();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [username, setUsername] = useState('');
  const [phoneNumber, setPhoneNumber] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    if (password.length < 6) {
      setError(t('passwordMinLength'));
      return;
    }
    if (password !== confirmPassword) {
      setError(t('passwordMismatch'));
      return;
    }
    setLoading(true);
    const url = apiUrl('/api/user/register');
    try {
      const body = {
        email: email.trim().toLowerCase(),
        password,
        username: username.trim() || undefined,
        phone_number: phoneNumber.trim() || undefined,
      };
      const res = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        const msg = Array.isArray(data.detail) ? data.detail[0]?.msg ?? data.detail[0] : data.detail;
        setError(msg || t('registerFailed'));
        return;
      }
      navigate('/login', { replace: true });
    } catch (err) {
      const hint = API_BASE ? t('backendConnectionHint') : t('backendConnectionHintProxy');
      setError(t('cannotConnectBackend') + hint);
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
            <h2 className="login-card-title">{t('register')}</h2>
            <p className="login-card-desc">{t('registerCardDesc')}</p>
          </div>

          <form className="login-form register-form" onSubmit={handleSubmit}>
            {error && (
              <div className="login-error" role="alert">
                {error}
              </div>
            )}
            <div className="login-field">
              <label className="login-label" htmlFor="register-email">
                {t('email')} <span className="login-required">*</span>
              </label>
              <input
                id="register-email"
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
              <label className="login-label" htmlFor="register-password">
                {t('password')} <span className="login-required">*</span>
              </label>
              <input
                id="register-password"
                type="password"
                className="login-input"
                placeholder={t('passwordPlaceholderMin')}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                autoComplete="new-password"
                required
                minLength={6}
              />
            </div>
            <div className="login-field">
              <label className="login-label" htmlFor="register-confirm">
                {t('confirmPassword')} <span className="login-required">*</span>
              </label>
              <input
                id="register-confirm"
                type="password"
                className="login-input"
                placeholder={t('confirmPasswordPlaceholder')}
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                autoComplete="new-password"
                required
              />
            </div>
            <div className="login-field">
              <label className="login-label" htmlFor="register-username">
                {t('usernameOrNickname')}
              </label>
              <input
                id="register-username"
                type="text"
                className="login-input"
                placeholder={t('optionalMax64')}
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                autoComplete="username"
                maxLength={64}
              />
            </div>
            <div className="login-field">
              <label className="login-label" htmlFor="register-phone-number">
                {t('phoneNumber')}
              </label>
              <input
                id="register-phone-number"
                type="tel"
                className="login-input"
                placeholder={t('optional')}
                value={phoneNumber}
                onChange={(e) => setPhoneNumber(e.target.value)}
                autoComplete="tel-national"
                maxLength={20}
              />
            </div>
            <button type="submit" className="login-submit" disabled={loading}>
              {loading ? t('registerSubmitting') : t('register')}
            </button>
          </form>
        </div>

        <p className="login-footer-text">
          {t('haveAccount')}{' '}
          <Link className="login-link-bold" to="/login">
            {t('goToLogin')}
          </Link>
        </p>
      </div>
    </div>
  );
}
