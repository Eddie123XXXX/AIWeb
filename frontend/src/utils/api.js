/**
 * API 基地址：开发时未设置则用相对路径走 Vite 代理；可设 VITE_API_BASE=http://localhost:8000 直连后端排查 404
 */
export const API_BASE = typeof import.meta !== 'undefined' && import.meta.env && import.meta.env.VITE_API_BASE
  ? import.meta.env.VITE_API_BASE.replace(/\/$/, '')
  : '';

export function apiUrl(path) {
  const p = path.startsWith('/') ? path : `/${path}`;
  return `${API_BASE}${p}`;
}
