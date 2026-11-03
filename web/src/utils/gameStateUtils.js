/** 解析对局终局状态（兼容 is_checkmate 标志与 game_result 回退） */
export function resolveGameEndState(data) {
  const noLegalMoves = !data.legal_moves || data.legal_moves.length === 0;

  const isCheckmate =
    Boolean(data.is_checkmate) ||
    data.game_result === 'white_win' ||
    data.game_result === 'black_win' ||
    (noLegalMoves && Boolean(data.is_check));

  const isStalemate =
    Boolean(data.is_stalemate) ||
    data.game_result === 'draw' ||
    (noLegalMoves && !data.is_check && !isCheckmate);

  const isCheck = Boolean(data.is_check) && !isCheckmate;

  return { isCheckmate, isStalemate, isCheck };
}

/** 根据回合方或 game_result 推断获胜方 */
export function getWinnerLabel(turn, gameResult) {
  if (gameResult === 'white_win') return '白棋';
  if (gameResult === 'black_win') return '黑棋';
  return turn === 'white' ? '黑棋' : '白棋';
}
