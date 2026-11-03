import { createContext, useContext, useMemo, useState } from 'react';

const STORAGE_KEY = 'z-chess-piece-theme';

export const PIECE_THEMES = [
  { id: 'studio', name: '圆润', hint: '柔和渐变的现代棋子' },
  { id: 'signal', name: '几何', hint: '扁平棱角的现代棋子' },
  { id: 'classic', name: '经典', hint: '原来的传统棋子' },
];

const PieceThemeContext = createContext(null);

function readStoredTheme() {
  try {
    const saved = localStorage.getItem(STORAGE_KEY);
    return PIECE_THEMES.some((theme) => theme.id === saved) ? saved : 'studio';
  } catch {
    return 'studio';
  }
}

export function PieceThemeProvider({ children }) {
  const [themeId, setThemeId] = useState(readStoredTheme);

  const setTheme = (id) => {
    if (!PIECE_THEMES.some((theme) => theme.id === id)) return;
    setThemeId(id);
    try {
      localStorage.setItem(STORAGE_KEY, id);
    } catch {
      /* 无存储权限时只保留当前会话 */
    }
  };

  const value = useMemo(() => ({ themeId, setTheme }), [themeId]);

  return <PieceThemeContext.Provider value={value}>{children}</PieceThemeContext.Provider>;
}

export function usePieceTheme() {
  const value = useContext(PieceThemeContext);
  if (!value) {
    throw new Error('usePieceTheme 必须在 PieceThemeProvider 内使用');
  }
  return value;
}
