/**
 * 认证工具：token 与用户信息存储、请求头
 * 与后端标准登录流程配合：登录后存 token，请求需登录接口时带 Authorization: Bearer <token>
 */

const AUTH_TOKEN_KEY = 'auth_token';
const AUTH_USER_KEY = 'auth_user';

export function getStoredToken() {
  try {
    return window.localStorage.getItem(AUTH_TOKEN_KEY);
  } catch {
    return null;
  }
}

export function setStoredToken(token) {
  try {
    if (token) window.localStorage.setItem(AUTH_TOKEN_KEY, token);
    else window.localStorage.removeItem(AUTH_TOKEN_KEY);
  } catch (_) {}
}

export function getStoredUser() {
  try {
    const raw = window.localStorage.getItem(AUTH_USER_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

export function setStoredUser(user) {
  try {
    if (user) window.localStorage.setItem(AUTH_USER_KEY, JSON.stringify(user));
    else window.localStorage.removeItem(AUTH_USER_KEY);
  } catch (_) {}
}

/** 登出：清除 token 与用户信息 */
export function clearAuth() {
  setStoredToken(null);
  setStoredUser(null);
}

/**
 * 请求头：带 Authorization Bearer（若有 token）
 * 用于 fetch('/api/xxx', { headers: { ...getAuthHeaders() } })
 */
export function getAuthHeaders() {
  const token = getStoredToken();
  if (!token) return {};
  return { Authorization: `Bearer ${token}` };
}
