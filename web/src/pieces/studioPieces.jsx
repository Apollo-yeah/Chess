import { usePiecePaint, ink, PieceSvg, Ground, StudioPlinth, KNIGHT_D, ROOK_POINTS } from './piecePaint.jsx';

function StudioPawn({ color, className, label, decorative }) {
  const paint = usePiecePaint(color, 'studio');
  const s = ink(paint);
  return (
    <PieceSvg paint={paint} className={className} label={label} decorative={decorative}>
      <Ground paint={paint} />
      <path d="M32 40 C27 49 22.5 56 22.5 64 H57.5 C57.5 56 53 49 48 40 C44 45 36 45 32 40 Z" {...s} />
      <rect x="32" y="33" width="16" height="8" rx="4" fill={paint.accent} />
      <circle cx="40" cy="23.5" r="11.2" {...s} />
      <ellipse cx="35.2" cy="19.4" rx="4.2" ry="2.8" fill={paint.gloss} />
      <StudioPlinth paint={paint} />
    </PieceSvg>
  );
}

function StudioRook({ color, className, label, decorative }) {
  const paint = usePiecePaint(color, 'studio');
  const s = ink(paint);
  return (
    <PieceSvg paint={paint} className={className} label={label} decorative={decorative}>
      <Ground paint={paint} />
      <polygon points={ROOK_POINTS} {...s} strokeLinejoin="miter" strokeMiterlimit="2" />
      <rect x="30" y="38" width="20" height="3.4" rx="1.7" fill={paint.accent} />
      <StudioPlinth paint={paint} />
    </PieceSvg>
  );
}

function StudioKnight({ color, className, label, decorative }) {
  const paint = usePiecePaint(color, 'studio');
  const s = ink(paint);
  return (
    <PieceSvg paint={paint} className={className} label={label} decorative={decorative}>
      <Ground paint={paint} />
      <path d={KNIGHT_D} {...s} />
      <circle cx="31" cy="30" r="2.2" fill={paint.eye} />
      <StudioPlinth paint={paint} />
    </PieceSvg>
  );
}

function StudioBishop({ color, className, label, decorative }) {
  const paint = usePiecePaint(color, 'studio');
  const s = ink(paint);
  return (
    <PieceSvg paint={paint} className={className} label={label} decorative={decorative}>
      <Ground paint={paint} />
      <path d="M31 52 H49 L53 64 H27 Z" {...s} />
      <path d="M40 6 C50 16 58 28 55 40 C52 50 46 55 40 56 C34 55 28 50 25 40 C22 28 30 16 40 6 Z" {...s} />
      <path d="M46 18 L32 42" stroke={paint.stroke} strokeWidth="4" strokeLinecap="round" fill="none" />
      <StudioPlinth paint={paint} />
    </PieceSvg>
  );
}

function StudioQueen({ color, className, label, decorative }) {
  const paint = usePiecePaint(color, 'studio');
  const s = ink(paint);
  return (
    <PieceSvg paint={paint} className={className} label={label} decorative={decorative}>
      <Ground paint={paint} />
      <path d="M25 40 H55 C58 40 61 44 59 51 L55 64 H25 L21 51 C19 44 22 40 25 40 Z" {...s} />
      <rect x="24.6" y="22" width="5.2" height="20" rx="2.6" {...s} />
      <rect x="37.2" y="14" width="5.6" height="28" rx="2.8" {...s} />
      <rect x="50.2" y="22" width="5.2" height="20" rx="2.6" {...s} />
      <circle cx="27.2" cy="21.5" r="4.6" {...s} />
      <circle cx="52.8" cy="21.5" r="4.6" {...s} />
      <circle cx="40" cy="13.2" r="5.3" {...s} />
      <circle cx="40" cy="13.2" r="2.15" fill={paint.accent} />
      <rect x="30" y="48" width="20" height="3.6" rx="1.8" fill={paint.accent} />
      <StudioPlinth paint={paint} />
    </PieceSvg>
  );
}

function StudioKing({ color, className, label, decorative }) {
  const paint = usePiecePaint(color, 'studio');
  const s = ink(paint);
  return (
    <PieceSvg paint={paint} className={className} label={label} decorative={decorative}>
      <Ground paint={paint} />
      <path d="M26 35 H54 C58 35 61 39 60 45 L56 64 H24 L20 45 C19 39 22 35 26 35 Z" {...s} />
      <rect x="35.2" y="28" width="9.6" height="12" rx="2.4" {...s} />
      <path d="M34.5 4.5 H45.5 V12.5 H56 V23.5 H45.5 V31.5 H34.5 V23.5 H24 V12.5 H34.5 Z" {...s} />
      <rect x="30" y="46" width="20" height="3.8" rx="1.9" fill={paint.accent} />
      <StudioPlinth paint={paint} />
    </PieceSvg>
  );
}

const STUDIO_PIECES = {
  p: StudioPawn,
  r: StudioRook,
  n: StudioKnight,
  b: StudioBishop,
  q: StudioQueen,
  k: StudioKing,
};

export default STUDIO_PIECES;
