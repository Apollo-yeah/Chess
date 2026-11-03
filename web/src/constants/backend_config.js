/**
 * 后端地址配置。
 *
 * 默认走**同源**：生产由 Nginx 反代 /api 与 /ws 到 API 服务；
 * 开发由 Vite dev server 代理（见 vite.config.js 的 proxy）承担同样职责。
 * 仅当前后端分域名部署时才需要设置 VITE_API_BASE_URL。
 */
const stripTrailingSlash = (value) => (value || '').replace(/\/+$/, '');

export const API_BASE_URL = stripTrailingSlash(import.meta.env.VITE_API_BASE_URL || '');

/** 构造 WebSocket 地址：可携带要订阅的 game_id */
export function buildWsUrl(gameId) {
  const base =
    API_BASE_URL ||
    (typeof window !== 'undefined' && window.location
      ? window.location.origin
      : 'http://localhost:8156');
  const url = new URL('/ws/game', base);
  url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:';
  if (gameId) url.searchParams.set('game_id', gameId);
  return url.toString();
}
