import React from 'react';
import ReactDOM from 'react-dom/client';
import { App } from './App';
import './index.css';

// 首屏即应用保存的主题，避免闪烁
try {
  const saved = localStorage.getItem('app-theme') || 'light';
  document.documentElement.setAttribute('data-theme', saved);
} catch (_) {}

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
