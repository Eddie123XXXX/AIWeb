import React, { useState } from 'react';
import { useTheme } from '../hooks/useTheme';
import { getProviderLogoUrl, getProviderFallbackLetter } from '../utils/providerLogos';

/**
 * 在模型名称左侧展示提供商 logo；加载失败或无 URL 时显示首字母。
 * 优先使用 Brandfetch（需配置 VITE_BRANDFETCH_CLIENT_ID），否则 Clearbit。
 * @param {string} provider - 提供商标识，如 openai、moonshot
 * @param {string} [className] - 额外类名，用于尺寸/圆角等
 */
export function ProviderLogo({ provider, className = '' }) {
  const { theme } = useTheme();
  const [imgFailed, setImgFailed] = useState(false);
  const brandfetchTheme = theme === 'dark' ? 'dark' : 'light';
  const url = getProviderLogoUrl(provider, { theme: brandfetchTheme });
  const letter = getProviderFallbackLetter(provider);
  const showImg = url && !imgFailed;

  return (
    <span
      className={`provider-logo ${className}`.trim()}
      aria-hidden="true"
      role="img"
    >
      {showImg ? (
        <img
          src={url}
          alt=""
          onError={() => setImgFailed(true)}
          className="provider-logo__img"
        />
      ) : (
        <span className="provider-logo__fallback">{letter}</span>
      )}
    </span>
  );
}
