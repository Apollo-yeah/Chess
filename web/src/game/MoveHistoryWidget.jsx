import { useRef, useEffect } from 'react';
import './MoveHistoryWidget.css';

const COLOR_TEXT = { white: '白棋', black: '黑棋' };

/** 优先展示 SAN 记谱；旧数据没有 SAN 时退回 UCI */
const formatMoveText = (move) => (
  <span className="move-text">
    #{move.move_number} {COLOR_TEXT[move.color] || move.color} {move.type === 'ai' ? '(AI)' : '(玩家)'}：
    <code>{move.san || move.move}</code>
  </span>
);

/**
 * 走棋历史组件（自动滚动到最新一着）
 * @param {Array} moveHistory - 服务端返回的 move_history
 */
const MoveHistoryWidget = ({ moveHistory = [], style = {} }) => {
  const historyListRef = useRef(null);

  useEffect(() => {
    if (historyListRef.current) {
      historyListRef.current.scrollTop = historyListRef.current.scrollHeight;
    }
  }, [moveHistory]);

  return (
    <div className="move-history-container" style={style}>
      <h3>走棋历史{moveHistory.length > 0 ? `（${moveHistory.length}）` : ''}</h3>
      {moveHistory.length === 0 ? (
        <div className="empty-history">暂无走棋记录</div>
      ) : (
        <div className="move-history-list" ref={historyListRef}>
          {moveHistory.map((move, index) => (
            <div
              key={`${move.move_number}-${move.move}-${index}`}
              className={`move-item ${move.color} ${move.type}`}
            >
              {formatMoveText(move)}
              <span className="move-time">{move.timestamp}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

export default MoveHistoryWidget;
