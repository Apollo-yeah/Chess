/**
 * 当前服务的共享对局。
 *
 * 进入这个进程的每个客户端都加入同一局，可以一起看、一起走棋。
 * 本地仍记下 game_id，只为让同一浏览器里的其它板块显示一致；
 * 真正以哪一局为准，由服务端的「当前对局」决定。
 */
import { fetchCurrentGame } from './apiUtils.js';

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

/** 取得本进程正在进行的那一局；还没有时由服务端创建。 */
export async function ensureSessionGame() {
  const state = await fetchCurrentGame();
  saveGameId(state.game_id);
  return state;
}
