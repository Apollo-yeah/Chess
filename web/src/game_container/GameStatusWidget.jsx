import { useState, useEffect, useRef, useCallback, forwardRef, useImperativeHandle } from 'react';
import ReactECharts from 'echarts-for-react';
import * as echarts from 'echarts';
import { buildWsUrl } from '../constants/backend_config.js';
import { loadGameId, saveGameId } from '../utils/gameSession.js';
import './GameStatusWidget.css';

const ADVANTAGE_LABELS = {
  white_winning: '白棋必胜',
  black_winning: '黑棋必胜',
  white_advantage: '白棋明显优势',
  black_advantage: '黑棋明显优势',
  slight_white_advantage: '白棋小幅优势',
  slight_black_advantage: '黑棋小幅优势',
  equal: '双方势均力敌',
  unknown: '无法分析',
};

const formatAdvantage = (advantage, score, mateIn) => {
  let scoreText = '';
  if (mateIn !== null && mateIn !== undefined && mateIn !== 0) {
    scoreText = mateIn > 0 ? `（白方 ${mateIn} 步将杀）` : `（黑方 ${Math.abs(mateIn)} 步将杀）`;
  } else if (score) {
    scoreText = `（分值：${score}）`;
  }
  return `${ADVANTAGE_LABELS[advantage] || advantage || '—'} ${scoreText}`;
};

const MAX_POINTS = 20;
const RECONNECT_BASE_MS = 1500;
const RECONNECT_MAX_MS = 15000;

