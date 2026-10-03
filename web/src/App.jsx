import { Routes, Route, Link } from 'react-router-dom';
import Game from './game/Game.jsx';
import './App.css'
import GameContainer from './game_container/GameContainer.jsx';
import PGNReplay from './pgn_replay/PGNReplay.jsx';

function App() {
  return (
    <div className="App">

      <Routes>

        {/* 游戏板块 */}
        <Route path="/" element={<Game />} />

        {/* 热力图板块 */}
        <Route path="/flight-charts" element={<GameContainer />} />

        {/* 棋谱演变板块 */}
        <Route path='/pgn-replay' element={<PGNReplay/>} />

      </Routes>

    </div>
  );
}

export default App;