import React, { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import logoImg from '../../img/Ling_Flowing_Logo.png';
import { apiUrl, API_BASE } from '../utils/api';

export function Register() {
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
      setError('密码至少 6 位');
      return;
    }
    if (password !== confirmPassword) {
      setError('两次输入的密码不一致');
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
        setError(msg || '注册失败，请稍后重试');
        return;
      }
      navigate('/login', { replace: true });
    } catch (err) {
      const hint = API_BASE
        ? '请确认后端已启动（默认 http://localhost:8000），且无 CORS/防火墙拦截。'
        : '请确认已启动后端（npm run dev 会通过代理访问 8000 端口）。';
      setError(`无法连接后端：${hint}`);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="login-page">
      <div className="login-container">
        <div className="login-brand">
          <div className="login-logo-wrap">
            <img src={logoImg} alt="" className="login-logo-img" />
          </div>
        </div>

        <div className="login-card">
          <div className="login-card-head">
            <h2 className="login-card-title">注册</h2>
            <p className="login-card-desc">填写以下信息完成注册。</p>
          </div>

          <form className="login-form register-form" onSubmit={handleSubmit}>
            {error && (
              <div className="login-error" role="alert">
                {error}
              </div>
            )}
            <div className="login-field">
              <label className="login-label" htmlFor="register-email">
                邮箱地址 <span className="login-required">*</span>
              </label>
              <input
                id="register-email"
                type="email"
                className="login-input"
                placeholder="请输入邮箱"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                autoComplete="email"
                required
              />
            </div>
            <div className="login-field">
              <label className="login-label" htmlFor="register-password">
                密码 <span className="login-required">*</span>
              </label>
              <input
                id="register-password"
                type="password"
                className="login-input"
                placeholder="至少 6 位"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                autoComplete="new-password"
                required
                minLength={6}
              />
            </div>
            <div className="login-field">
              <label className="login-label" htmlFor="register-confirm">
                确认密码 <span className="login-required">*</span>
              </label>
              <input
                id="register-confirm"
                type="password"
                className="login-input"
                placeholder="再次输入密码"
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                autoComplete="new-password"
                required
              />
            </div>
            <div className="login-field">
              <label className="login-label" htmlFor="register-username">
                用户名 / 昵称
              </label>
              <input
                id="register-username"
                type="text"
                className="login-input"
                placeholder="选填，最多 64 字"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                autoComplete="username"
                maxLength={64}
              />
            </div>
            <div className="login-field">
              <label className="login-label" htmlFor="register-phone-number">
                手机号码
              </label>
              <input
                id="register-phone-number"
                type="tel"
                className="login-input"
                placeholder="选填"
                value={phoneNumber}
                onChange={(e) => setPhoneNumber(e.target.value)}
                autoComplete="tel-national"
                maxLength={20}
              />
            </div>
            <button type="submit" className="login-submit" disabled={loading}>
              {loading ? '注册中…' : '注册'}
            </button>
          </form>
        </div>

        <p className="login-footer-text">
          已有账号？{' '}
          <Link className="login-link-bold" to="/login">
            去登录
          </Link>
        </p>
      </div>
    </div>
  );
}
