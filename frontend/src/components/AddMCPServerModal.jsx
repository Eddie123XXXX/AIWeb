import React, { useState, useEffect, useRef, useCallback } from 'react';
import { useLocale, useTranslation } from '../context/LocaleContext';
import { apiUrl } from '../utils/api';
import { getAuthHeaders } from '../utils/auth';

const PLACEHOLDER_URL_ZH = 'https://mcp.amap.com/mcp?key=你的API_KEY';
const PLACEHOLDER_URL_EN = 'https://mcp.amap.com/mcp?key=YOUR_API_KEY';

function tryParseServerJson(raw) {
  const text = (raw || '').trim();
  if (!text) return null;

  let obj;
  try { obj = JSON.parse(text); } catch { return null; }
  if (!obj || typeof obj !== 'object') return null;

  // 标准格式：{ mcpServers: { name: { url, type?, ... } } }
  const servers = obj.mcpServers || obj.mcp_servers || obj;
  if (typeof servers !== 'object') return null;

  const entries = Object.entries(servers).filter(
    ([, v]) => v && typeof v === 'object' && (v.url || v.endpoint)
  );
  if (entries.length === 0) return null;

  const [serverName, cfg] = entries[0];
  const transport =
    cfg.type === 'streamable_http' || cfg.type === 'streamableHttp'
      ? 'streamable_http'
      : cfg.type === 'sse'
      ? 'sse'
      : (cfg.url || '').includes('/sse')
      ? 'sse'
      : 'streamable_http';

  return {
    name: serverName || '',
    url: cfg.url || cfg.endpoint || '',
    transport,
    apiKey: cfg.api_key || cfg.apiKey || cfg.env?.API_KEY || '',
    toolPrefix: cfg.tool_prefix || cfg.toolPrefix || '',
  };
}

