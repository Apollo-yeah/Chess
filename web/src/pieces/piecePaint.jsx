import { useId } from 'react';

/** 棋子配色。圆润主题用斜向渐变，几何主题用纯色平面。 */
export function usePiecePaint(color, variant) {
  const uid = useId().replace(/:/g, '');
  const white = color === 'white';

  if (variant === 'signal') {
    return {
      variant,
      white,
      fill: white ? '#F6F7FB' : '#151922',
      stroke: white ? '#151922' : '#F6F7FB',
      accent: white ? '#3D7EFF' : '#FF7A59',
      eye: white ? '#151922' : '#F6F7FB',
      gloss: 'transparent',
      shadow: 'rgba(8, 12, 22, 0.2)',
      sw: 2.4,
      join: 'miter',
      defs: null,
    };
  }

  return {
    variant,
    white,
    fill: `url(#${uid}-fill)`,
    stroke: white ? '#1B2433' : '#F7F8FA',
    accent: white ? '#14B8A6' : '#F5C451',
    eye: white ? '#1B2433' : '#F7F8FA',
    gloss: white ? 'rgba(255,255,255,0.72)' : 'rgba(255,255,255,0.22)',
    shadow: 'rgba(8, 12, 22, 0.28)',
    sw: 2.4,
    join: 'round',
    defs: (
      <defs>
        <linearGradient id={`${uid}-fill`} x1="16" y1="4" x2="64" y2="76" gradientUnits="userSpaceOnUse">
          <stop offset="0%" stopColor={white ? '#FFFFFF' : '#4A5470'} />
          <stop offset="46%" stopColor={white ? '#E8EEF6' : '#262C3D'} />
          <stop offset="100%" stopColor={white ? '#C9D4E2' : '#10131B'} />
        </linearGradient>
      </defs>
    ),
  };
}

export function ink(paint) {
  return {
    fill: paint.fill,
    stroke: paint.stroke,
    strokeWidth: paint.sw,
    strokeLinejoin: paint.join,
    strokeLinecap: paint.join === 'round' ? 'round' : 'butt',
  };
}

export function PieceSvg({ paint, className, label, decorative = false, children }) {
  return (
    <svg
      viewBox="0 0 80 80"
      className={className}
      role={decorative ? 'presentation' : 'img'}
      aria-hidden={decorative ? true : undefined}
      aria-label={decorative ? undefined : label}
      shapeRendering={paint.join === 'miter' ? 'geometricPrecision' : 'auto'}
    >
      {label && !decorative ? <title>{label}</title> : null}
      {paint.defs}
      {children}
    </svg>
  );
}

export function Ground({ paint }) {
  return <ellipse cx="40" cy="71.2" rx="18" ry="3" fill={paint.shadow} />;
}

export function StudioPlinth({ paint }) {
  return (
    <path
      d="M24 62.2h32c1.7 0 2.8 1.1 2.8 2.3 0 2.8-7.8 5-18.8 5s-18.8-2.2-18.8-5c0-1.2 1.1-2.3 2.8-2.3z"
      {...ink(paint)}
    />
  );
}

export function SignalPlinth({ paint }) {
  return <polygon points="15,62 65,62 69,71 11,71" {...ink(paint)} />;
}

/** 车：城楼连成一体，齿间留出足够空隙，避免描边把垛口糊住。 */
export const ROOK_POINTS = '22,64 58,64 58,11 52,11 52,28 43,28 43,11 37,11 37,28 28,28 28,11 22,11';

/** 马头朝左，耳朵有一定宽度，底部落到底座里。 */
export const KNIGHT_D = 'M16 40 L22 33 L30 25 L36 22 L48 4 L41 18 L54 22 L61 33 L63 47 L55 64 L25 64 L19 51 L31 43 L17 41 Z';
