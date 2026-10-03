import { useState, useEffect } from 'react';

import { Chess } from 'chess.js';

import {
  INITIAL_FEN,
  COL_LABELS,
  ROW_LABELS
} from '../constants/chess_config';

import './PGNReplay.css';

import PGNHistoryWidget from './PGNHistoryWidget.jsx'

import ChessBoard from '../component/ChessBox.jsx'

// 极简标准PGN（仅走法部分）
const DEFAULT_MOVES = "e4 e5 Nf3 Nc6 Bc4 Bc5 b4 Bxb4 c3 Ba5 d4 exd4 O-O d3 Qb3 Qf6 e5 Qg6 Re1 Nge7 Ba3 b5 Qxb5 Rb8 Qa4 Bb6 Nbd2 Bb7 Ne4 Qf5 Bxd3 Qh5 Nf6+ gxf6 exf6 Rg8 Rad1 Qxf3 Rxe7+ Nxe7 Qxd7+ Kxd7 Bf5+ Ke8 Bd7+ Kf8 Bxe7#";

const PGNReplay = () => {
  const [moveText, setMoveText] = useState(DEFAULT_MOVES);
  const [board, setBoard] = useState(initBoard());
  const [loading, setLoading] = useState(false);
  const [hint, setHint] = useState({ show: false, text: '', type: 'info' });
  const [pgnMoves, setPgnMoves] = useState([]);
  const [currentStep, setCurrentStep] = useState(0);
  const [lastMove, setLastMove] = useState({ from: null, to: null });
  const [flipBoard, setFlipBoard] = useState(false);

  const toggleFlipBoard = () => setFlipBoard(prev => !prev);

  const rounds = [];
  for (let i = 1; i < pgnMoves.length; i += 2) {
    rounds.push({
      round: Math.ceil(i / 2),
      white: pgnMoves[i],
      black: pgnMoves[i + 1] || null,
      whiteIndex: i,
      blackIndex: i + 1
    });
  }

  function initBoard() {
    return [
      ['r', 'n', 'b', 'q', 'k', 'b', 'n', 'r'],
      ['p', 'p', 'p', 'p', 'p', 'p', 'p', 'p'],
      ['', '', '', '', '', '', '', ''],
      ['', '', '', '', '', '', '', ''],
      ['', '', '', '', '', '', '', ''],
      ['', '', '', '', '', '', '', ''],
      ['P', 'P', 'P', 'P', 'P', 'P', 'P', 'P'],
      ['R', 'N', 'B', 'Q', 'K', 'B', 'N', 'R']
    ];
  }

  function initEmptyBoard() {
    return Array(8).fill(null).map(() => Array(8).fill(''));
  }

  function fromChessNotation(notation) {
    if (!notation || notation.length !== 2) return { row: -1, col: -1 };
    const colChar = notation.charAt(0).toLowerCase();
    const rowLabel = notation.charAt(1);
    const col = COL_LABELS.indexOf(colChar);
    const row = ROW_LABELS.indexOf(rowLabel);
    return { row, col };
  }

  function parseFEN(fen) {
    const newBoard = initEmptyBoard();
    const [position] = fen.split(' ');
    const rows = position.split('/');
    
    rows.forEach((rowStr, rowIdx) => {
      let colIdx = 0;
      for (const char of rowStr) {
        if (/\d/.test(char)) {
          colIdx += parseInt(char);
        } else {
          newBoard[rowIdx][colIdx] = char;
          colIdx++;
        }
      }
    });
    return newBoard;
  }

  const parseMoves = () => {
    if (!moveText.trim()) {
      showHint('请输入有效的走法字符串', 'warning');
      return;
    }

    setLoading(true);
    try {
      const moveArray = moveText.trim().split(/\s+/);
      if (moveArray.length === 0) {
        throw new Error('走法字符串为空');
      }

      const tempChess = new Chess();
      const moves = [{
        move: '',
        fen: INITIAL_FEN,
        notation: '初始局面'
      }];

      let plyCount = 0;
      moveArray.forEach((san) => {
        try {
          const moveResult = tempChess.move(san);
          if (!moveResult) return;
          plyCount++;
          const round = Math.ceil(plyCount / 2);
          const moveStr = moveResult.from + moveResult.to + (moveResult.promotion || '');
          let notation = `${round}. ${san}`;
          if (tempChess.isCheckmate()) notation += ' #（将死）';
          else if (tempChess.isCheck()) notation += ' +（将军）';
          moves.push({
            move: moveStr,
            fen: tempChess.fen(),
            notation
          });
        } catch (err) {
          console.warn(`执行走法 ${san} 失败：`, err);
        }
      });

      setPgnMoves(moves);
      setCurrentStep(0);
      setBoard(parseFEN(INITIAL_FEN));
      setLastMove({ from: null, to: null });
      showHint(`解析成功！共${moves.length - 1}步`, 'info');

    } catch (err) {
      showHint(`解析失败：${err.message}`, 'error');
      console.error('走法解析错误：', err);
      setPgnMoves([]);
      setBoard(initBoard());
    } finally {
      setLoading(false);
    }
  };

  const showHint = (text, type = 'info') => {
    setHint({ show: true, text, type });
    setTimeout(() => setHint(prev => ({ ...prev, show: false })), 3000);
  };

  const goToStep = (step) => {
    if (step < 0 || step >= pgnMoves.length) return;
    const target = pgnMoves[step];
    setBoard(parseFEN(target.fen));
    setCurrentStep(step);
    
    if (step > 0 && target.move.length >= 4) {
      const fromNotation = target.move.substring(0, 2);
      const toNotation = target.move.substring(2, 4);
      setLastMove({
        from: fromChessNotation(fromNotation),
        to: fromChessNotation(toNotation)
      });
    } else {
      setLastMove({ from: null, to: null });
    }
  };

  const handlePrevStep = () => goToStep(currentStep - 1);
  const handleNextStep = () => goToStep(currentStep + 1);
  const resetReplay = () => goToStep(0);

  useEffect(() => {
    parseMoves();
  }, []);

  useEffect(() => {
    if (hint.show) {
      const timer = setTimeout(() => setHint({ ...hint, show: false }), 3000);
      return () => clearTimeout(timer);
    }
  }, [hint]);

  return (
    <div className="pgn-replay-container">
      <h1 className="page-title">国际象棋 PGN 复盘工具</h1>

      <div className='container-host-parent'>
        <div>
          <div className="pgn-input-section">
            <h3 className="section-title">走法字符串输入（SAN格式）</h3>
            <textarea
              className="pgn-textarea"
              value={moveText}
              onChange={(e) => setMoveText(e.target.value)}
              rows={4}
              disabled={loading}
              placeholder="输入SAN格式走法，空格分隔（如：e4 e5 Nf3 Nc6）"
            />
            <div className="pgn-input-buttons">
              <button className="btn primary-btn" onClick={parseMoves} disabled={loading}>
                {loading ? '解析中...' : '解析走法'}
              </button>
              <button className="btn secondary-btn" onClick={() => setMoveText('')} disabled={loading}>
                清空
              </button>
            </div>
          </div>

          {hint.show && <div className={`hint hint-${hint.type}`}>{hint.text}</div>}

          {pgnMoves.length > 0 && (
            <div className="replay-controls">
              <h3 className="section-title">复盘控制</h3>
              <div className="control-buttons">
                <button className="btn success-btn" onClick={handlePrevStep} disabled={currentStep === 0 || loading}>
                  上一步
                </button>
                <span className="step-info">
                  步骤：{currentStep} / {pgnMoves.length - 1}
                  {pgnMoves[currentStep].notation && ` | ${pgnMoves[currentStep].notation}`}
                </span>
                <button className="btn success-btn" onClick={handleNextStep} disabled={currentStep === pgnMoves.length - 1 || loading}>
                  下一步
                </button>
                <button className="btn primary-btn" onClick={resetReplay} disabled={loading}>
                  重置
                </button>
              </div>
              <button onClick={() => toggleFlipBoard()}>翻转棋盘</button>
            </div>
          )}

          <div className="chessboard-section">
            <h3 className="section-title">棋局预览</h3>

            <ChessBoard
              lastMove={lastMove}
              isFlipBoard={flipBoard}
              // PGN Replay 中，恒定不选中状态
              isSelected={null}
              legalMovePositions={null}
              onClickEvent={() => showHint('复盘模式下不可走棋', 'info')}
              board={board}
            />
          </div>
        </div>

        {pgnMoves.length > 0 && (
          <PGNHistoryWidget
            rounds={rounds}
            currentStep={currentStep}
            goToStep={goToStep}
          />
        )}
      </div>
    </div>
  );
};

export default PGNReplay;
