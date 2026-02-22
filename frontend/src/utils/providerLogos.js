/**
 * 各模型提供商 logo：用于 Header 模型按钮与下拉项左侧展示。
 * 优先使用 Brandfetch Logo API；未配置 Client ID 时回退到 Clearbit。
 */

const PROVIDER_DOMAINS = {
  openai: 'openai.com',
  anthropic: 'anthropic.com',
  deepseek: 'deepseek.com',
  qwen: 'aliyun.com',
  zhipu: 'zhipuai.cn',
  moonshot: 'moonshot.cn',
  gemini: 'gemini.google',
  custom: null,
};

const BRANDFETCH_CLIENT_ID =
  typeof import.meta !== 'undefined' &&
  import.meta.env &&
  import.meta.env.VITE_BRANDFETCH_CLIENT_ID
    ? String(import.meta.env.VITE_BRANDFETCH_CLIENT_ID).trim()
    : '';

/**
 * 使用 Brandfetch 生成 logo 地址
 * @param {string} domain - 域名，如 openai.com
 * @param {{ theme?: 'light'|'dark', w?: number, h?: number }} [opts]
 */
function brandfetchLogoUrl(domain, opts = {}) {
  if (!BRANDFETCH_CLIENT_ID || !domain) return null;
  const theme = opts.theme || 'light';
  const w = opts.w ?? 64;
  const h = opts.h ?? 64;
  const base = `https://cdn.brandfetch.io/domain/${domain}`;
  const path = `${base}/w/${w}/h/${h}/theme/${theme}/fallback/lettermark/type/icon`;
  return `${path}?c=${encodeURIComponent(BRANDFETCH_CLIENT_ID)}`;
}

/**
 * 使用 Clearbit 生成 logo 地址（无 Brandfetch Client ID 时的回退）
 */
function clearbitLogoUrl(domain) {
  if (!domain) return null;
  return `https://logo.clearbit.com/${domain}`;
}

/**
 * 获取提供商 logo 图片地址。优先 Brandfetch，否则 Clearbit。
 * @param {string} provider - 提供商标识
 * @param {{ theme?: 'light'|'dark' }} [opts] - theme 仅对 Brandfetch 生效
 */
export function getProviderLogoUrl(provider, opts = {}) {
  if (!provider || typeof provider !== 'string') return null;
  const domain = PROVIDER_DOMAINS[provider.toLowerCase()];
  if (!domain) return null;
  if (BRANDFETCH_CLIENT_ID) return brandfetchLogoUrl(domain, opts);
  return clearbitLogoUrl(domain);
}

/**
 * 获取提供商首字母，用于 logo 加载失败时的回退展示
 */
export function getProviderFallbackLetter(provider) {
  if (!provider || typeof provider !== 'string') return '?';
  const p = provider.toLowerCase();
  if (p === 'openai') return 'O';
  if (p === 'anthropic') return 'A';
  if (p === 'deepseek') return 'D';
  if (p === 'qwen') return 'Q';
  if (p === 'zhipu') return 'Z';
  if (p === 'moonshot') return 'K';
  if (p === 'gemini') return 'G';
  if (p === 'custom') return 'C';
  return provider.charAt(0).toUpperCase() || '?';
}
