import { useState, useEffect, useRef, useCallback } from 'react';
import './Game.css';
import MoveHistoryWidget from './MoveHistoryWidget.jsx';

// 导入常量
import { PROMOTION_OPTIONS, PROMOTION_NAMES } from '../constants/chess_config.js';
import PieceView from '../pieces/PieceView.jsx';
import ThemeSwitcher from '../pieces/ThemeSwitcher.jsx';

// 导入工具函数
import { parseFEN, toChessNotation, fromChessNotation, updateBoardLocally, initBoard } from '../utils/boardUtils.js';
import { getInvalidMoveReason, isPromotion, isValidPromotionMove, parseLegalMovePositions } from '../utils/moveUtils.js';
import {
  fetchGameState,
  makeMoveToServer,
  requestAIMoveToServer,
  resetGameToServer,
  setGameModeToServer,
  undoMoveToServer,
} from '../utils/apiUtils.js';
import { ensureSessionGame, loadGameId, saveGameId, clearGameId } from '../utils/gameSession.js';
import { useLiveGame } from '../utils/useLiveGame.js';
import { resolveGameEndState, getWinnerLabel } from '../utils/gameStateUtils.js';
import ChessBoard from '../component/ChessBox.jsx';

function Game() {
  const [board, setBoard] = useState(initBoard());
  const [selected, setSelected] = useState(null);
  const [legalMoves, setLegalMoves] = useState([]);
  const [currentTurn, setCurrentTurn] = useState('white');
  const [gameId, setGameId] = useState(loadGameId());
  const [synced, setSynced] = useState(false);
  const [gameInfo, setGameInfo] = useState({});
  const [statistics, setStatistics] = useState({});
  const [loading, setLoading] = useState(false);
  const [booting, setBooting] = useState(true);
  const [showPromotion, setShowPromotion] = useState(false);
  const [promotionData, setPromotionData] = useState({});
  const [hint, setHint] = useState({ show: false, text: '', type: 'info' });
  const [gameAlert, setGameAlert] = useState({ type: '', text: '' });
  const [gameStatus, setGameStatus] = useState('正在初始化对局…');
  const [moveHistory, setMoveHistory] = useState([]);
  const [lastMove, setLastMove] = useState({ from: null, to: null });
  const [legalMovePositions, setLegalMovePositions] = useState([]);
  const [flipBoard, setFlipBoard] = useState(false);
  /** 终局标志：由服务端 board_state 计算，避免用局部字段猜测局面 */
  const [endState, setEndState] = useState({ isCheckmate: false, isStalemate: false, isCheck: false, over: false });

  // 防止 AI 走棋被重复触发（例如 effect 重入 + 手动按钮同时点击）
  const aiThinkingRef = useRef(false);
  const gameIdRef = useRef(gameId);
  gameIdRef.current = gameId;
  /** 丢掉比界面更旧的快照，避免其它客户端的推送把棋盘打回去 */
  const seenRef = useRef({ id: '', version: -1 });
  const gameMode = gameInfo.mode || '';
  const playerColor = gameInfo.player_color || '';
  const aiLevel = gameInfo.ai_level || 'normal';
  const aiLevelRef = useRef(aiLevel);
  aiLevelRef.current = aiLevel;

  const showHint = useCallback((text, type = 'info') => {
    setHint({ show: true, text, type });
  }, []);

  /** 把后端返回的完整快照落到界面状态。更旧的版本直接丢掉。 */
  const applySnapshot = useCallback((data) => {
    if (!data || !data.board_state) return;
    const boardState = data.board_state;
    const history = data.move_history || [];
    const info = data.game_info || {};
    const incomingId = info.game_id || '';
    const incomingVersion = Number(info.version ?? 0);
    const seen = seenRef.current;
    if (incomingId && incomingId === seen.id && incomingVersion < seen.version) return;
    const changed = !incomingId || incomingId !== seen.id || incomingVersion !== seen.version;
    if (incomingId) {
      seenRef.current = { id: incomingId, version: incomingVersion };
      gameIdRef.current = incomingId;
    }
    const turn = boardState.turn || 'white';

    setBoard(parseFEN(boardState.fen));
    setLegalMoves(boardState.legal_moves || []);
    setCurrentTurn(turn);
    setMoveHistory(history);
    setGameInfo(info);
    setStatistics(data.statistics || {});
    if (info.game_id) {
      setGameId(info.game_id);
      saveGameId(info.game_id);
    }

    const { isCheckmate, isStalemate, isCheck } = resolveGameEndState(boardState);
    setEndState({
      isCheckmate,
      isStalemate,
      isCheck,
      over: Boolean(boardState.is_game_over) || isCheckmate || isStalemate,
    });
    const modeLabel = info.mode === 'ai' ? '人机对战' : info.mode === 'self' ? '自我博弈' : '未选择模式';
    const sideLabel = turn === 'white' ? '白棋' : '黑棋';

    if (isCheckmate) {
      const winner = getWinnerLabel(turn, boardState.game_result);
      setGameAlert({ type: 'checkmate', text: `将死！${winner} 获胜` });
      setGameStatus(`【${modeLabel}】对局结束，${winner} 获胜！`);
    } else if (isStalemate) {
      setGameAlert({ type: '', text: '' });
      setGameStatus(`【${modeLabel}】和棋！`);
    } else if (isCheck) {
      setGameAlert({ type: 'check', text: '将军！请立即应将' });
      setGameStatus(`【${modeLabel}】当前回合：${sideLabel}`);
    } else {
      setGameAlert({ type: '', text: '' });
      if (info.mode === 'ai') {
        const humanLabel = info.player_color === 'white' ? '白' : '黑';
        const whose = turn === info.player_color ? '（你的回合）' : '（AI 回合）';
        setGameStatus(`【人机对战-你执${humanLabel}棋】当前回合：${sideLabel} ${whose}`);
      } else if (info.mode === 'self') {
        setGameStatus(`【自我博弈】当前回合：${sideLabel} | 请点击对应颜色棋子走棋`);
      } else {
        setGameStatus('请选择对局模式开始');
      }
    }

    // 高亮最后一着：优先用服务端给出的 last_move
    const recent = boardState.last_move;
    if (recent && recent.from && recent.to) {
      setLastMove({
        from: fromChessNotation(recent.from),
        to: fromChessNotation(recent.to),
      });
    } else if (history.length > 0) {
      const uci = history[history.length - 1].move || '';
      setLastMove({ from: fromChessNotation(uci.substring(0, 2)), to: fromChessNotation(uci.substring(2, 4)) });
    } else {
      setLastMove({ from: null, to: null });
    }

    setSelected(null);
    setLegalMovePositions([]);
    if (changed) {
      setShowPromotion(false);
      setPromotionData({});
    }
  }, []);

  /** 走棋回包如果还停在旧局，而实时通道已经切到新局，就不要把界面拉回去。 */
  const applyIfCurrent = useCallback((requestedId, data) => {
    const returned = data?.game_info?.game_id || '';
    if (returned && returned === requestedId && gameIdRef.current !== requestedId) return;
    applySnapshot(data);
  }, [applySnapshot]);

  useLiveGame(applySnapshot, setSynced);

  /** 启动：加入本进程正在进行的那一局 */
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const state = await ensureSessionGame();
        if (!cancelled) applySnapshot(state);
      } catch (err) {
        if (!cancelled) {
          setGameStatus('无法连接后端服务，请确认 API 已启动');
          showHint(err.message, 'error');
        }
      } finally {
        if (!cancelled) setBooting(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [applySnapshot, showHint]);

  const reloadState = useCallback(
    async (id = gameIdRef.current) => {
      if (!id) return null;
      try {
        const data = await fetchGameState(id);
        applySnapshot(data);
        return data;
      } catch (err) {
        if (err.status === 404) {
          // 这局已经不在了：回到服务端当前正在进行的那一局
          clearGameId();
          const fresh = await ensureSessionGame();
          applySnapshot(fresh);
          return fresh;
        }
        throw err;
      }
    },
    [applySnapshot],
  );

  // --- 模式切换：重置并带上新的模式 ---
  const switchMode = useCallback(
    async (mode, color = '') => {
      const id = gameIdRef.current;
      if (!id) return;
      setLoading(true);
      try {
        const data = await resetGameToServer(id, mode ? { mode, player_color: color } : {});
        applyIfCurrent(id, data);
        if (mode === 'ai') {
          showHint(`已开始人机对战（你执${color === 'white' ? '白' : '黑'}棋）`, 'info');
        } else if (mode === 'self') {
          showHint('已开始自我博弈', 'info');
        } else {
          showHint('对局已重置', 'info');
        }
      } catch (err) {
        showHint(err.message, 'error');
      } finally {
        setLoading(false);
      }
    },
    [applyIfCurrent, showHint],
  );

  const selectAILevel = useCallback(
    async (level) => {
      const id = gameIdRef.current;
      if (gameMode !== 'ai' || !id) return;
      try {
        // 只切等级，不重置对局
        const data = await setGameModeToServer(id, 'ai', playerColor, level);
        applyIfCurrent(id, data);
        showHint(`已切换为${level === 'normal' ? '普通' : '高级'} AI`, 'info');
      } catch (err) {
        showHint(err.message, 'error');
      }
    },
    [gameMode, playerColor, applyIfCurrent, showHint],
  );

  const handlePromotionSelect = (pieceType) => {
    const { from, to } = promotionData;
    const move = toChessNotation(from.row, from.col) + toChessNotation(to.row, to.col) + pieceType.toLowerCase();
    setShowPromotion(false);
    setPromotionData({});
    submitMove(move, `兵升变为${PROMOTION_NAMES[pieceType]}`);
  };

  /** 统一的落子提交：乐观更新 + 失败回滚 */
  const submitMove = useCallback(
    async (move, successText = '走棋成功') => {
      const rollback = board.map((row) => [...row]);
      const id = gameIdRef.current;
      if (!id) return;
      try {
        const data = await makeMoveToServer(id, move);
        applyIfCurrent(id, data);
        const { isCheckmate } = resolveGameEndState(data.board_state || {});
        showHint(isCheckmate ? '将死！对局结束' : successText, isCheckmate ? 'warning' : 'info');
      } catch (err) {
        setBoard(rollback);
        setSelected(null);
        setLegalMovePositions([]);
        showHint(err.message, 'error');
        // 服务端可能已推进（例如本地状态过期），重新对齐一次
        reloadState().catch(() => {});
      }
    },
    [board, applyIfCurrent, showHint, reloadState],
  );

  // 处理棋盘格子点击
  const handleSquareClick = (row, col) => {
    if (booting || loading || !gameMode || endState.over || showPromotion) return;

    const piece = board[row][col];

    // 1. 未选中任何棋子：选中目标棋子
    if (!selected) {
      if (!piece) {
        showHint('该位置无棋子，请选择有棋子的格子', 'info');
        return;
      }
      const isWhitePiece = piece === piece.toUpperCase();
      if (gameMode === 'ai') {
        const isMyPiece = (playerColor === 'white' && isWhitePiece) || (playerColor === 'black' && !isWhitePiece);
        if (!isMyPiece) {
          showHint(`你执${playerColor === 'white' ? '白' : '黑'}棋，该棋子是${isWhitePiece ? '白' : '黑'}棋，无法选择`, 'warning');
          return;
        }
        if (currentTurn !== playerColor) {
          showHint(`当前是${currentTurn === 'white' ? '白' : '黑'}棋回合（AI 回合），请等待 AI 走棋`, 'warning');
          return;
        }
      } else {
        const isCurrentTurnPiece =
          (currentTurn === 'white' && isWhitePiece) || (currentTurn === 'black' && !isWhitePiece);
        if (!isCurrentTurnPiece) {
          showHint(`当前是${currentTurn === 'white' ? '白' : '黑'}棋回合，该棋子是${isWhitePiece ? '白' : '黑'}棋，无法移动`, 'warning');
          return;
        }
      }

      setSelected({ row, col });
      setLegalMovePositions(parseLegalMovePositions({ row, col }, legalMoves, fromChessNotation));
      return;
    }

    // 2. 已选中棋子
    const fromRow = selected.row;
    const fromCol = selected.col;
    const selectedPiece = board[fromRow][fromCol];
    const isSelectedPieceWhite = selectedPiece === selectedPiece.toUpperCase();

    // 2.1 点击同色棋子：切换选中
    if (piece) {
      const isTargetPieceWhite = piece === piece.toUpperCase();
      const isSameColor = isSelectedPieceWhite === isTargetPieceWhite;
      const isMyTargetPiece =
        gameMode === 'ai'
          ? (playerColor === 'white' && isTargetPieceWhite) || (playerColor === 'black' && !isTargetPieceWhite)
          : true;
      if (isSameColor && isMyTargetPiece) {
        setSelected({ row, col });
        setLegalMovePositions(parseLegalMovePositions({ row, col }, legalMoves, fromChessNotation));
        return;
      }
    }

    const toRow = row;
    const toCol = col;
    const move = toChessNotation(fromRow, fromCol) + toChessNotation(toRow, toCol);

    // 2.2 升变
    if (isPromotion(fromRow, fromCol, toRow, toCol, board)) {
      if (!isValidPromotionMove(fromRow, fromCol, toRow, toCol, board, legalMoves)) {
        setSelected(null);
        setLegalMovePositions([]);
        showHint(getInvalidMoveReason(board, fromRow, fromCol, toRow, toCol, currentTurn), 'error');
        return;
      }
      const promotionPiece = board[fromRow][fromCol];
      setPromotionData({
        from: { row: fromRow, col: fromCol },
        to: { row: toRow, col: toCol },
        color: promotionPiece === 'P' ? 'white' : 'black',
      });
      setShowPromotion(true);
      return;
    }

    // 2.3 普通走法合法性
    if (!legalMoves.includes(move)) {
      setSelected(null);
      setLegalMovePositions([]);
      showHint(getInvalidMoveReason(board, fromRow, fromCol, toRow, toCol, currentTurn), 'error');
      return;
    }

    // 2.4 乐观更新 + 提交
    setBoard(updateBoardLocally(board, fromRow, fromCol, toRow, toCol));
    setLastMove({ from: { row: fromRow, col: fromCol }, to: { row: toRow, col: toCol } });
    setSelected(null);
    setLegalMovePositions([]);
    submitMove(move);
  };

  // AI 走棋
  const handleAIMove = useCallback(async ({ automatic = false } = {}) => {
    const id = gameIdRef.current;
    if (!id || aiThinkingRef.current || endState.over) return;
    aiThinkingRef.current = true;
    setLoading(true);
    showHint('AI 正在思考…', 'info');
    try {
      const data = await requestAIMoveToServer(id, aiLevelRef.current);
      applyIfCurrent(id, data);
      const { isCheckmate } = resolveGameEndState(data.board_state || {});
      showHint(
        isCheckmate ? `将死！${getWinnerLabel(data.board_state?.turn, data.board_state?.game_result)} 获胜` : `AI 走棋：${data.ai_move}`,
        isCheckmate ? 'warning' : 'info',
      );
    } catch (err) {
      // 多个客户端会同时替 AI 落子，只有一个成功；其余对齐到已经走完的局面
      const message = err?.message || '';
      const raced =
        automatic &&
        (message.includes('当前是玩家回合') || message.includes('已无棋可走') || message.includes('对局已结束'));
      if (raced) {
        await reloadState().catch(() => {});
      } else {
        showHint(message, 'error');
      }
    } finally {
      aiThinkingRef.current = false;
      setLoading(false);
    }
  }, [endState.over, applyIfCurrent, showHint, reloadState]);

  // AI 回合自动落子
  useEffect(() => {
    if (booting || loading || gameMode !== 'ai' || !gameId) return;
    if (endState.over) return;
    if (currentTurn !== playerColor) handleAIMove({ automatic: true });
  }, [booting, loading, gameMode, gameId, currentTurn, playerColor, endState.over, handleAIMove]);

  // 提示自动消失
  useEffect(() => {
    if (!hint.show) return undefined;
    const duration = hint.type === 'info' ? 2000 : hint.type === 'warning' ? 3000 : 4000;
    const timer = setTimeout(() => setHint((prev) => ({ ...prev, show: false })), duration);
    return () => clearTimeout(timer);
  }, [hint.show, hint.type]);

  const resetGame = async () => {
    const id = gameIdRef.current;
    if (!id) return;
    setLoading(true);
    try {
      const data = await resetGameToServer(id);
      applyIfCurrent(id, data);
      showHint('对局已重置', 'info');
    } catch (err) {
      showHint(err.message, 'error');
    } finally {
      setLoading(false);
    }
  };

  const undoMove = async () => {
    const plies = gameMode === 'ai' ? 2 : 1;
    const id = gameIdRef.current;
    if (!id || loading || gameAlert.type === 'checkmate') return;
    if (moveHistory.length < plies) {
      showHint(`暂无足够走棋记录（需要至少 ${plies} 着），无法悔棋`, 'warning');
      return;
    }
    setLoading(true);
    try {
      const data = await undoMoveToServer(id, plies);
      applyIfCurrent(id, data);
      showHint(`悔棋成功（已回退 ${plies} 着）`, 'info');
    } catch (err) {
      showHint(err.message, 'error');
    } finally {
      setLoading(false);
    }
  };

  const toggleFlipBoard = () => setFlipBoard((prev) => !prev);

  const isGameLocked = loading || booting;
  const canUndo = moveHistory.length >= (gameMode === 'ai' ? 2 : 1);

  return (
    <div className="game-page">
      <header className="game-header">
        <div className="game-header__brand">
          <span className="game-header__icon" aria-hidden="true">♟</span>
          <div>
            <h1 className="game-header__title">Chess By DIPENG</h1>
            <p className="game-header__subtitle">国际象棋 AI 对弈与分析</p>
          </div>
        </div>
        {gameId && (
          <div className="game-header__meta">
            <span className="game-header__label">对局 ID</span>
            <code className="game-header__id">{gameId.slice(0, 8)}</code>
            {statistics.total_moves > 0 && (
              <span className="game-header__label">共 {statistics.total_moves} 着</span>
            )}
            <span className={`game-header__label ${synced ? 'game-header__label--live' : ''}`}>
              {synced ? '实时同步' : '未连接'}
            </span>
          </div>
        )}
      </header>

      <div className="game-status-bar">
        {gameMode && (
          <span className={`status-indicator ${currentTurn === 'white' ? 'status-indicator--white' : 'status-indicator--black'}`} />
        )}
        <p className="game-status-bar__text">{gameStatus}</p>
      </div>

      <section className="game-toolbar" aria-label="游戏设置">
        <div className="toolbar-group">
          <span className="toolbar-group__label">对局模式</span>
          <div className="toolbar-group__buttons">
            <button
              className={`btn btn--segment ${gameMode === 'self' ? 'btn--segment-active' : ''}`}
              onClick={() => switchMode('self')}
              disabled={isGameLocked}
            >
              自我博弈
            </button>
            <button
              className={`btn btn--segment ${gameMode === 'ai' && playerColor === 'white' ? 'btn--segment-active' : ''}`}
              onClick={() => switchMode('ai', 'white')}
              disabled={isGameLocked}
            >
              人机 · 执白
            </button>
            <button
              className={`btn btn--segment ${gameMode === 'ai' && playerColor === 'black' ? 'btn--segment-active' : ''}`}
              onClick={() => switchMode('ai', 'black')}
              disabled={isGameLocked}
            >
              人机 · 执黑
            </button>
            <button className="btn btn--ghost" onClick={toggleFlipBoard} disabled={isGameLocked}>
              ↕ 翻转棋盘
            </button>
          </div>
        </div>

        <ThemeSwitcher />

        {gameMode === 'ai' && (
          <div className="toolbar-group">
            <span className="toolbar-group__label">AI 等级</span>
            <div className="toolbar-group__buttons">
              <button
                className={`btn btn--segment ${aiLevel === 'normal' ? 'btn--segment-active' : ''}`}
                onClick={() => selectAILevel('normal')}
                disabled={isGameLocked}
              >
                普通
              </button>
              <button
                className={`btn btn--segment ${aiLevel === 'advanced' ? 'btn--segment-active' : ''}`}
                onClick={() => selectAILevel('advanced')}
                disabled={isGameLocked}
              >
                高级
              </button>
            </div>
          </div>
        )}
      </section>

      <div className="game-layout">
        <div className="game-board-panel">
          <ChessBoard
            lastMove={lastMove}
            isFlipBoard={flipBoard}
            selected={selected}
            legalMovePositions={legalMovePositions}
            onClickEvent={handleSquareClick}
            board={board}
          />
        </div>

        <aside className="game-sidebar">
          <MoveHistoryWidget moveHistory={moveHistory} />
        </aside>
      </div>

      <footer className="game-actions">
        <button className="btn btn--secondary" onClick={resetGame} disabled={isGameLocked}>
          重置游戏
        </button>
        <button
          className="btn btn--secondary"
          onClick={undoMove}
          disabled={isGameLocked || !canUndo || gameAlert.type === 'checkmate'}
        >
          悔棋{gameMode === 'ai' ? '（回退 2 着）' : ''}
        </button>
        {gameMode === 'ai' && (
          <button
            className="btn btn--primary"
            onClick={() => handleAIMove()}
            disabled={isGameLocked || gameAlert.type === 'checkmate' || endState.isStalemate}
          >
            {loading ? (
              <span className="btn__loading">
                <span className="btn__spinner" aria-hidden="true" />
                AI 思考中…
              </span>
            ) : (
              '强制 AI 走棋'
            )}
          </button>
        )}
      </footer>

      {showPromotion && (
        <div className="promotion-modal" role="dialog" aria-modal="true" aria-label="兵升变">
          <div className="promotion-modal__backdrop" />
          <div className="promotion-content">
            <h3 className="promotion-content__title">兵升变</h3>
            <p className="promotion-content__desc">请选择要升变的棋子</p>
            <div className="promotion-options">
              {PROMOTION_OPTIONS[promotionData.color].map((piece) => (
                <button
                  key={piece}
                  onClick={() => handlePromotionSelect(piece)}
                  className="promotion-btn"
                  disabled={gameAlert.type === 'checkmate'}
                >
                  <PieceView piece={piece} className="promotion-img" />
                  <span>{PROMOTION_NAMES[piece]}</span>
                </button>
              ))}
            </div>
          </div>
        </div>
      )}

      {hint.show && (
        <div className="toast-container" role="status" aria-live="polite">
          <div className={`toast toast--${hint.type}`}>{hint.text}</div>
        </div>
      )}

      {(gameAlert.type === 'checkmate' || gameAlert.type === 'check') && (
        <div className={`global-alert global-alert--${gameAlert.type}`} role="alert" aria-live="assertive">
          {gameAlert.text}
        </div>
      )}
    </div>
  );
}

export default Game;
