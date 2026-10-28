import axios from 'axios';
import { API_BASE_URL } from '../constants/backend_config.js';

const client = axios.create({
  baseURL: API_BASE_URL,
  timeout: 30000,
  headers: { 'Content-Type': 'application/json' },
});

/** 把后端 {success:false, error} 与网络异常统一成带可读 message 的 Error */
function toError(err) {
  if (err.response) {
    const payload = err.response.data;
    const message =
      (payload && typeof payload === 'object' && payload.error) ||
      `${err.response.status} ${err.response.statusText}`;
    const wrapped = new Error(message);
    wrapped.status = err.response.status;
    wrapped.payload = payload;
    return wrapped;
  }
  if (err.code === 'ECONNABORTED') return new Error('请求超时，请稍后重试');
  return new Error(`无法连接后端服务：${err.message}`);
}

async function request(method, url, data, config = {}) {
  try {
    const response = await client.request({ method, url, data, ...config });
    return response.data;
  } catch (err) {
    throw toError(err);
  }
}

// --- 对局 ---
export const fetchHistory = () => request('get', '/api/games');
export const fetchCurrentGame = () => request('get', '/api/games/current');
export const createGame = (payload = {}) => request('post', '/api/games', payload);
export const fetchGameState = (gameId) => request('get', `/api/games/${gameId}`);
export const makeMoveToServer = (gameId, move) =>
  request('post', `/api/games/${gameId}/move`, { move });
export const requestAIMoveToServer = (gameId, aiLevel) =>
  request('post', `/api/games/${gameId}/ai`, { ai_level: aiLevel });
export const undoMoveToServer = (gameId, plies = 1) =>
  request('post', `/api/games/${gameId}/undo`, { plies });
export const setGameModeToServer = (gameId, mode, playerColor, aiLevel) =>
  request('post', `/api/games/${gameId}/mode`, {
    mode,
    player_color: playerColor,
    ai_level: aiLevel,
  });
/** 重置：可同时切换模式/执子颜色（一次调用完成归档旧局 + 开新局） */
export const resetGameToServer = (gameId, options = {}) =>
  request('post', `/api/games/${gameId}/reset`, options);
export const fetchAnalysis = (gameId, depth) =>
  request('get', `/api/games/${gameId}/analysis`, undefined, {
    params: depth ? { depth } : undefined,
  });

// --- 长棋谱分析任务 ---
export const submitPgnAnalysis = (pgnText, depth) =>
  request('post', '/api/analysis/jobs', { pgn_text: pgnText, depth });
export const fetchAnalysisJob = (jobId) => request('get', `/api/analysis/jobs/${jobId}`);
export const cancelAnalysisJob = (jobId) => request('delete', `/api/analysis/jobs/${jobId}`);

// --- 运维 ---
export const fetchHealth = () => request('get', '/api/health');
export const fetchServerStatus = () => request('get', '/api/status');