export function AddMCPServerModal({ onClose, onSuccess }) {
  const { locale } = useLocale();
  const t = useTranslation();

  const [jsonText, setJsonText] = useState('');
  const [jsonStatus, setJsonStatus] = useState(''); // '' | 'ok' | 'error'

  const [url, setUrl] = useState('');
  const [name, setName] = useState('');
  const [transport, setTransport] = useState('streamable_http');
  const [toolPrefix, setToolPrefix] = useState('');
  const [apiKey, setApiKey] = useState('');
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState('');
  const urlRef = useRef(null);

  useEffect(() => {
    if (urlRef.current) urlRef.current.focus();
  }, []);

  // URL 变化时自动推断 name
  useEffect(() => {
    if (!url.trim() || name) return;
    try {
      const u = new URL(url.trim());
      const host = u.hostname.replace(/^www\./, '');
      setName(host.split('.')[0] || '');
    } catch { /* ignore */ }
  }, [url]);

  const handleParseJson = useCallback(() => {
    setJsonStatus('');
    const parsed = tryParseServerJson(jsonText);
    if (!parsed) {
      setJsonStatus('error');
      return;
    }
    setUrl(parsed.url);
    setName(parsed.name);
    setTransport(parsed.transport);
    if (parsed.apiKey) setApiKey(parsed.apiKey);
    if (parsed.toolPrefix) setToolPrefix(parsed.toolPrefix);
    setJsonStatus('ok');
    setError('');
  }, [jsonText]);

  // 粘贴到 textarea 时自动尝试解析
  const handleJsonPaste = useCallback((e) => {
    const pasted = e.clipboardData?.getData('text') || '';
    // 延一帧等 state 更新后再解析
    setTimeout(() => {
      const parsed = tryParseServerJson(pasted);
      if (parsed) {
        setUrl(parsed.url);
        setName(parsed.name);
        setTransport(parsed.transport);
        if (parsed.apiKey) setApiKey(parsed.apiKey);
        if (parsed.toolPrefix) setToolPrefix(parsed.toolPrefix);
        setJsonStatus('ok');
        setError('');
      }
    }, 0);
  }, []);

  const transportOptions = [
    { value: 'streamable_http', label: t('mcpModalTransportStreamable') },
    { value: 'sse', label: t('mcpModalTransportSse') },
  ];

  const handleSubmit = async () => {
    if (!url.trim()) { setError(t('mcpModalUrlRequired')); return; }
    setError('');
    setResult(null);
    setLoading(true);
    try {
      const resp = await fetch(apiUrl('/api/agentic/mcp-servers/add'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...getAuthHeaders() },
        body: JSON.stringify({
          name: (name.trim() || url.trim().replace(/https?:\/\//, '').split('/')[0]),
          url: url.trim(),
          transport,
          tool_prefix: toolPrefix.trim(),
          api_key: apiKey.trim() || null,
        }),
      });
      const data = await resp.json();
      if (!resp.ok) {
        const d = data?.detail;
        const msg = typeof d === 'string' ? d : (Array.isArray(d) && d[0]?.msg ? d.map((x) => x.msg).join('; ') : null);
        setError(msg || `${t('mcpModalRequestFailed')} (${resp.status})`);
        return;
      }
      setResult(data);
      if (data.registered?.length > 0 && onSuccess) {
        onSuccess(data.registered);
      }
    } catch (err) {
      setError(err?.message || t('mcpModalNetworkError'));
    } finally {
      setLoading(false);
    }
  };

  const handleBackdropClick = (e) => {
    if (e.target === e.currentTarget) onClose();
  };

  const resetForm = () => {
    setResult(null);
    setUrl('');
    setName('');
    setToolPrefix('');
    setApiKey('');
    setJsonText('');
    setJsonStatus('');
    setError('');
  };

  return (
    <div className="mcp-modal-overlay" onClick={handleBackdropClick} role="dialog" aria-modal="true" aria-label={t('mcpModalTitle')}>
      <div className="mcp-modal" onClick={(e) => e.stopPropagation()}>
        <div className="mcp-modal__head">
          <span className="mcp-modal__icon material-symbols-outlined">extension</span>
          <div className="mcp-modal__title">{t('mcpModalTitle')}</div>
          <button className="mcp-modal__close" onClick={onClose} aria-label={t('mcpModalClose')}>
            <span className="material-symbols-outlined">close</span>
          </button>
        </div>

        {result ? (
          <div className="mcp-modal__result">
            {result.registered?.length > 0 ? (
              <>
                <div className="mcp-modal__result-ok">
                  <span className="material-symbols-outlined">check_circle</span>
                  {t('mcpModalSuccessCount').replace('{n}', result.registered.length)}
                </div>
                <div className="mcp-modal__tool-chips">
                  {result.registered.map((n) => (
                    <span key={n} className="mcp-modal__tool-chip">{n}</span>
                  ))}
                </div>
                {result.skipped?.length > 0 && (
                  <div className="mcp-modal__result-skip">
                    {t('mcpModalSkippedCount').replace('{n}', result.skipped.length)}
                  </div>
                )}
              </>
            ) : (
              <div className="mcp-modal__result-empty">
                <span className="material-symbols-outlined">info</span>
                {t('mcpModalNoTools')}
                {result.skipped?.length > 0 && t('mcpModalNoToolsSkipped').replace('{n}', result.skipped.length)}
              </div>
            )}
            <div className="mcp-modal__env-hint">
              <div className="mcp-modal__env-hint-label">
                <span className="material-symbols-outlined">tips_and_updates</span>
                {t('mcpModalEnvHint')}
              </div>
              <code className="mcp-modal__env-code">{result.env_hint?.split('\n')[1]}</code>
            </div>
            <div className="mcp-modal__result-actions">
              <button className="mcp-modal__btn mcp-modal__btn--secondary" onClick={resetForm}>
                {t('mcpModalContinueAdd')}
              </button>
              <button className="mcp-modal__btn mcp-modal__btn--primary" onClick={onClose}>
                {t('mcpModalDone')}
              </button>
            </div>
          </div>
        ) : (
          <>
            <div className="mcp-modal__form">
              {/* JSON 粘贴区 */}
              <div className="mcp-modal__field">
                <label className="mcp-modal__label">
                  <span className="material-symbols-outlined" style={{ fontSize: '0.95rem', verticalAlign: '-2px', marginRight: '0.25rem' }}>data_object</span>
                  {t('mcpModalJsonParse')}
                </label>
                <div className="mcp-modal__json-wrap">
                  <textarea
                    className="mcp-modal__json-input"
                    rows={4}
                    placeholder={t('mcpModalJsonPlaceholder')}
                    value={jsonText}
                    onChange={(e) => { setJsonText(e.target.value); setJsonStatus(''); }}
                    onPaste={handleJsonPaste}
                    spellCheck={false}
                  />
                  <button
                    type="button"
                    className="mcp-modal__json-parse-btn"
                    onClick={handleParseJson}
                    disabled={!jsonText.trim()}
                  >
                    <span className="material-symbols-outlined">auto_fix_high</span>
                    {t('mcpModalJsonParseBtn')}
                  </button>
                </div>
                {jsonStatus === 'ok' && (
                  <div className="mcp-modal__json-ok">
                    <span className="material-symbols-outlined">check_circle</span>
                    {t('mcpModalJsonParsed')}
                  </div>
                )}
                {jsonStatus === 'error' && (
                  <div className="mcp-modal__json-error">
                    <span className="material-symbols-outlined">error</span>
                    {t('mcpModalJsonParseError')}
                  </div>
                )}
              </div>

              {/* 分隔线 */}
              <div className="mcp-modal__divider">
                <span>{t('mcpModalOrManual')}</span>
              </div>

              {/* 手动表单 */}
              <div className="mcp-modal__field">
                <label className="mcp-modal__label">{t('mcpModalServerUrl')} <span className="mcp-modal__required">*</span></label>
                <input
                  ref={urlRef}
                  className="mcp-modal__input"
                  type="text"
                  placeholder={locale === 'en' ? PLACEHOLDER_URL_EN : PLACEHOLDER_URL_ZH}
                  value={url}
                  onChange={(e) => setUrl(e.target.value)}
                  autoComplete="off"
                  spellCheck={false}
                />
                <div className="mcp-modal__hint">{t('mcpModalServerUrlHint')}</div>
              </div>

              <div className="mcp-modal__row">
                <div className="mcp-modal__field mcp-modal__field--half">
                  <label className="mcp-modal__label">{t('mcpModalName')}</label>
                  <input
                    className="mcp-modal__input"
                    type="text"
                    placeholder={t('mcpModalNamePlaceholder')}
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    autoComplete="off"
                  />
                </div>
                <div className="mcp-modal__field mcp-modal__field--half">
                  <label className="mcp-modal__label">{t('mcpModalToolPrefix')}</label>
                  <input
                    className="mcp-modal__input"
                    type="text"
                    placeholder={t('mcpModalToolPrefixPlaceholder')}
                    value={toolPrefix}
                    onChange={(e) => setToolPrefix(e.target.value)}
                    autoComplete="off"
                  />
                </div>
              </div>

              <div className="mcp-modal__field">
                <label className="mcp-modal__label">{t('mcpModalTransport')}</label>
                <div className="mcp-modal__transport-group">
                  {transportOptions.map((opt) => (
                    <label key={opt.value} className={`mcp-modal__transport-opt${transport === opt.value ? ' mcp-modal__transport-opt--active' : ''}`}>
                      <input
                        type="radio"
                        name="transport"
                        value={opt.value}
                        checked={transport === opt.value}
                        onChange={() => setTransport(opt.value)}
                      />
                      {opt.label}
                    </label>
                  ))}
                </div>
              </div>

              <div className="mcp-modal__field">
                <label className="mcp-modal__label">{t('mcpModalApiKey')}</label>
                <input
                  className="mcp-modal__input"
                  type="password"
                  placeholder={t('mcpModalApiKeyPlaceholder')}
                  value={apiKey}
                  onChange={(e) => setApiKey(e.target.value)}
                  autoComplete="new-password"
                />
              </div>

              {error && (
                <div className="mcp-modal__error">
                  <span className="material-symbols-outlined">error</span>
                  {error}
                </div>
              )}
            </div>

            {/* 底部按钮固定 */}
            <div className="mcp-modal__footer">
              <button type="button" className="mcp-modal__btn mcp-modal__btn--primary" onClick={handleSubmit} disabled={loading || !url.trim()}>
                {loading ? (
                  <>
                    <span className="mcp-modal__spinner" />
                    {t('mcpModalDiscovering')}
                  </>
                ) : (
                  <>
                    <span className="material-symbols-outlined">add_circle</span>
                    {t('mcpModalAddAndDiscover')}
                  </>
                )}
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
