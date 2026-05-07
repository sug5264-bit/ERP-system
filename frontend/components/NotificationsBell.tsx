"use client";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { useWS } from "@/lib/ws";

type Notif = {
  id: string;
  level: "info" | "warning" | "error";
  type: string;
  title: string;
  message: string;
  module: string;
  ref_id: number;
};

export default function NotificationsBell() {
  const [items, setItems] = useState<Notif[]>([]);
  const [open, setOpen] = useState(false);
  const { history, unreadCount, markAllRead } = useWS();

  const load = () =>
    api<{ count: number; items: Notif[] }>("/api/notifications")
      .then((r) => setItems(r.items))
      .catch(() => setItems([]));

  useEffect(() => {
    load();
    const id = setInterval(load, 30000);
    return () => clearInterval(id);
  }, []);

  // Mark history read when the dropdown opens.
  useEffect(() => {
    if (open) markAllRead();
  }, [open]);

  const totalBadge = items.length + unreadCount;

  const levelColor = (l: Notif["level"]) =>
    l === "error"
      ? "bg-red-100 text-red-700"
      : l === "warning"
      ? "bg-amber-100 text-amber-700"
      : "bg-slate-100 text-slate-700";

  return (
    <div className="relative">
      <button
        onClick={() => setOpen((v) => !v)}
        className="relative px-2 py-1 rounded hover:bg-slate-100"
        title="Notifications"
      >
        🔔
        {totalBadge > 0 && (
          <span className="absolute -top-1 -right-1 bg-red-600 text-white text-xs rounded-full w-5 h-5 flex items-center justify-center">
            {totalBadge > 9 ? "9+" : totalBadge}
          </span>
        )}
      </button>
      {open && (
        <div className="absolute right-0 mt-1 w-80 bg-white border border-slate-200 rounded-lg shadow-lg z-20 max-h-[28rem] overflow-y-auto">
          <div className="px-3 py-2 border-b font-medium text-sm">
            현재 알림 ({items.length})
          </div>
          {items.length === 0 ? (
            <div className="p-3 text-xs text-slate-500 text-center">새 알림 없음</div>
          ) : (
            <ul>
              {items.map((n) => (
                <li key={n.id} className="px-3 py-2 border-b last:border-b-0 hover:bg-slate-50">
                  <div className="flex items-center justify-between gap-2">
                    <span className={`text-xs px-2 py-0.5 rounded uppercase ${levelColor(n.level)}`}>
                      {n.level}
                    </span>
                    <span className="text-xs text-slate-500">{n.module}</span>
                  </div>
                  <div className="text-sm font-medium mt-1">{n.title}</div>
                  <div className="text-xs text-slate-600">{n.message}</div>
                </li>
              ))}
            </ul>
          )}

          <div className="px-3 py-2 border-t font-medium text-sm bg-slate-50">
            최근 푸시 (50개)
          </div>
          {history.length === 0 ? (
            <div className="p-3 text-xs text-slate-500 text-center">기록 없음</div>
          ) : (
            <ul>
              {history.map((h) => (
                <li
                  key={h.id}
                  className={`px-3 py-2 border-b last:border-b-0 ${
                    h.read ? "opacity-60" : ""
                  }`}
                >
                  <div className="flex items-center justify-between text-xs">
                    <span className="text-slate-500">
                      {new Date(h.ts).toLocaleString()}
                    </span>
                    {!h.read && (
                      <span className="text-brand-700 font-medium">●</span>
                    )}
                  </div>
                  <div className="text-sm">{h.text}</div>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}
