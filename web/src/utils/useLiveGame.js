import { useEffect, useRef } from 'react';
import { buildWsUrl } from '../constants/backend_config.js';

const RECONNECT_BASE_MS = 1500;
const RECONNECT_MAX_MS = 15000;

/**
 * 订阅本进程正在进行的那一局。
 * 地址不带 game_id：服务端把所有这样的连接挂到同一局，重置时再迁到新局。
 * @param {(snapshot: object) => void} onSnapshot
 * @param {(connected: boolean) => void} [onConnection]
 */
export function useLiveGame(onSnapshot, onConnection) {
  const onSnapshotRef = useRef(onSnapshot);
  const onConnectionRef = useRef(onConnection);
  onSnapshotRef.current = onSnapshot;
  onConnectionRef.current = onConnection;

  useEffect(() => {
    let stopped = false;
    let socket = null;
    let timer = null;
    let attempt = 0;

    const connect = () => {
      if (stopped) return;
      let next;
      try {
        next = new WebSocket(buildWsUrl());
      } catch {
        onConnectionRef.current?.(false);
        return;
      }
      socket = next;

      next.onopen = () => {
        if (stopped) return;
        attempt = 0;
        onConnectionRef.current?.(true);
      };

      next.onmessage = (event) => {
        if (stopped) return;
        let data;
        try {
          data = JSON.parse(event.data);
        } catch {
          return;
        }
        if (data.type === 'hello' || data.type === 'status_update') {
          if (data.status) onSnapshotRef.current(data.status);
        }
      };

      next.onclose = () => {
        socket = null;
        if (stopped) return;
        onConnectionRef.current?.(false);
        const delay = Math.min(RECONNECT_BASE_MS * 2 ** attempt, RECONNECT_MAX_MS);
        attempt += 1;
        timer = setTimeout(connect, delay);
      };
    };

    connect();
    return () => {
      stopped = true;
      clearTimeout(timer);
      if (socket) {
        try {
          socket.close(1000, '组件卸载');
        } catch {
          /* 连接可能已经断开 */
        }
      }
    };
  }, []);
}
