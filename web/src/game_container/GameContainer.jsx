import { useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import GameStatusWidget from './GameStatusWidget';
import { resetGameToServer } from '../utils/apiUtils.js';
import { saveGameId, ensureSessionGame } from '../utils/gameSession.js';
import './GameContainer.css';

/** 实时分析板块：订阅本进程正在进行的那一局 */
const GameContainer = () => {
  const gameStatusRef = useRef(null);
  const [notice, setNotice] = useState('');
  const [busy, setBusy] = useState(false);

  const handleGameReset = async () => {
    setBusy(true);
    setNotice('');
    try {
      const gameId = (await ensureSessionGame()).game_id;
      const data = await resetGameToServer(gameId);
      saveGameId(data.game_id);
      if (gameStatusRef.current) gameStatusRef.current.resetGameData();
      setNotice(`已重置，所有打开的客户端都会进入新对局 ${String(data.game_id).slice(0, 8)}`);
    } catch (err) {
      setNotice(`重置失败：${err.message}`);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="game-container">
      <div className="game-controls">
        <div>
          <Link to="/" className="page-back">← 返回对弈</Link>
          <h2>棋局对战</h2>
        </div>
        <button onClick={handleGameReset} className="reset-btn" disabled={busy}>
          {busy ? '重置中…' : '🔄 重置游戏'}
        </button>
        {notice && <p className="reset-notice">{notice}</p>}
      </div>

      <GameStatusWidget ref={gameStatusRef} />
    </div>
  );
};

export default GameContainer;
