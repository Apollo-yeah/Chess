// utils/moveUtils.js
import { PROMOTION_NAMES, PIECE_RULES } from '../constants/chess_config.js';
import { toChessNotation } from './boardUtils.js';

// 分析走法无效原因
export const getInvalidMoveReason = (board, fromRow, fromCol, toRow, toCol, currentTurn) => {
  const piece = board[fromRow][fromCol];
  if (!piece) return '该位置无棋子，请选择有棋子的格子';

  const isWhitePiece = piece === piece.toUpperCase();
  const isCurrentTurnPiece = (currentTurn === 'white' && isWhitePiece) || (currentTurn === 'black' && !isWhitePiece);
  if (!isCurrentTurnPiece) {
    return `当前是${currentTurn === 'white' ? '白' : '黑'}棋回合，该棋子是${isWhitePiece ? '白' : '黑'}棋，无法移动`;
  }

  const targetPiece = board[toRow][toCol];
  if (targetPiece) {
    const targetIsWhite = targetPiece === targetPiece.toUpperCase();
    if ((isWhitePiece && targetIsWhite) || (!isWhitePiece && !targetIsWhite)) {
      return `目标位置有己方${targetIsWhite ? '白' : '黑'}棋（${targetPiece.toLowerCase() === 'p' ? '兵' : PROMOTION_NAMES[targetPiece] || '王'}），无法移动`;
    }
  }

  return `该走法违反${isWhitePiece ? '白' : '黑'}${piece.toLowerCase() === 'p' ? '兵' : PROMOTION_NAMES[piece] || '王'}的走法规则：${PIECE_RULES[piece]}`;
};

// 判断是否是升变走法（位置+棋子类型判断）
export const isPromotion = (fromRow, fromCol, toRow, toCol, board) => {
  const piece = board[fromRow][fromCol];
  if (!piece || piece.toLowerCase() !== 'p') return false; // 不是兵则不升变
  const isWhitePawn = piece === 'P';
  // 白兵走到第0行（8线）、黑兵走到第7行（1线）
  return (isWhitePawn && toRow === 0) || (!isWhitePawn && toRow === 7);
};

// 校验升变走法是否合法（兼容升变后缀）
export const isValidPromotionMove = (fromRow, fromCol, toRow, toCol, board, legalMoves) => {
  // 1. 先判断是否是升变位置
  if (!isPromotion(fromRow, fromCol, toRow, toCol, board)) return false;
  
  // 2. 校验走法是否合法（兼容升变后缀：如 e7e8q 以 e7e8 开头）
  const fromNotation = toChessNotation(fromRow, fromCol);
  const toNotation = toChessNotation(toRow, toCol);
  const baseMove = fromNotation + toNotation;
  
  // 检查 legalMoves 中是否有以 baseMove 开头的走法
  return legalMoves.some(move => move.startsWith(baseMove));
};

// 解析合法走棋位置（用于高亮可走位置）
export const parseLegalMovePositions = (selected, legalMoves, fromChessNotation) => {
  if (!selected) return [];
  const selectedNotation = toChessNotation(selected.row, selected.col);
  const filteredMoves = legalMoves.filter(move => move.startsWith(selectedNotation));
  return filteredMoves.map(move => {
    const toNotation = move.substring(2, 4);
    return fromChessNotation(toNotation);
  });
};

// 格式化走棋记录文本
export const formatMoveText = (moveInfo) => {
  const colorText = moveInfo.color === 'white' ? '白棋' : '黑棋';
  const typeText = moveInfo.type === 'ai' ? '(AI)' : '(玩家)';
  return `${moveInfo.move_number}. ${colorText} ${typeText}: ${moveInfo.move}`;
};