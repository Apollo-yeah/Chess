import React, { useState, useEffect } from 'react';
import './Game.css';
import MoveHistoryWidget from './MoveHistoryWidget.jsx';

// 导入常量
import { PIECE_IMAGES, PROMOTION_OPTIONS, PROMOTION_NAMES, INITIAL_FEN, ROW_LABELS, COL_LABELS } from '../constants/chess_config.js';

// 导入工具函数
import { parseFEN, toChessNotation, fromChessNotation, updateBoardLocally, initBoard } from '../utils/boardUtils.js';
import { getInvalidMoveReason, isPromotion, isValidPromotionMove, parseLegalMovePositions, formatMoveText } from '../utils/moveUtils.js';
import { fetchBoardState, setGameModeToServer, makeMoveToServer, requestAIMoveToServer, resetGameToServer, undoMoveToServer } from '../utils/apiUtils.js';
import { resolveGameEndState, getWinnerLabel } from '../utils/gameStateUtils.js';
import ChessBoard from '../component/ChessBox.jsx';

function Game() {
  const [board, setBoard] = useState(initBoard());
  const [selected, setSelected] = useState(null);
  const [legalMoves, setLegalMoves] = useState([]);
  const [currentTurn, setCurrentTurn] = useState('white');
  const [gameMode, setGameMode] = useState('');
  const [playerColor, setPlayerColor] = useState('');
  const [aiLevel, setAiLevel] = useState('normal');
  const [loading, setLoading] = useState(false);
  const [showPromotion, setShowPromotion] = useState(false);
  const [promotionData, setPromotionData] = useState({});
  const [hint, setHint] = useState({ show: false, text: '', type: 'info' });
  const [gameAlert, setGameAlert] = useState({ type: '', text: '' });
  const [gameStatus, setGameStatus] = useState('请选择游戏模式');
  const [moveHistory, setMoveHistory] = useState([]);
  const [gameId, setGameId] = useState('');
  const [lastMove, setLastMove] = useState({ from: null, to: null });
  const [legalMovePositions, setLegalMovePositions] = useState([]);
  const [flipBoard, setFlipBoard] = useState(false); // 新增：棋盘翻转状态

  const showHint = (text, type = 'info') => setHint({ show: true, text, type });

  const applyBoardState = (data) => {
    const newTurn = data.turn;
    setBoard(parseFEN(data.fen));
    setLegalMoves(data.legal_moves || []);
    setCurrentTurn(newTurn);

    const { isCheckmate, isStalemate, isCheck } = resolveGameEndState(data);
    const modeLabel = gameMode === 'ai' ? '人机对战' : '自我博弈';

    if (isCheckmate) {
      const winner = getWinnerLabel(newTurn, data.game_result);
      setGameAlert({ type: 'checkmate', text: `将死！${winner} 获胜` });
      setGameStatus(`【${modeLabel}】对局结束，${winner} 获胜！`);
    } else if (isStalemate) {
      setGameAlert({ type: '', text: '' });
      setGameStatus(`【${modeLabel}】和棋！`);
    } else if (isCheck) {
      setGameAlert({ type: 'check', text: '将军！请立即应将' });
      setGameStatus(`【${modeLabel}】当前回合：${newTurn === 'white' ? '白棋' : '黑棋'}`);
    } else {
      setGameAlert({ type: '', text: '' });
      if (gameMode === 'ai') {
        setGameStatus(`【人机对战-你执${playerColor === 'white' ? '白' : '黑'}棋】当前回合：${newTurn === 'white' ? '白棋' : '黑棋'} ${newTurn === playerColor ? '（你的回合）' : '（AI回合）'}`);
      } else if (gameMode === 'self') {
        setGameStatus(`【自我博弈】当前回合：${newTurn === 'white' ? '白棋' : '黑棋'} | 请点击对应颜色棋子走棋`);
      }
    }

    setMoveHistory(data.current_history || []);
    if (data.current_history && data.current_history.length > 0) {
      const lastMoveRecord = data.current_history[data.current_history.length - 1];
      const moveStr = lastMoveRecord.move;
      setLastMove({
        from: fromChessNotation(moveStr.substring(0, 2)),
        to: fromChessNotation(moveStr.substring(2, 4))
      });
    } else {
      setLastMove({ from: null, to: null });
    }

    setLegalMovePositions(parseLegalMovePositions(selected, data.legal_moves || [], fromChessNotation));
  };

  const loadBoardState = async () => {
    try {
      const data = await fetchBoardState();
      applyBoardState(data);
    } catch (err) {
      console.error(err.message);
      setGameStatus('请先启动Tornado后端服务！');
      showHint(err.message, 'error');
    }
  };

  useEffect(() => {
    if (gameMode) {
      loadBoardState();
      setGameModeToServer(gameMode, playerColor, aiLevel)
        .then(data => { if (data.success) setGameId(data.game_id); })
        .catch(err => console.error(err.message));
    }
  }, [gameMode, playerColor]);

  useEffect(() => {
    if (gameMode === 'ai' && !loading && gameAlert.type !== 'checkmate' && !gameStatus.includes('和棋')) {
      const isAITurn = (playerColor === 'white' && currentTurn === 'black') || (playerColor === 'black' && currentTurn === 'white');
      if (isAITurn) handleAIMove();
    }
  }, [currentTurn, gameMode, playerColor, loading, gameAlert]);

  useEffect(() => {
    if (hint.show) {
      const duration = hint.type === 'info' ? 2000 : (hint.type === 'warning' ? 3000 : 4000);
      const timer = setTimeout(() => setHint(prev => ({ ...prev, show: false })), duration);
      return () => clearTimeout(timer);
    }
  }, [hint.show, hint.type]);

  const switchToSelfMode = () => {
    setGameMode('self');
    setPlayerColor('');
    resetGame();
    setGameStatus('【自我博弈】当前回合：白棋 | 请点击对应颜色棋子走棋');
    showHint('已切换为自我博弈模式', 'info');
  };

  const switchToAiMode = (color) => {
    setGameMode('ai');
    setPlayerColor(color);
    resetGame();
    setGameStatus(`【人机对战-你执${color === 'white' ? '白' : '黑'}棋】${color === 'black' ? 'AI先出棋（白棋）...' : '你的回合，请走白棋'}`);
    showHint(`已切换为人机对战模式（你执${color === 'white' ? '白' : '黑'}棋）`, 'info');
  };

  const selectAILevel = (level) => {
    if (gameMode !== 'ai') return;
    setAiLevel(level);
    setGameModeToServer(gameMode, playerColor, level).catch(err => console.error(err.message));
    setGameStatus(gameStatus.replace('普通AI', '高级AI').replace('高级AI', '普通AI').replace('AI', `${level === 'normal' ? '普通' : '高级'}AI`));
    showHint(`已切换为${level === 'normal' ? '普通' : '高级'}AI`, 'info');
  };

  const handlePromotionSelect = (pieceType) => {
    const { from, to } = promotionData;
    const fromNotation = toChessNotation(from.row, from.col);
    const toNotation = toChessNotation(to.row, to.col);
    const move = fromNotation + toNotation + pieceType.toLowerCase();

    const newBoard = updateBoardLocally(board, from.row, from.col, to.row, to.col, pieceType);
    setBoard(newBoard);

    makeMoveToServer(move)
      .then(async (data) => {
        if (data.success) {
          if (data.fen) {
            applyBoardState(data);
          } else {
            await loadBoardState();
          }
          const { isCheckmate } = resolveGameEndState(data);
          showHint(
            isCheckmate ? '将死！对局结束' : `兵升变为${PROMOTION_NAMES[pieceType]}`,
            isCheckmate ? 'warning' : 'info'
          );
        } else {
          showHint('走棋失败：' + (data.error || '未知错误'), 'error');
        }
      })
      .catch(err => showHint(err.message, 'error'));

    setShowPromotion(false);
    setPromotionData({});
    setLegalMovePositions([]);
  };

  // 处理棋盘格子点击
  const handleSquareClick = (row, col) => {
    if (loading || !gameMode || gameAlert.type === 'checkmate' || gameStatus.includes('和棋') || showPromotion) return;
    
    const piece = board[row][col];
    
    // 1. 未选中任何棋子：选中目标棋子
    if (!selected) {
      if (!piece) {
        showHint('该位置无棋子，请选择有棋子的格子', 'info');
        return;
      }
      
      // 人机模式下校验是否是己方棋子且当前回合
      if (gameMode === 'ai') {
        const isWhitePiece = piece === piece.toUpperCase();
        const isMyPiece = (playerColor === 'white' && isWhitePiece) || (playerColor === 'black' && !isWhitePiece);
        const isMyTurn = currentTurn === playerColor;
        
        if (!isMyPiece) {
          showHint(`你执${playerColor === 'white' ? '白' : '黑'}棋，该棋子是${isWhitePiece ? '白' : '黑'}棋，无法选择`, 'warning');
          return;
        }
        if (!isMyTurn) {
          showHint(`当前是${currentTurn === 'white' ? '白' : '黑'}棋回合（AI回合），请等待AI走棋`, 'warning');
          return;
        }
      } else if (gameMode === 'self') {
        // 自我博弈模式下校验是否是当前回合棋子
        const isWhitePiece = piece === piece.toUpperCase();
        const isCurrentTurnPiece = (currentTurn === 'white' && isWhitePiece) || (currentTurn === 'black' && !isWhitePiece);
        if (!isCurrentTurnPiece) {
          showHint(`当前是${currentTurn === 'white' ? '白' : '黑'}棋回合，该棋子是${isWhitePiece ? '白' : '黑'}棋，无法移动`, 'warning');
          return;
        }
      }
      
      // 选中棋子并解析可走位置
      setSelected({ row, col });
      showHint(`已选中${piece === piece.toUpperCase() ? '白' : '黑'}${piece.toLowerCase() === 'p' ? '兵' : PROMOTION_NAMES[piece] || '王'}`, 'info');
      setLegalMovePositions(parseLegalMovePositions({ row, col }, legalMoves, fromChessNotation));
      return;
    }

    // 2. 已选中棋子：处理走棋逻辑
    const fromRow = selected.row;
    const fromCol = selected.col;
    const selectedPiece = board[fromRow][fromCol];
    const isSelectedPieceWhite = selectedPiece === selectedPiece.toUpperCase();
    
    // 2.1 点击己方棋子：切换选中
    if (piece) {
      const isTargetPieceWhite = piece === piece.toUpperCase();
      const isSameColor = (isSelectedPieceWhite && isTargetPieceWhite) || (!isSelectedPieceWhite && !isTargetPieceWhite);
      
      const isMyTargetPiece = gameMode === 'ai' 
        ? ((playerColor === 'white' && isTargetPieceWhite) || (playerColor === 'black' && !isTargetPieceWhite))
        : true;
      
      if (isSameColor && isMyTargetPiece) {
        setSelected({ row, col });
        showHint(`已切换选中为${isTargetPieceWhite ? '白' : '黑'}${piece.toLowerCase() === 'p' ? '兵' : PROMOTION_NAMES[piece] || '王'}`, 'info');
        setLegalMovePositions(parseLegalMovePositions({ row, col }, legalMoves, fromChessNotation));
        return;
      }
    }

    // Game.jsx 中 handleSquareClick 里的升变校验部分
    // 2.2 点击敌方/空位：走棋
    const toRow = row;
    const toCol = col;
    const fromNotation = toChessNotation(fromRow, fromCol);
    const toNotation = toChessNotation(toRow, toCol);
    const move = fromNotation + toNotation;

    // 修复：调用 isValidPromotionMove 时参数顺序正确
    if (isPromotion(fromRow, fromCol, toRow, toCol, board)) {
      // 校验升变走法是否合法
      if (!isValidPromotionMove(fromRow, fromCol, toRow, toCol, board, legalMoves)) {
        setSelected(null);
        setLegalMovePositions([]);
        const reason = getInvalidMoveReason(board, fromRow, fromCol, toRow, toCol, currentTurn);
        showHint(reason, 'error');
        return;
      }
      
      // 合法升变：显示升变弹窗
      const piece = board[fromRow][fromCol];
      const color = piece === 'P' ? 'white' : 'black';
      setPromotionData({ from: { row: fromRow, col: fromCol }, to: { row: toRow, col: toCol }, color });
      setShowPromotion(true);
      return;
    }

    // 校验普通走法合法性
    if (!legalMoves.includes(move)) {
      setSelected(null);
      setLegalMovePositions([]);
      const reason = getInvalidMoveReason(board, fromRow, fromCol, toRow, toCol, currentTurn);
      showHint(reason, 'error');
      return;
    }

    // 合法走棋：本地乐观更新
    const newBoard = updateBoardLocally(board, fromRow, fromCol, toRow, toCol);
    setBoard(newBoard);
    setLastMove({ from: { row: fromRow, col: fromCol }, to: { row: toRow, col: toCol } });
    
    // 执行走棋
    makeMoveToServer(move)
      .then(async (data) => {
        if (data.success) {
          setSelected(null);
          setLegalMovePositions([]);
          if (data.fen) {
            applyBoardState(data);
          } else {
            await loadBoardState();
          }
          const { isCheckmate } = resolveGameEndState(data);
          showHint(isCheckmate ? '将死！对局结束' : '走棋成功', isCheckmate ? 'warning' : 'info');
        } else {
          // 走棋失败：回滚本地棋盘
          setBoard(JSON.parse(JSON.stringify(board)));
          setSelected(null);
          setLegalMovePositions([]);
          showHint('走棋失败：' + (data.error || '未知错误'), 'error');
        }
      })
      .catch(err => {
        // 异常：回滚本地棋盘
        setBoard(JSON.parse(JSON.stringify(board)));
        setSelected(null);
        setLegalMovePositions([]);
        showHint(err.message, 'error');
      });
  };

  // AI走棋逻辑
  const handleAIMove = async () => {
    if (loading || gameMode !== 'ai' || gameAlert.type === 'checkmate' || gameStatus.includes('和棋')) return;
    
    setLoading(true);
    showHint('AI正在思考...', 'info');
    try {
      const data = await requestAIMoveToServer(aiLevel);
      console.log(data)
      if (data.success && data.ai_move) {
        const aiMove = data.ai_move;
        const fromNotation = aiMove.substring(0, 2);
        const toNotation = aiMove.substring(2, 4);
        const fromPos = fromChessNotation(fromNotation);
        const toPos = fromChessNotation(toNotation);
        const promotionPiece = aiMove.length > 4 ? aiMove[4].toUpperCase() : null;

        const newBoard = updateBoardLocally(board, fromPos.row, fromPos.col, toPos.row, toPos.col, promotionPiece);
        setBoard(newBoard);
        setLastMove({ from: fromPos, to: toPos });

        if (data.fen) {
          applyBoardState(data);
        } else {
          await loadBoardState();
        }

        const { isCheckmate } = resolveGameEndState(data);
        showHint(isCheckmate ? `将死！${getWinnerLabel(data.turn, data.game_result)} 获胜` : `AI走棋：${aiMove}`, isCheckmate ? 'warning' : 'info');
      } else {
        showHint('AI走棋失败', 'error');
      }
    } catch (err) {
      showHint(err.message, 'error');
    } finally {
      setLoading(false);
    }
  };

  
  // 重置游戏
  const resetGame = async () => {
    // 本地乐观重置
    setBoard(parseFEN(INITIAL_FEN));
    setSelected(null);
    setLegalMovePositions([]);
    setShowPromotion(false);
    setPromotionData({});
    setGameAlert({ type: '', text: '' });
    setMoveHistory([]);
    setLastMove({ from: null, to: null });
    
    try {
      const data = await resetGameToServer();
      if (data.success) {
        setGameId(data.new_game_id);
        await loadBoardState();
        showHint('游戏已重置', 'info');
      } else {
        showHint('重置失败，请重试', 'error');
      }
    } catch (err) {
      console.error(err.message);
      showHint('重置失败，请重试', 'error');
    }
  };

  // 悔棋逻辑
  const undoMove = async () => {
    const undoSteps = gameMode === 'ai' ? 2 : 1;
    if (moveHistory.length < undoSteps || loading || gameAlert.type === 'checkmate') {
      const minSteps = undoSteps === 2 ? '至少两步' : '至少一步';
      showHint(moveHistory.length < undoSteps ? `暂无足够走棋记录（需要${minSteps}），无法悔棋` : '当前状态无法悔棋', 'warning');
      return;
    }

    try {
      setLoading(true);
      showHint(`正在悔棋（回退${undoSteps}步）...`, 'info');
      
      let lastData = null;
      for (let i = 0; i < undoSteps; i++) {
        lastData = await undoMoveToServer();
        if (!lastData.success) {
          throw new Error(lastData.error || '悔棋失败');
        }
      }
      
      setSelected(null);
      setLegalMovePositions([]);
      if (lastData?.fen) {
        applyBoardState(lastData);
      } else {
        await loadBoardState();
      }
      showHint(`悔棋成功（已回退${undoSteps}步）`, 'info');
    } catch (err) {
      console.error(err.message);
      showHint('悔棋失败：' + err.message, 'error');
    } finally {
      setLoading(false);
    }
  };

  // 新增：翻转棋盘
  const toggleFlipBoard = () => setFlipBoard(prev => !prev);



  const isGameLocked = loading || gameAlert.type === 'checkmate';
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
            <code className="game-header__id">{gameId}</code>
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
              onClick={switchToSelfMode}
              disabled={isGameLocked}
            >
              自我博弈
            </button>
            <button
              className={`btn btn--segment ${gameMode === 'ai' && playerColor === 'white' ? 'btn--segment-active' : ''}`}
              onClick={() => switchToAiMode('white')}
              disabled={isGameLocked}
            >
              人机 · 执白
            </button>
            <button
              className={`btn btn--segment ${gameMode === 'ai' && playerColor === 'black' ? 'btn--segment-active' : ''}`}
              onClick={() => switchToAiMode('black')}
              disabled={isGameLocked}
            >
              人机 · 执黑
            </button>
            <button
              className="btn btn--ghost"
              onClick={() => toggleFlipBoard()}
              disabled={isGameLocked}
            >
              ↕ 翻转棋盘
            </button>
          </div>
        </div>

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
            onClickEvent={(actualRow, actualCol) => { handleSquareClick(actualRow, actualCol) }}
            board={board}
          />
        </div>

        <aside className="game-sidebar">
          <MoveHistoryWidget
            moveHistory={moveHistory}
            formatMoveText={formatMoveText}
          />
        </aside>
      </div>

      <footer className="game-actions">
        <button className="btn btn--secondary" onClick={resetGame} disabled={loading}>
          重置游戏
        </button>
        <button
          className="btn btn--secondary"
          onClick={undoMove}
          disabled={loading || !canUndo || gameAlert.type === 'checkmate'}
        >
          悔棋
        </button>
        {gameMode === 'ai' && (
          <button
            className="btn btn--primary"
            onClick={handleAIMove}
            disabled={loading || gameAlert.type === 'checkmate' || gameStatus.includes('和棋')}
          >
            {loading ? (
              <span className="btn__loading">
                <span className="btn__spinner" aria-hidden="true" />
                AI 思考中…
              </span>
            ) : '强制 AI 走棋'}
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
              {PROMOTION_OPTIONS[promotionData.color].map(piece => (
                <button
                  key={piece}
                  onClick={() => handlePromotionSelect(piece)}
                  className="promotion-btn"
                  disabled={gameAlert.type === 'checkmate'}
                >
                  <img src={PIECE_IMAGES[piece]} alt={PROMOTION_NAMES[piece]} className="promotion-img" />
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
