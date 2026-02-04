import { useState, useEffect, useRef, useCallback, forwardRef, useImperativeHandle } from 'react';
import ReactECharts from 'echarts-for-react';
import * as echarts from 'echarts';
import { API_BASE_URL } from '../constants/backend_config.js';
import './GameStatusWidget.css';

const formatAdvantage = (advantage, score) => {
  const advantageMap = {
    'white_winning': '白棋必胜',
    'black_winning': '黑棋必胜',
    'white_advantage': '白棋明显优势',
    'black_advantage': '黑棋明显优势',
    'slight_white_advantage': '白棋小幅优势',
    'slight_black_advantage': '黑棋小幅优势',
    'equal': '双方势均力敌',
    'unknown': '无法分析'
  };
  
  let scoreText = '';
  if (score === 100) scoreText = '（白棋将死）';
  else if (score === -100) scoreText = '（黑棋将死）';
  else if (score !== 0) scoreText = `（分值：${score}）`;
  
  return `${advantageMap[advantage]} ${scoreText}`;
};

// 防抖函数
const debounce = (func, delay) => {
  let timeoutId;
  const debouncedFunc = (...args) => {
    clearTimeout(timeoutId);
    timeoutId = setTimeout(() => func.apply(this, args), delay);
  };
  // 增加取消方法
  debouncedFunc.cancel = () => clearTimeout(timeoutId);
  return debouncedFunc;
};

