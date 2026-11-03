import { useId } from 'react';
import { PIECE_THEMES, usePieceTheme } from './PieceThemeContext.jsx';
import STUDIO_PIECES from './studioPieces.jsx';
import SIGNAL_PIECES from './signalPieces.jsx';
import whiteKing from '../assets/chess-pieces/white-king.png';
import './ThemeSwitcher.css';

const PREVIEW = {
  studio: STUDIO_PIECES.k,
  signal: SIGNAL_PIECES.k,
};

export default function ThemeSwitcher() {
  const { themeId, setTheme } = usePieceTheme();
  const labelId = useId();

  return (
    <div className="piece-theme-switch" role="group" aria-labelledby={labelId}>
      <span className="piece-theme-switch__label" id={labelId}>棋子样式</span>
      <div className="piece-theme-switch__buttons">
        {PIECE_THEMES.map((theme) => {
          const active = themeId === theme.id;
          const Preview = PREVIEW[theme.id];
          return (
            <button
              key={theme.id}
              type="button"
              className={`piece-theme-switch__btn${active ? ' is-active' : ''}`}
              aria-pressed={active}
              title={theme.hint}
              onClick={() => setTheme(theme.id)}
            >
              <span className="piece-theme-switch__preview" aria-hidden="true">
                {Preview ? (
                  <Preview color="white" className="piece-theme-switch__glyph" decorative />
                ) : (
                  <img src={whiteKing} alt="" className="piece-theme-switch__glyph" draggable={false} />
                )}
              </span>
              {theme.name}
            </button>
          );
        })}
      </div>
    </div>
  );
}
