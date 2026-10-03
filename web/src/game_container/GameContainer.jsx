import React, { useRef } from 'react';
import GameStatusWidget from './GameStatusWidget';
import './GameContainer.css';

const GameContainer = () => {
  // 创建ref指向分析组件，用于调用重置方法
  const gameStatusRef = useRef(null);

  // 重置游戏的核心方法
  const handleGameReset = () => {
    // 1. 调用你的游戏重置逻辑（比如清空棋盘、通知后端重置等）
    console.log('触发游戏重置');
    // 示例：这里可以添加调用后端重置接口的代码
    // fetch(`${API_BASE_URL}/reset-game`, { method: 'POST' })
    //   .then(res => res.json())
    //   .then(data => console.log('后端重置成功:', data))
    //   .catch(err => console.error('后端重置失败:', err));

    // 2. 调用分析组件的重置方法，清空历史数据
    if (gameStatusRef.current) {
      gameStatusRef.current.resetGameData();
      alert('游戏已重置，分析数据已清空！');
    }
  };

  return (
    <div className="game-container">
      {/* 游戏控制区 */}
      <div className="game-controls">
        <h2>棋局对战</h2>
        <button onClick={handleGameReset} className="reset-btn">🔄 重置游戏</button>
      </div>

      {/* 实时分析模块（绑定ref） */}
      <GameStatusWidget ref={gameStatusRef} />
    </div>
  );
};

export default GameContainer;