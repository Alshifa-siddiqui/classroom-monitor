import { useEffect, useRef, useState, useCallback } from 'react';
import { wsUrl } from './api';

export function useWebSocket(active = true) {
  const [connected, setConnected] = useState(false);
  const [frame, setFrame] = useState(null);
  const [analytics, setAnalytics] = useState(null);
  const [liveAlerts, setLiveAlerts] = useState([]);
  const wsRef = useRef(null);
  const retryRef = useRef(null);

  const connect = useCallback(() => {
    const ws = new WebSocket(wsUrl());
    wsRef.current = ws;

    ws.onopen = () => setConnected(true);
    ws.onmessage = (event) => {
      const msg = JSON.parse(event.data);
      if (msg.type === 'frame') {
        setFrame(`data:image/jpeg;base64,${msg.data}`);
      } else if (msg.type === 'analytics') {
        setAnalytics(msg);
      } else if (msg.type === 'alert') {
        setLiveAlerts((prev) => [msg.alert, ...prev].slice(0, 50));
      } else if (msg.type === 'session_ended') {
        // clear the frozen last frame and live stats so the UI reflects
        // that the camera and session have actually stopped
        setFrame(null);
        setAnalytics(null);
      }
    };
    ws.onclose = () => {
      setConnected(false);
      retryRef.current = setTimeout(connect, 2000);
    };
    ws.onerror = () => ws.close();
  }, []);

  useEffect(() => {
    if (!active) return undefined;
    connect();
    return () => {
      clearTimeout(retryRef.current);
      if (wsRef.current) {
        wsRef.current.onclose = null;
        wsRef.current.close();
      }
    };
  }, [connect, active]);

  return { connected, frame, analytics, liveAlerts };
}
