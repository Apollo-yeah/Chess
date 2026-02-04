// src/constants/chess_config.js

// 导入棋子图片（如果用Vite/Webpack，也可以用 require.context 批量导入）
import whitePawn from '../assets/chess-pieces/white-pawn.png';
import whiteRook from '../assets/chess-pieces/white-rook.png';
import whiteKnight from '../assets/chess-pieces/white-knight.png';
import whiteBishop from '../assets/chess-pieces/white-bishop.png';
import whiteQueen from '../assets/chess-pieces/white-queen.png';
import whiteKing from '../assets/chess-pieces/white-king.png';

import blackPawn from '../assets/chess-pieces/black-pawn.png';
import blackRook from '../assets/chess-pieces/black-rook.png';
import blackKnight from '../assets/chess-pieces/black-knight.png';
import blackBishop from '../assets/chess-pieces/black-bishop.png';
import blackQueen from '../assets/chess-pieces/black-queen.png';
import blackKing from '../assets/chess-pieces/black-king.png';

// 1. 棋子符号→图片映射（FEN：小写=黑棋，大写=白棋）
export const PIECE_IMAGES = {
  'p': blackPawn,    'r': blackRook,    'n': blackKnight,  'b': blackBishop,  'q': blackQueen,   'k': blackKing,
  'P': whitePawn,    'R': whiteRook,    'N': whiteKnight,  'B': whiteBishop,  'Q': whiteQueen,   'K': whiteKing
};

// 2. 升变可选棋子（排除王）
export const PROMOTION_OPTIONS = {
  white: ['Q', 'R', 'N', 'B'],
  black: ['q', 'r', 'n', 'b']
};

// 3. 棋子名称映射（用于显示）
export const PROMOTION_NAMES = {
  'Q': '后', 'R': '车', 'N': '马', 'B': '象',
  'q': '后', 'r': '车', 'n': '马', 'b': '象'
};

// 4. 棋子走法规则（用于提示无效原因）
export const PIECE_RULES = {
  'p': '黑兵只能向前走，第一步可走1-2格，后续只能走1格，吃子斜向走',
  'P': '白兵只能向前走，第一步可走1-2格，后续只能走1格，吃子斜向走',
  'r': '黑车可横竖走任意格，不能斜走，不能跳过其他棋子',
  'R': '白车可横竖走任意格，不能斜走，不能跳过其他棋子',
  'n': '黑马走"日"字，可跳过其他棋子',
  'N': '白马走"日"字，可跳过其他棋子',
  'b': '黑象只能斜走任意格，不能跳过其他棋子',
  'B': '白象只能斜走任意格，不能跳过其他棋子',
  'q': '黑后可横竖斜走任意格，不能跳过其他棋子',
  'Q': '白后可横竖斜走任意格，不能跳过其他棋子',
  'k': '黑王每次只能走1格，不能进入被攻击的位置',
  'K': '白王每次只能走1格，不能进入被攻击的位置'
};

// 可选：补充更多通用常量（比如初始FEN、坐标映射）
export const INITIAL_FEN = 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1';
export const COL_LABELS = ['a', 'b', 'c', 'd', 'e', 'f', 'g', 'h'];
export const ROW_LABELS = ['8', '7', '6', '5', '4', '3', '2', '1'];