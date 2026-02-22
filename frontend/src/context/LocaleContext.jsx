import React, { createContext, useContext, useState, useCallback, useMemo, useEffect } from 'react';
import { translations } from '../data/translations';

const STORAGE_KEY = 'app-locale';

function getStoredLocale() {
  try {
    const v = localStorage.getItem(STORAGE_KEY);
    if (v === 'zh' || v === 'en') return v;
  } catch (_) {}
  return 'zh';
}

const LocaleContext = createContext(null);

export function LocaleProvider({ children }) {
  const [locale, setLocaleState] = useState(getStoredLocale);

  useEffect(() => {
    document.documentElement.lang = locale === 'en' ? 'en' : 'zh-CN';
  }, [locale]);

  const setLocale = useCallback((next) => {
    const value = next === 'en' ? 'en' : 'zh';
    setLocaleState(value);
    try {
      localStorage.setItem(STORAGE_KEY, value);
    } catch (_) {}
  }, []);

  const t = useCallback(
    (key) => {
      const item = translations[key];
      if (!item) return key;
      return item[locale] ?? item.zh ?? key;
    },
    [locale]
  );

  const value = useMemo(() => ({ locale, setLocale, t }), [locale, setLocale, t]);

  return <LocaleContext.Provider value={value}>{children}</LocaleContext.Provider>;
}

export function useLocale() {
  const ctx = useContext(LocaleContext);
  if (!ctx) throw new Error('useLocale must be used within LocaleProvider');
  return ctx;
}

export function useTranslation() {
  const { t } = useLocale();
  return t;
}
