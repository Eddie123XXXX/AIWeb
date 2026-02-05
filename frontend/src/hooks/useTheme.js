import { useCallback, useEffect, useState } from 'react';

const THEME_KEY = 'app-theme';
const THEME_LIGHT = 'light';
const THEME_DARK = 'dark';

function getStoredTheme() {
  try {
    return localStorage.getItem(THEME_KEY) || THEME_LIGHT;
  } catch {
    return THEME_LIGHT;
  }
}

function setStoredTheme(theme) {
  try {
    localStorage.setItem(THEME_KEY, theme);
  } catch (_) {}
}

function applyThemeToDocument(theme) {
  document.documentElement.setAttribute('data-theme', theme);
  setStoredTheme(theme);
}

export function useTheme() {
  const [theme, setThemeState] = useState(() => getStoredTheme());

  useEffect(() => {
    applyThemeToDocument(theme);
  }, [theme]);

  const toggleTheme = useCallback(() => {
    setThemeState((prev) => (prev === THEME_LIGHT ? THEME_DARK : THEME_LIGHT));
  }, []);

  return { theme, isDark: theme === THEME_DARK, toggleTheme };
}
