"use client";
import { createContext, useContext, useEffect, useRef, useState, ReactNode } from "react";
import { getToken } from "./api";

export type WSMessage = {
  type: string;
  [key: string]: unknown;
};

type Toast = { id: number; level: "info" | "success" | "error"; text: string };

const WSContext = createContext<{
  lastMessage: WSMessage | null;
  toasts: Toast[];
  pushToast: (level: Toast["level"], text: string) => void;
  dismissToast: (id: number) => void;
}>({
  lastMessage: null,
  toasts: [],
  pushToast: () => {},
  dismissToast: () => {},
});

export function WSProvider({ children }: { children: ReactNode }) {
  const [lastMessage, setLastMessage] = useState<WSMessage | null>(null);
  const [toasts, setToasts] = useState<Toast[]>([]);
  const wsRef = useRef<WebSocket | null>(null);
  const idRef = useRef(0);

  const pushToast = (level: Toast["level"], text: string) => {
    const id = ++idRef.current;
    setToasts((prev) => [...prev, { id, level, text }]);
    setTimeout(() => setToasts((prev) => prev.filter((t) => t.id !== id)), 5000);
  };

  const dismissToast = (id: number) => setToasts((prev) => prev.filter((t) => t.id !== id));

  useEffect(() => {
    const token = getToken();
    if (!token || typeof window === "undefined") return;

    const apiBase = process.env.NEXT_PUBLIC_API_BASE || window.location.origin;
    const wsUrl =
      apiBase.replace(/^http/, "ws") + `/api/notifications/ws?token=${encodeURIComponent(token)}`;

    let stopped = false;
    let reconnectDelay = 1000;

    const connect = () => {
      if (stopped) return;
      const ws = new WebSocket(wsUrl);
      wsRef.current = ws;

      ws.onmessage = (e) => {
        try {
          const data = JSON.parse(e.data) as WSMessage;
          setLastMessage(data);

          if (data.type === "approval.requested") {
            pushToast("info", `결재 요청: ${data.title} (요청자 ${data.requester})`);
          } else if (data.type === "approval.approved") {
            pushToast("success", `${data.title} 승인 (${data.by})`);
          } else if (data.type === "approval.rejected") {
            pushToast("error", `${data.title} 반려 (${data.by})`);
          }
        } catch {}
      };

      ws.onclose = () => {
        wsRef.current = null;
        if (stopped) return;
        setTimeout(connect, reconnectDelay);
        reconnectDelay = Math.min(reconnectDelay * 2, 30000);
      };

      ws.onopen = () => {
        reconnectDelay = 1000;
      };
    };

    connect();

    return () => {
      stopped = true;
      wsRef.current?.close();
    };
  }, []);

  return (
    <WSContext.Provider value={{ lastMessage, toasts, pushToast, dismissToast }}>
      {children}
    </WSContext.Provider>
  );
}

export function useWS() {
  return useContext(WSContext);
}
