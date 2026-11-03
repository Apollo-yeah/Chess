import { PIECE_IMAGES } from '../constants/chess_config.js';
import { usePieceTheme } from './PieceThemeContext.jsx';
import STUDIO_PIECES from './studioPieces.jsx';
import SIGNAL_PIECES from './signalPieces.jsx';

const PIECE_SETS = {
  studio: STUDIO_PIECES,
  signal: SIGNAL_PIECES,
};

const PIECE_LABELS = {
  K: '白王', Q: '白后', R: '白车', B: '白象', N: '白马', P: '白兵',
  k: '黑王', q: '黑后', r: '黑车', b: '黑象', n: '黑马', p: '黑兵',
};

export default function PieceView({ piece, className = 'piece-image' }) {
  const { themeId } = usePieceTheme();
  if (!piece) return null;

  const label = PIECE_LABELS[piece] || piece;
  if (themeId === 'classic') {
    return (
      <img
        src={PIECE_IMAGES[piece]}
        alt={label}
        title={label}
        className={className}
        draggable={false}
      />
    );
  }

  const Comp = PIECE_SETS[themeId]?.[piece.toLowerCase()];
  if (!Comp) return null;
  const color = piece === piece.toUpperCase() ? 'white' : 'black';
  return <Comp color={color} className={className} label={label} />;
}
