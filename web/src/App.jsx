import { Routes, Route } from 'react-router-dom';
import Game from './game/Game.jsx';
import './App.css'
import GameContainer from './game_container/GameContainer.jsx';
import PGNReplay from './pgn_replay/PGNReplay.jsx';
import StatusPage from './status/StatusPage.jsx';
import { PieceThemeProvider } from './pieces/PieceThemeContext.jsx';

function App() {
  return (
    <PieceThemeProvider>
      <div className="App">

        <Routes>

          {/* 游戏板块 */}
          <Route path="/" element={<Game />} />

          {/* 热力图板块 */}
          <Route path="/flight-charts" element={<GameContainer />} />

          {/* 棋谱演变板块 */}
          <Route path='/pgn-replay' element={<PGNReplay/>} />

          {/* 服务状态 */}
          <Route path="/status" element={<StatusPage />} />

        </Routes>

      </div>
    </PieceThemeProvider>
  );
}

export default App;