import React, { useRef, useEffect } from 'react';
import './MoveHistoryWidget.css';

// 格式化走棋文本的工具函数（可根据你的业务逻辑调整）
const formatMoveText = (move) => {
  const colorText = move.color === 'white' ? '白棋' : '黑棋';
  const typeText = move.type === 'ai' ? '(AI)' : '(玩家)';
  return (
    <span className="move-text">
      #{move.move_number} {colorText} {typeText}：{move.move}
    </span>
  );
};

/**
 * 走棋历史组件
 * @param {Array} moveHistory - 走棋历史数组
 * @param {Object} style - 自定义样式（可选）
 * @returns {JSX.Element}
 */
const MoveHistoryWidget = ({ moveHistory, style = {} }) => {
  // 1. 创建列表容器的ref，用于获取DOM元素
  const historyListRef = useRef(null);

  // 2. 监听moveHistory变化，更新后自动滚动到底部
  useEffect(() => {
    if (historyListRef.current) {
      // 滚动到底部（两种方式兼容所有浏览器）
      historyListRef.current.scrollTop = historyListRef.current.scrollHeight;
      // 备选方案（更通用）：
      // historyListRef.current.scrollIntoView({
      //   behavior: 'smooth', // 平滑滚动（可选）
      //   block: 'end'
      // });
    }
  }, [moveHistory]); // 依赖moveHistory，数组变化时触发

  return (
    <div className="move-history-container" style={style}>
      <h3>走棋历史</h3>
      {moveHistory.length === 0 ? (
        <div className="empty-history">暂无走棋记录</div>
      ) : (
        // 3. 将ref绑定到滚动列表容器
        <div 
          className="move-history-list"
          ref={historyListRef} // 关键：绑定ref
        >
          {moveHistory.map((move, index) => (
            <div 
              key={index} 
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