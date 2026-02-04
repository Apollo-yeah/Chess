import React, { useState, useEffect } from 'react';
import './Game.css';
import MoveHistoryWidget from './MoveHistoryWidget.jsx';

// 导入常量
import { PIECE_IMAGES, PROMOTION_OPTIONS, PROMOTION_NAMES, INITIAL_FEN, ROW_LABELS, COL_LABELS } from '../constants/chess_config.js';

// 导入工具函数
import { parseFEN, toChessNotation, fromChessNotation, updateBoardLocally, initBoard } from '../utils/boardUtils.js';
import { getInvalidMoveReason, isPromotion, isValidPromotionMove, parseLegalMovePositions, formatMoveText } from '../utils/moveUtils.js';
import { fetchBoardState, setGameModeToServer, makeMoveToServer, requestAIMoveToServer, resetGameToServer, undoMoveToServer } from '../utils/apiUtils.js';
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

  const loadBoardState = async () => {
    try {
      const data = await fetchBoardState();
      const newTurn = data.turn;
      setBoard(parseFEN(data.fen));
      setLegalMoves(data.legal_moves);
      setCurrentTurn(newTurn);

      if (data.is_checkmate) {
        setGameAlert({ type: 'checkmate', text: 'Checkmate!' });
        const winner = newTurn === 'white' ? '黑棋' : '白棋';
        setGameStatus(`【${gameMode === 'ai' ? '人机对战' : '自我博弈'}】Checkmate！${winner} 获胜！`);
      } else if (data.is_check) {
        setGameAlert({ type: 'check', text: 'Check!' });
        setGameStatus(`【${gameMode === 'ai' ? '人机对战' : '自我博弈'}】当前回合：${newTurn === 'white' ? '白棋' : '黑棋'}（Check！）`);
      } else if (data.is_stalemate) {
        setGameAlert({ type: '', text: '' });
        setGameStatus(`【${gameMode === 'ai' ? '人机对战' : '自我博弈'}】和棋！`);
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

      setLegalMovePositions(parseLegalMovePositions(selected, data.legal_moves, fromChessNotation));
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
      .then(data => { if (data.success) { loadBoardState(); showHint(`兵升变为${PROMOTION_NAMES[pieceType]}`, 'info'); } else showHint('走棋失败：' + (data.error || '未知错误'), 'error'); })
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
      .then(data => {
        if (data.success) {
          setSelected(null);
          setLegalMovePositions([]);
          loadBoardState();
          showHint('走棋成功', 'info');
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
        // 解析AI走法并本地更新
        const aiMove = data.ai_move;
        const fromNotation = aiMove.substring(0, 2);
        const toNotation = aiMove.substring(2, 4);
        const fromPos = fromChessNotation(fromNotation);
        const toPos = fromChessNotation(toNotation);
        const promotionPiece = aiMove.length > 4 ? aiMove[4].toUpperCase() : null;
        
        // 本地乐观更新
        const newBoard = updateBoardLocally(board, fromPos.row, fromPos.col, toPos.row, toPos.col, promotionPiece);
        setBoard(newBoard);
        setLastMove({ from: fromPos, to: toPos });
        
        // 加载最新状态
        await loadBoardState();
        showHint(`AI走棋：${aiMove}`, 'info');
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
      
      // 循环悔棋
      for (let i = 0; i < undoSteps; i++) {
        const data = await undoMoveToServer();
        if (!data.success) {
          throw new Error(data.error || '悔棋失败');
        }
      }
      
      setSelected(null);
      setLegalMovePositions([]);
      await loadBoardState();
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



  return (
    <div className="App">
      <h1>Chess By DIPENG</h1>
      <div className="game-info">{gameId && <p>当前游戏ID：{gameId}</p>}</div>
      <div className="status">{gameStatus}</div>

      <div className="mode-selector">
        <div className="base-mode">
          <span>选择模式：</span>
          <button onClick={switchToSelfMode} disabled={loading || gameAlert.type === 'checkmate'}>自我博弈</button>
          <button onClick={() => switchToAiMode('white')} disabled={loading || gameAlert.type === 'checkmate'}>人机对战（执白）</button>
          <button onClick={() => switchToAiMode('black')} disabled={loading || gameAlert.type === 'checkmate'}>人机对战（执黑）</button>
          <button onClick={() => toggleFlipBoard()} disabled={loading || gameAlert.type === 'checkmate'}>翻转棋盘</button>
        </div>
        {gameMode === 'ai' && (
          <div className="ai-level">
            <span>AI等级：</span>
            <button onClick={() => selectAILevel('normal')} disabled={loading || gameAlert.type === 'checkmate'}>普通AI</button>
            <button onClick={() => selectAILevel('advanced')} disabled={loading || gameAlert.type === 'checkmate'}>高级AI</button>
          </div>
        )}
      </div>

      <div className="main-content">
        <ChessBoard
          lastMove={lastMove}
          isFlipBoard={flipBoard}
          selected={selected}
          legalMovePositions={legalMovePositions}
          onClickEvent={(actualRow, actualCol) => {handleSquareClick(actualRow, actualCol)}}
          board={board}
        />

        <div>
          <MoveHistoryWidget 
            moveHistory={moveHistory} 
            formatMoveText={formatMoveText} 
          />
        </div>
      </div>

      {showPromotion && (
        <div className="promotion-modal">
          <div className="promotion-content">
            <h3>兵升变 - 选择棋子</h3>
            <div className="promotion-options">
              {PROMOTION_OPTIONS[promotionData.color].map(piece => (
                <button key={piece} onClick={() => handlePromotionSelect(piece)} className="promotion-btn" disabled={gameAlert.type === 'checkmate'}>
                  <img src={PIECE_IMAGES[piece]} alt={PROMOTION_NAMES[piece]} className="promotion-img" />
                  <span>{PROMOTION_NAMES[piece]}</span>
                </button>
              ))}
            </div>
          </div>
        </div>
      )}

      <div className="controls">
        <button onClick={resetGame} disabled={loading}>重置游戏</button>
        <button onClick={undoMove} disabled={loading || (moveHistory.length < (gameMode === 'ai' ? 2 : 1)) || gameAlert.type === 'checkmate'}>悔棋</button>
        {gameMode === 'ai' && <button onClick={handleAIMove} disabled={loading || gameAlert.type === 'checkmate' || gameStatus.includes('和棋')}>{loading ? 'AI思考中...' : '强制AI走棋'}</button>}
      </div>

      <div className="hint-container">{hint.show && <div className={`hint hint-${hint.type}`}>{hint.text}</div>}</div>

      <div className="game-alert-container">
        {gameAlert.type === 'checkmate' && <div className="game-alert checkmate">⚠️ {gameAlert.text} （将死）</div>}
        {gameAlert.type === 'check' && <div className="game-alert check">⚠️ {gameAlert.text} （将军）</div>}
      </div>
    </div>
  );
}

export default Game;
