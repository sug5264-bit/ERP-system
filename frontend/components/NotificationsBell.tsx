"use client";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";

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

  const load = () =>
    api<{ count: number; items: Notif[] }>("/api/notifications")
      .then((r) => setItems(r.items))
      .catch(() => setItems([]));

  useEffect(() => {
    load();
    const id = setInterval(load, 30000);
    return () => clearInterval(id);
  }, []);

  const levelColor = (l: Notif["level"]) =>
    l === "error" ? "bg-red-100 text-red-700"
    : l === "warning" ? "bg-amber-100 text-amber-700"
    : "bg-slate-100 text-slate-700";

  return (
    <div className="relative">
      <button
        onClick={() => setOpen((v) => !v)}
        className="relative px-2 py-1 rounded hover:bg-slate-100"
        title="Notifications"
      >
        🔔
        {items.length > 0 && (
          <span className="absolute -top-1 -right-1 bg-red-600 text-white text-xs rounded-full w-5 h-5 flex items-center justify-center">
            {items.length > 9 ? "9+" : items.length}
          </span>
        )}
      </button>
      {open && (
        <div className="absolute right-0 mt-1 w-80 bg-white border border-slate-200 rounded-lg shadow-lg z-20 max-h-96 overflow-y-auto">
          <div className="px-3 py-2 border-b font-medium text-sm">알림 ({items.length})</div>
          {items.length === 0 ? (
            <div className="p-4 text-sm text-slate-500 text-center">새 알림 없음</div>
          ) : (
            <ul>
              {items.map((n) => (
                <li key={n.id} className="px-3 py-2 border-b last:border-b-0 hover:bg-slate-50">
                  <div className="flex items-center justify-between gap-2">
                    <span
                      className={`text-xs px-2 py-0.5 rounded uppercase ${levelColor(n.level)}`}
                    >
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
        </div>
      )}
    </div>
  );
}
