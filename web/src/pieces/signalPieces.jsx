import { usePiecePaint, ink, PieceSvg, Ground, SignalPlinth, KNIGHT_D, ROOK_POINTS } from './piecePaint.jsx';

function SignalPawn({ color, className, label, decorative }) {
  const paint = usePiecePaint(color, 'signal');
  const s = ink(paint);
  return (
    <PieceSvg paint={paint} className={className} label={label} decorative={decorative}>
      <Ground paint={paint} />
      <polygon points="33,38 47,38 57,63 23,63" {...s} />
      <rect x="36" y="32" width="8" height="10" {...s} />
      <polygon points="40,11 50.5,17.5 50.5,29 40,35.5 29.5,29 29.5,17.5" {...s} />
      <polygon points="35,45 45,45 46.5,49.5 33.5,49.5" fill={paint.accent} />
      <SignalPlinth paint={paint} />
    </PieceSvg>
  );
}

function SignalRook({ color, className, label, decorative }) {
  const paint = usePiecePaint(color, 'signal');
  const s = ink(paint);
  return (
    <PieceSvg paint={paint} className={className} label={label} decorative={decorative}>
      <Ground paint={paint} />
      <polygon points={ROOK_POINTS} {...s} />
      <polygon points="30,38 50,38 50,42 30,42" fill={paint.accent} />
      <SignalPlinth paint={paint} />
    </PieceSvg>
  );
}

function SignalKnight({ color, className, label, decorative }) {
  const paint = usePiecePaint(color, 'signal');
  const s = ink(paint);
  return (
    <PieceSvg paint={paint} className={className} label={label} decorative={decorative}>
      <Ground paint={paint} />
      <path d={KNIGHT_D} {...s} />
      <rect x="28.8" y="27.6" width="4.4" height="4.4" fill={paint.eye} />
      <SignalPlinth paint={paint} />
    </PieceSvg>
  );
}

function SignalBishop({ color, className, label, decorative }) {
  const paint = usePiecePaint(color, 'signal');
  const s = ink(paint);
  return (
    <PieceSvg paint={paint} className={className} label={label} decorative={decorative}>
      <Ground paint={paint} />
      <polygon points="40,7 58,36 40,57 22,36" {...s} />
      <polygon points="30,51 50,51 56,63 24,63" {...s} />
      <polygon points="40,20 46,32 40,38 34,32" fill={paint.accent} />
      <SignalPlinth paint={paint} />
    </PieceSvg>
  );
}

function SignalQueen({ color, className, label, decorative }) {
  const paint = usePiecePaint(color, 'signal');
  const s = ink(paint);
  return (
    <PieceSvg paint={paint} className={className} label={label} decorative={decorative}>
      <Ground paint={paint} />
      <polygon points="22,40 58,40 62,63 18,63" {...s} />
      <rect x="24.4" y="23" width="5.2" height="19" {...s} />
      <rect x="37.4" y="15" width="5.2" height="27" {...s} />
      <rect x="50.4" y="23" width="5.2" height="19" {...s} />
      <polygon points="27,14 32.6,21 27,28 21.4,21" {...s} />
      <polygon points="40,4 46.4,13 40,22 33.6,13" {...s} />
      <polygon points="53,14 58.6,21 53,28 47.4,21" {...s} />
      <polygon points="32,47 48,47 49.2,51.5 30.8,51.5" fill={paint.accent} />
      <SignalPlinth paint={paint} />
    </PieceSvg>
  );
}

function SignalKing({ color, className, label, decorative }) {
  const paint = usePiecePaint(color, 'signal');
  const s = ink(paint);
  return (
    <PieceSvg paint={paint} className={className} label={label} decorative={decorative}>
      <Ground paint={paint} />
      <polygon points="20,36 60,36 64,63 16,63" {...s} />
      <rect x="35" y="28" width="10" height="12" {...s} />
      <path d="M34 4 H46 V12.5 H57 V24.5 H46 V33 H34 V24.5 H23 V12.5 H34 Z" {...s} />
      <polygon points="31,45 49,45 50.2,49.5 29.8,49.5" fill={paint.accent} />
      <SignalPlinth paint={paint} />
    </PieceSvg>
  );
}

const SIGNAL_PIECES = {
  p: SignalPawn,
  r: SignalRook,
  n: SignalKnight,
  b: SignalBishop,
  q: SignalQueen,
  k: SignalKing,
};

export default SIGNAL_PIECES;
