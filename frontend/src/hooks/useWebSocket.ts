import { useEffect, useRef, useState, useCallback } from 'react';

interface WSMessage {
  type: string;
  [key: string]: unknown;
}

export function useWebSocket(url: string) {
  const [lastMessage, setLastMessage] = useState<WSMessage | null>(null);
  const [connected, setConnected] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);

  const connect = useCallback(() => {
    const ws = new WebSocket(url);

    ws.onopen = () => {
      setConnected(true);
    };

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        setLastMessage(data);
      } catch {
        /* ignore non-JSON messages */
      }
    };

    ws.onclose = () => {
      setConnected(false);
      setTimeout(connect, 3000);
    };

    wsRef.current = ws;
  }, [url]);

  useEffect(() => {
    connect();
    return () => {
      wsRef.current?.close();
    };
  }, [connect]);

  const send = useCallback((msg: WSMessage) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(msg));
    }
  }, []);

  return { lastMessage, connected, send };
}