// 用forwardRef包装，暴露重置方法
const GameStatusWidget = forwardRef((props, ref) => {
  // 核心状态
  const [statusData, setStatusData] = useState(null);
  const [analysisData, setAnalysisData] = useState(null);
  const [connectionStatus, setConnectionStatus] = useState('idle'); // idle/connecting/connected/disconnected
  const [errorMsg, setErrorMsg] = useState('');
  const [advantageHistory, setAdvantageHistory] = useState([]); // 优势历史（K线图）
  const [currentGameId, setCurrentGameId] = useState(''); // 当前对局ID，用于自动识别新对局
  
  // 关键ref
  const wsRef = useRef(null);
  const reconnectTimerRef = useRef(null);
  const isConnectedRef = useRef(false);
  const isInReconnectRef = useRef(false);
  const updateDataDebouncedRef = useRef(null);

  // --- 核心：重置游戏数据方法（对外暴露）---
  const resetGameData = useCallback(() => {
    console.log('执行游戏数据重置');
    // 1. 清空所有历史数据
    setAdvantageHistory([]);
    setAnalysisData(null);
    setErrorMsg('');
    setCurrentGameId('');
    
    // 2. 清空对局状态（保留基础结构，避免页面闪烁）
    if (statusData) {
      setStatusData(prev => ({
        ...prev,
        move_history: [],
        game_info: {
          ...prev.game_info,
          game_id: '',
          result: 'ongoing'
        }
      }));
    }
    
    // 3. 关闭现有WS连接，重新建立（确保获取新对局数据）
    if (wsRef.current) {
      try {
        wsRef.current.close(1000, '游戏重置，重新连接');
      } catch (e) {
        console.error('关闭WS连接失败:', e);
      }
      wsRef.current = null;
      isConnectedRef.current = false;
    }
    
    // 4. 清除重连定时器，重新连接
    if (reconnectTimerRef.current) {
      clearTimeout(reconnectTimerRef.current);
      reconnectTimerRef.current = null;
    }
    
    // 5. 延迟重连，避免连接冲突
    setTimeout(() => {
      connectWebSocket();
    }, 500);
  }, []);

  // 暴露重置方法给父组件
  useImperativeHandle(ref, () => ({
    resetGameData
  }));

  // 初始化防抖函数
  useEffect(() => {
    updateDataDebouncedRef.current = debounce((data) => {
      // 自动识别新对局：如果对局ID变化，清空历史
      const newGameId = data.status?.game_info?.game_id || '';
      if (currentGameId && newGameId && newGameId !== currentGameId) {
        setAdvantageHistory([]);
        setCurrentGameId(newGameId);
        console.log('检测到新对局，自动清空历史数据');
      } else if (!currentGameId && newGameId) {
        setCurrentGameId(newGameId);
      }

      // 更新数据
      if (data.status) setStatusData(data.status);
      if (data.analysis) {
        setAnalysisData(data.analysis);
        // 记录优势变化历史（只保留最近20步）
        if (data.analysis.success) {
          setAdvantageHistory(prev => {
            const newHistory = [
              ...prev, 
              {
                step: prev.length + 1,
                score: data.analysis.advantage_score,
                advantage: data.analysis.advantage,
                timestamp: new Date().getTime(),
                gameId: newGameId
              }
            ];
            return newHistory.slice(-20);
          });
        }
      }
      setErrorMsg('');
    }, 100);
    
    // 组件卸载时清理防抖
    return () => {
      if (updateDataDebouncedRef.current) {
        updateDataDebouncedRef.current.cancel();
      }
    };
  }, [currentGameId]);

  // 构建WS连接地址
  const getWsUrl = useCallback(() => {
    try {
      const url = new URL(API_BASE_URL);
      const wsProtocol = url.protocol === 'https:' ? 'wss:' : 'ws:';
      return `${wsProtocol}//${url.host}/ws/game`;
    } catch (e) {
      return API_BASE_URL.replace(/^http(s)?:\/\//, 'ws$1://') + '/ws/game';
    }
  }, [API_BASE_URL]);

  // 建立WS连接
  const connectWebSocket = useCallback(() => {
    // 防止重复连接
    if (wsRef.current || isConnectedRef.current || isInReconnectRef.current) {
      console.log('WS连接已存在/正在连接，跳过重复创建');
      return;
    }

    const wsUrl = getWsUrl();
    console.log('尝试连接WebSocket:', wsUrl);
    
    setConnectionStatus('connecting');
    isInReconnectRef.current = true;
    
    const ws = new WebSocket(wsUrl);
    wsRef.current = ws;

    // 连接成功
    ws.onopen = () => {
      console.log('WebSocket 连接成功');
      isConnectedRef.current = true;
      isInReconnectRef.current = false;
      setConnectionStatus('connected');
      setErrorMsg('');
      
      if (reconnectTimerRef.current) {
        clearTimeout(reconnectTimerRef.current);
        reconnectTimerRef.current = null;
      }
    };

    // 接收消息
    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        console.log('收到WS消息:', data.type);
        
        if (data.type === 'full_update' && updateDataDebouncedRef.current) {
          updateDataDebouncedRef.current(data);
        } else if (data.type === 'error') {
          setErrorMsg(`服务器错误：${data.message}`);
        }
      } catch (err) {
        console.error('解析WS数据失败:', err);
        setErrorMsg(`数据解析失败：${err.message}`);
      }
    };

    // 连接关闭
    ws.onclose = (event) => {
      console.log('WebSocket 连接关闭', event.code, event.reason);
      
      isConnectedRef.current = false;
      wsRef.current = null;
      
      // 正常关闭（不重连）
      if (event.code === 1000 || event.code === 1005) {
        setConnectionStatus('idle');
        if (event.code !== 1000) {
          setErrorMsg(`连接已关闭：${event.reason || '正常关闭'}`);
        }
        return;
      }
      
      // 异常关闭（重连）
      setConnectionStatus('disconnected');
      setErrorMsg(`连接断开（码：${event.code}）：${event.reason || '网络异常'}`);
      
      if (!isInReconnectRef.current) {
        reconnectTimerRef.current = setTimeout(() => {
          if (!isConnectedRef.current) {
            connectWebSocket();
          }
        }, 5000);
      }
    };

    // 连接错误
    ws.onerror = (err) => {
      console.error('WebSocket 错误:', err);
      setErrorMsg(`连接出错：${err.message || '未知错误'}`);
    };
    
  }, [getWsUrl]);

  // 手动刷新连接
  const handleRefresh = useCallback(() => {
    console.log('手动刷新WS连接');
    
    if (wsRef.current) {
      try {
        wsRef.current.close(1000, '手动刷新');
      } catch (e) {}
      wsRef.current = null;
      isConnectedRef.current = false;
    }
    
    if (reconnectTimerRef.current) {
      clearTimeout(reconnectTimerRef.current);
      reconnectTimerRef.current = null;
    }
    
    setTimeout(connectWebSocket, 1000);
  }, [connectWebSocket]);

  // 组件挂载/卸载
  useEffect(() => {
    connectWebSocket();

    return () => {
      console.log('组件卸载，清理WS连接');
      
      if (reconnectTimerRef.current) {
        clearTimeout(reconnectTimerRef.current);
      }
      
      if (wsRef.current) {
        try {
          wsRef.current.close(1000, '组件卸载');
        } catch (e) {
          console.error('关闭WS连接失败:', e);
        }
        wsRef.current = null;
      }
      
      isConnectedRef.current = false;
      isInReconnectRef.current = false;
      
      // 清理防抖
      if (updateDataDebouncedRef.current) {
        updateDataDebouncedRef.current.cancel();
      }
    };
  }, [connectWebSocket]);

  // K线图配置
  const getChartOption = useCallback(() => {
    const xData = advantageHistory.map(item => `第${item.step}步`);
    const yData = advantageHistory.map(item => item.score);
    
    return {
      title: {
        text: '棋局优势变化',
        left: 'center',
        textStyle: { fontSize: 14, fontWeight: 'normal' }
      },
      tooltip: {
        trigger: 'axis',
        formatter: (params) => {
          const item = advantageHistory[params[0].dataIndex];
          return `
            <div>
              <p>步数：第${item.step}步</p>
              <p>优势分值：${item.score}</p>
              <p>优势方：${formatAdvantage(item.advantage, item.score)}</p>
            </div>
          `;
        }
      },
      grid: { left: '3%', right: '4%', bottom: '3%', containLabel: true },
      xAxis: {
        type: 'category',
        data: xData,
        axisLabel: { fontSize: 12 }
      },
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
            { yAxis: -1, name: '黑棋优势', lineStyle: { color: '#333333', type: 'dashed' } }
          ]
        }
      },
      series: [
        {
          name: '优势分值',
          type: 'line',
          data: yData,
          smooth: true,
          itemStyle: {
            color: (params) => {
              const value = params.value;
              if (value > 0) return '#66ccff';
              if (value < 0) return '#333333';
              return '#999999';
            }
          },
          lineStyle: { width: 2 },
          symbol: 'circle',
          symbolSize: 6,
          areaStyle: {
            color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
              { offset: 0, color: 'rgba(102, 204, 255, 0.3)' },
              { offset: 1, color: 'rgba(102, 204, 255, 0.1)' }
            ])
          }
        }
      ],
      backgroundColor: 'transparent'
    };
  }, [advantageHistory]);

  // 加载状态
  if (connectionStatus === 'connecting' || (connectionStatus === 'idle' && !statusData)) {
    return (
      <div className="game-status-widget">
        <div className="widget-header">
          <h3>📊 实时棋局分析</h3>
          <span className="connection-status connecting">🔄 连接中...</span>
        </div>
        <div className="widget-content">
          <div className="loading-container">
            <div className="loading-text">正在建立实时连接...</div>
            <div className="debug-info">连接地址：{getWsUrl()}</div>
          </div>
        </div>
        <div className="widget-footer">
          <span className="update-time">未连接</span>
          <button onClick={handleRefresh} className="refresh-btn" disabled>🔄 刷新</button>
        </div>
      </div>
    );
  }

  // 错误状态
  if (connectionStatus === 'disconnected' || errorMsg) {
    return (
      <div className="game-status-widget">
        <div className="widget-header">
          <h3>📊 实时棋局分析</h3>
          <span className="connection-status error">❌ 已断开</span>
        </div>
        <div className="widget-content">
          <div className="error-container">
            <div className="error-text">{errorMsg || '连接已断开'}</div>
            <button onClick={handleRefresh} className="retry-btn">重新连接</button>
          </div>
        </div>
        <div className="widget-footer">
          <span className="update-time">最后更新：——</span>
          <button onClick={handleRefresh} className="refresh-btn">🔄 刷新</button>
        </div>
      </div>
    );
  }

  // 无数据状态
  if (!statusData) {
    return (
      <div className="game-status-widget">
        <div className="widget-header">
          <h3>📊 实时棋局分析</h3>
          <span className="connection-status connected">✅ 已连接</span>
        </div>
        <div className="widget-content">
          <div className="loading-container">
            <div className="loading-text">等待数据推送...</div>
          </div>
        </div>
        <div className="widget-footer">
          <span className="update-time">最后更新：——</span>
          <button onClick={handleRefresh} className="refresh-btn">🔄 刷新</button>
        </div>
      </div>
    );
  }

  // 正常渲染
  const { board_state, game_info } = statusData;
  return (
    <div className="game-status-widget">
      <div className="widget-header">
        <h3>📊 实时棋局分析</h3>
        <div className="header-right">
          <span className="game-id">对局ID: {game_info.game_id?.slice(-6) || '未知'}</span>
          <span className={`connection-status ${connectionStatus}`}>
            {connectionStatus === 'connected' ? '✅ 已连接' : '🔄 重连中'}
          </span>
        </div>
      </div>

      {/* 核心修改：水平排列的内容区域 */}
      <div className="widget-content">
        {/* 左侧：基础信息 + 当前分析（垂直排列） */}
        <div className="content-left">
          {/* 基础信息 */}

          {/* 当前分析 */}
          <div className="status-section analysis">
            <h4>🎯 当前分析</h4>
            {!analysisData ? (
              <div className="analysis-loading">分析数据加载中...</div>
            ) : !analysisData.success ? (
              <div className="analysis-error">{analysisData.error || '分析失败'}</div>
            ) : (
              <div className="analysis-content">
                <div className="advantage-item">
                  <span className="label">当前优势：</span>
                  <span className={`value advantage-${analysisData.advantage}`}>
                    {formatAdvantage(analysisData.advantage, analysisData.advantage_score)}
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
              </div>
            )}
          </div>
        </div>

        {/* 右侧：K线图（占主要宽度） */}
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
        <span className="update-time">最后更新：{new Date().toLocaleTimeString('zh-CN')}</span>
        <button onClick={handleRefresh} className="refresh-btn">🔄 刷新</button>
      </div>
    </div>
  );
});

export default GameStatusWidget;