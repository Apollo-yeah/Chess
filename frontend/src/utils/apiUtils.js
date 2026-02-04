import axios from 'axios';
import { API_BASE_URL } from '../constants/backend_config.js';

// 获取棋盘状态
export const fetchBoardState = async () => {
  try {
    const res = await axios.get(`${API_BASE_URL}/api/board`);
    return res.data;
  } catch (err) {
    throw new Error('连接后端失败：' + err.message);
  }
};

// 设置游戏模式
export const setGameModeToServer = async (gameMode, playerColor, aiLevel) => {
  try {
    const res = await axios.post(`${API_BASE_URL}/api/set_mode`, {
      mode: gameMode,
      player_color: playerColor,
      ai_level: aiLevel
    });
    return res.data;
  } catch (err) {
    throw new Error('设置游戏模式失败：' + err.message);
  }
};

// 执行走棋
export const makeMoveToServer = async (move) => {
  try {
    const res = await axios.post(`${API_BASE_URL}/api/move`, { move });
    return res.data;
  } catch (err) {
    throw new Error('走棋失败：' + err.message);
  }
};

// 请求AI走棋
export const requestAIMoveToServer = async (aiLevel) => {
  try {
    const res = await axios.post(`${API_BASE_URL}/api/ai`, { ai_level: aiLevel });
    return res.data;
  } catch (err) {
    throw new Error('AI走棋失败：' + err.message);
  }
};

// 重置游戏
export const resetGameToServer = async () => {
  try {
    const res = await axios.post(`${API_BASE_URL}/api/reset`);
    return res.data;
  } catch (err) {
    throw new Error('重置游戏失败：' + err.message);
  }
};

// 悔棋（单步）
export const undoMoveToServer = async () => {
  try {
    const res = await axios.post(`${API_BASE_URL}/api/undo`);
    return res.data;
  } catch (err) {
    throw new Error('悔棋失败：' + err.message);
  }
};