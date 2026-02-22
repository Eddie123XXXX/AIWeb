import React from 'react';
import ReactDOM from 'react-dom/client';
import { App } from './App';
import { LocaleProvider } from './context/LocaleContext';
import './index.css';

// 首屏即应用保存的主题与语言，避免闪烁
try {
  const saved = localStorage.getItem('app-theme') || 'light';
  document.documentElement.setAttribute('data-theme', saved);
  const locale = localStorage.getItem('app-locale');
  document.documentElement.lang = locale === 'en' ? 'en' : 'zh-CN';
} catch (_) {}

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <LocaleProvider>
      <App />
    </LocaleProvider>
  </React.StrictMode>
);
