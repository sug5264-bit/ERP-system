"use client";
import { useWS } from "@/lib/ws";

export default function Toasts() {
  const { toasts, dismissToast } = useWS();
  if (toasts.length === 0) return null;
  return (
    <div className="fixed top-4 right-4 z-50 space-y-2 max-w-sm">
      {toasts.map((t) => (
        <div
          key={t.id}
          className={`px-4 py-3 rounded-lg shadow-lg border text-sm flex justify-between items-start gap-3 ${
            t.level === "error"
              ? "bg-red-50 border-red-200 text-red-800 dark:bg-red-900 dark:border-red-700 dark:text-red-100"
              : t.level === "success"
              ? "bg-green-50 border-green-200 text-green-800 dark:bg-green-900 dark:border-green-700 dark:text-green-100"
              : "bg-white border-slate-200 text-slate-800 dark:bg-slate-800 dark:border-slate-700 dark:text-slate-100"
          }`}
        >
          <span>{t.text}</span>
          <button
            onClick={() => dismissToast(t.id)}
            className="text-xs opacity-60 hover:opacity-100"
          >
            ✕
          </button>
        </div>
      ))}
    </div>
  );
}
