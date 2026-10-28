/**
 * 对局会话：把 game_id 存在浏览器本地，实现「刷新页面仍是同一局」。
 *
 * 每个浏览器各自持有一个 game_id，对应后端注册表里独立的一局棋，
 * 因此多人同时访问互不干扰。
 */
import { createGame, fetchGameState } from './apiUtils.js';

const STORAGE_KEY = 'zchess.game_id';

export function loadGameId() {
  try {
    return localStorage.getItem(STORAGE_KEY) || '';
  } catch {
    return '';
  }
}

export function saveGameId(gameId) {
  try {
    if (gameId) localStorage.setItem(STORAGE_KEY, gameId);
  } catch {
    /* 隐私模式下 localStorage 可能不可用，忽略 */
  }
}

export function clearGameId() {
  try {
    localStorage.removeItem(STORAGE_KEY);
  } catch {
    /* 同上 */
  }
}

/**
 * 取得当前会话的对局：本地有且服务端仍存在则复用，否则新建一局。
 * @param {{mode?: string, player_color?: string, ai_level?: string}} defaults 新建时使用的初始配置
 */
export async function ensureSessionGame(defaults = {}) {
  const existing = loadGameId();
  if (existing) {
    try {
      const state = await fetchGameState(existing);
      saveGameId(state.game_id || existing);
      return state;
    } catch {
      clearGameId();
    }
  }
  const state = await createGame(defaults);
  saveGameId(state.game_id);
  return state;
}
