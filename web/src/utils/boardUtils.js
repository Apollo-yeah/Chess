// 棋盘解析、坐标转换等基础工具函数
import { INITIAL_FEN, COL_LABELS, ROW_LABELS } from '../constants/chess_config.js';

// FEN解析
export const parseFEN = (fen) => {
  const [position] = fen.split(' ');
  const rows = position.split('/');
  const board = [];
  rows.forEach(row => {
    const rowArr = [];
    for (let char of row) {
      if (!isNaN(char)) {
        for (let i = 0; i < parseInt(char); i++) rowArr.push('');
      } else {
        rowArr.push(char);
      }
    }
    board.push(rowArr);
  });
  return board;
};

// 坐标转换：行列 → 象棋记谱法（如 a1, h8）
export const toChessNotation = (row, col) => {
  return COL_LABELS[col] + ROW_LABELS[row];
};

// 反向坐标转换：象棋记谱法 → 行列
export const fromChessNotation = (notation) => {
  const col = COL_LABELS.indexOf(notation[0]);
  const row = ROW_LABELS.indexOf(notation[1]);
  return { row, col };
};

// 本地更新棋盘（深拷贝避免直接修改状态）
export const updateBoardLocally = (board, fromRow, fromCol, toRow, toCol, promotionPiece = null) => {
  const newBoard = JSON.parse(JSON.stringify(board));
  const piece = newBoard[fromRow][fromCol];
  newBoard[fromRow][fromCol] = '';
  newBoard[toRow][toCol] = promotionPiece || piece;
  return newBoard;
};

// 初始化棋盘
export const initBoard = () => parseFEN(INITIAL_FEN);