/** 用 forwardRef 暴露清空方法给父组件 */
const GameStatusWidget = forwardRef((props, ref) => {
  const [statusData, setStatusData] = useState(null);
  const [analysisData, setAnalysisData] = useState(null);
  const [analysisPending, setAnalysisPending] = useState(false);
  const [connectionStatus, setConnectionStatus] = useState('idle'); // idle | connecting | connected | disconnected
  const [errorMsg, setErrorMsg] = useState('');
  const [advantageHistory, setAdvantageHistory] = useState([]);
  const [currentGameId, setCurrentGameId] = useState(loadGameId());

  const wsRef = useRef(null);
  const reconnectTimerRef = useRef(null);
  const reconnectAttemptRef = useRef(0);
  const shouldReconnectRef = useRef(true);
  const gameIdRef = useRef(currentGameId);
  gameIdRef.current = currentGameId;

  const appendHistory = useCallback((analysis) => {
    if (!analysis || !analysis.success) return;
    setAdvantageHistory((prev) => {
      const last = prev[prev.length - 1];
      // 同一局面重复推送时不重复记录
      if (last && last.fen === analysis.fen) return prev;
      const next = [
        ...prev,
        {
          step: prev.length + 1,
          score: analysis.advantage_score,
          advantage: analysis.advantage,
          mateIn: analysis.mate_in,
          fen: analysis.fen,
        },
      ];
      return next.slice(-MAX_POINTS);
    });
  }, []);

  const resetGameData = useCallback(() => {
    setAdvantageHistory([]);
    setAnalysisData(null);
    setErrorMsg('');
    setStatusData((prev) =>
      prev
        ? { ...prev, move_history: [], game_info: { ...prev.game_info, result: 'ongoing' } }
        : prev,
    );
  }, []);

  useImperativeHandle(ref, () => ({ resetGameData }), [resetGameData]);

  const applyMessage = useCallback(
    (data) => {
      if (data.type === 'hello') {
        setStatusData(data.status);
        setAnalysisPending(true);
        if (data.game_id) {
          setCurrentGameId(data.game_id);
          saveGameId(data.game_id);
        }
        return;
      }
      if (data.type === 'status_update') {
        setStatusData(data.status);
        setAnalysisPending(true);
        // 局面变化 → 上一次的优势点失效，保留历史曲线，仅清空当前分析
        setAnalysisData(null);
        return;
      }
      if (data.type === 'analysis_update') {
        setAnalysisData(data.analysis);
        setAnalysisPending(false);
        appendHistory(data.analysis);
        return;
      }
      if (data.type === 'error') {
        setErrorMsg(data.message || '服务器返回错误');
      }
    },
    [appendHistory],
  );

  const connectWebSocket = useCallback(() => {
    if (!shouldReconnectRef.current || wsRef.current) return;

    const url = buildWsUrl(gameIdRef.current || undefined);
    setConnectionStatus('connecting');

    let socket;
    try {
      socket = new WebSocket(url);
    } catch (err) {
      setErrorMsg(`无法创建连接：${err.message}`);
      setConnectionStatus('disconnected');
      return;
    }
    wsRef.current = socket;

    socket.onopen = () => {
      reconnectAttemptRef.current = 0;
      setConnectionStatus('connected');
      setErrorMsg('');
    };

    socket.onmessage = (event) => {
      try {
        applyMessage(JSON.parse(event.data));
      } catch (err) {
        setErrorMsg(`数据解析失败：${err.message}`);
      }
    };

    socket.onerror = () => {
      // onerror 之后必定触发 onclose，重连逻辑统一放在 onclose
      setErrorMsg('连接出错，正在尝试重连…');
    };

    socket.onclose = (event) => {
      wsRef.current = null;
      if (!shouldReconnectRef.current) {
        setConnectionStatus('idle');
        return;
      }
      setConnectionStatus('disconnected');
      if (event.code !== 1000) {
        setErrorMsg(`连接断开（code ${event.code}）：${event.reason || '网络异常'}`);
      }
      // 指数退避重连：连接从未建立成功时同样会重试（旧实现此处会永久卡死）
      const delay = Math.min(RECONNECT_BASE_MS * 2 ** reconnectAttemptRef.current, RECONNECT_MAX_MS);
      reconnectAttemptRef.current += 1;
      clearTimeout(reconnectTimerRef.current);
      reconnectTimerRef.current = setTimeout(() => {
        if (shouldReconnectRef.current && !wsRef.current) connectWebSocket();
      }, delay);
    };
  }, [applyMessage]);

  const handleRefresh = useCallback(() => {
    clearTimeout(reconnectTimerRef.current);
    reconnectAttemptRef.current = 0;
    const socket = wsRef.current;
    wsRef.current = null;
    if (socket) {
      try {
        socket.close(1000, '手动刷新');
      } catch {
        /* 忽略 */
      }
    }
    setErrorMsg('');
    setTimeout(() => {
      if (shouldReconnectRef.current && !wsRef.current) connectWebSocket();
    }, 200);
  }, [connectWebSocket]);

  useEffect(() => {
    shouldReconnectRef.current = true;
    connectWebSocket();
    return () => {
      shouldReconnectRef.current = false;
      clearTimeout(reconnectTimerRef.current);
      const socket = wsRef.current;
      wsRef.current = null;
      if (socket) {
        try {
          socket.close(1000, '组件卸载');
        } catch {
          /* 忽略 */
        }
      }
    };
  }, [connectWebSocket]);

  const getChartOption = useCallback(() => {
    const xData = advantageHistory.map((item) => `第${item.step}步`);
    const yData = advantageHistory.map((item) => item.score);

    return {
      title: {
        text: '棋局优势变化（白方视角）',
        left: 'center',
        textStyle: { fontSize: 14, fontWeight: 'normal' },
      },
      tooltip: {
        trigger: 'axis',
        formatter: (params) => {
          const item = advantageHistory[params[0].dataIndex];
          if (!item) return '';
          return `
            <div>
              <p>步数：第${item.step}步</p>
              <p>优势分值：${item.score}</p>
              <p>优势方：${formatAdvantage(item.advantage, item.score, item.mateIn)}</p>
            </div>
          `;
        },
      },
      grid: { left: '3%', right: '4%', bottom: '3%', containLabel: true },
      xAxis: { type: 'category', data: xData, axisLabel: { fontSize: 12 } },
      yAxis: {
        type: 'value',
        name: '优势分值',
        nameTextStyle: { fontSize: 12 },
        axisLabel: { fontSize: 12 },
        min: -100,
        max: 100,
        splitLine: { lineStyle: { color: '#ccc' } },
        markLine: {
          data: [
            { yAxis: 0, name: '均衡', lineStyle: { color: '#f00', type: 'solid' } },
            { yAxis: 1, name: '白棋优势', lineStyle: { color: '#66ccff', type: 'dashed' } },
            { yAxis: -1, name: '黑棋优势', lineStyle: { color: '#333333', type: 'dashed' } },
          ],
        },
      },
      series: [
        {
          name: '优势分值',
          type: 'line',
          data: yData,
          smooth: true,
          itemStyle: {
            color: (params) => {
              if (params.value > 0) return '#66ccff';
              if (params.value < 0) return '#333333';
              return '#999999';
            },
          },
          lineStyle: { width: 2 },
          symbol: 'circle',
          symbolSize: 6,
          areaStyle: {
            color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
              { offset: 0, color: 'rgba(102, 204, 255, 0.3)' },
              { offset: 1, color: 'rgba(102, 204, 255, 0.1)' },
            ]),
          },
        },
      ],
      backgroundColor: 'transparent',
    };
  }, [advantageHistory]);

  const headerStatus = () => {
    if (connectionStatus === 'connected') return { className: 'connected', text: '✅ 已连接' };
    if (connectionStatus === 'connecting') return { className: 'connecting', text: '🔄 连接中…' };
    return { className: 'error', text: '❌ 已断开' };
  };

  const renderAnalysis = () => {
    if (analysisData && !analysisData.success) {
      return (
        <div className="analysis-error">
          {analysisData.engine_available === false
            ? 'Stockfish 引擎不可用，请在服务端检查 STOCKFISH_PATH'
            : analysisData.error || '分析失败'}
        </div>
      );
    }
    if (!analysisData) {
      return (
        <div className="analysis-loading">
          {analysisPending ? '引擎分析中…' : '等待局面数据…'}
        </div>
      );
    }
    return (
      <div className="analysis-content">
        <div className="advantage-item">
          <span className="label">当前优势：</span>
          <span className={`value advantage-${analysisData.advantage}`}>
            {formatAdvantage(analysisData.advantage, analysisData.advantage_score, analysisData.mate_in)}
          </span>
        </div>
        <div className="best-moves">
          <div className="best-move-item white">
            <span className="label">白棋最佳：</span>
            <span className="value">{analysisData.white_best_move || '——'}</span>
          </div>
          <div className="best-move-item black">
            <span className="label">黑棋最佳：</span>
            <span className="value">{analysisData.black_best_move || '——'}</span>
          </div>
          <div className="best-move-item current">
            <span className="label">当前最佳：</span>
            <span className="value highlight">{analysisData.current_best_move || '——'}</span>
          </div>
        </div>
        <div className="analysis-meta">
          深度 {analysisData.depth}
          {analysisData.cached ? ' · 命中缓存' : ''}
          {analysisPending ? ' · 正在更新…' : ''}
        </div>
      </div>
    );
  };

  const status = headerStatus();
  const gameInfo = statusData?.game_info;

  return (
    <div className="game-status-widget">
      <div className="widget-header">
        <h3>📊 实时棋局分析</h3>
        <div className="header-right">
          {gameInfo?.game_id && <span className="game-id">对局ID: {gameInfo.game_id.slice(-6)}</span>}
          <span className={`connection-status ${status.className}`}>{status.text}</span>
        </div>
      </div>

      <div className="widget-content">
        <div className="content-left">
          <div className="status-section analysis">
            <h4>🎯 当前分析</h4>
            {renderAnalysis()}
          </div>

          {gameInfo && (
            <div className="status-section">
              <h4>ℹ️ 对局信息</h4>
              <div className="analysis-content">
                <div className="advantage-item">
                  <span className="label">模式：</span>
                  <span className="value">
                    {gameInfo.mode === 'ai'
                      ? `人机（你执${gameInfo.player_color === 'white' ? '白' : '黑'}棋 · ${gameInfo.ai_level}）`
                      : gameInfo.mode === 'self'
                        ? '自我博弈'
                        : '未选择'}
                  </span>
                </div>
                <div className="advantage-item">
                  <span className="label">状态：</span>
                  <span className="value">
                    {statusData?.board_state?.turn === 'white' ? '白棋行棋' : '黑棋行棋'} · {gameInfo.result}
                  </span>
                </div>
                <div className="advantage-item">
                  <span className="label">着数：</span>
                  <span className="value">{statusData?.statistics?.total_moves ?? 0}</span>
                </div>
              </div>
            </div>
          )}
        </div>

        <div className="content-right">
          <div className="status-section advantage-chart">
            <h4>📈 优势变化</h4>
            <div className="chart-container">
              {advantageHistory.length === 0 ? (
                <div className="chart-empty">暂无优势数据，开始走棋后显示曲线</div>
              ) : (
                <ReactECharts
                  option={getChartOption()}
                  style={{ height: '100%', width: '100%' }}
                  echarts={echarts}
                  opts={{ renderer: 'canvas' }}
                />
              )}
            </div>
          </div>
        </div>
      </div>

      <div className="widget-footer">
        {errorMsg ? (
          <span className="update-time error-text">{errorMsg}</span>
        ) : (
          <span className="update-time">
            {statusData?.board_state?.turn
              ? `当前回合：${statusData.board_state.turn === 'white' ? '白棋' : '黑棋'}`
              : '等待数据'}
          </span>
        )}
        <button onClick={handleRefresh} className="refresh-btn">
          🔄 刷新
        </button>
      </div>
    </div>
  );
});

GameStatusWidget.displayName = 'GameStatusWidget';

export default GameStatusWidget;
