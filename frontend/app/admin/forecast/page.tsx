"use client";
import { useEffect, useState } from "react";
import AppShell from "@/components/AppShell";
import { BarChart } from "@/components/charts";
import { api } from "@/lib/api";

type Item = { id: number; sku: string; name: string; stock_qty: string };

type Forecast = {
  item: { id: number; sku: string; name: string; stock_qty: number };
  moving_avg_per_day: number;
  trend_per_day: number;
  forecast: { day: string; qty: number }[];
  predicted_total: number;
  days_of_stock_remaining: number | null;
  reorder_point: number;
  suggested_reorder_qty: number;
};

export default function ForecastPage() {
  const [items, setItems] = useState<Item[]>([]);
  const [itemId, setItemId] = useState("");
  const [forecast, setForecast] = useState<Forecast | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    api<Item[]>("/api/inventory/items")
      .then((xs) => {
        setItems(xs);
        if (xs[0]) setItemId(String(xs[0].id));
      })
      .catch((e) => setError(String(e)));
  }, []);

  useEffect(() => {
    if (!itemId) return;
    api<Forecast>(`/api/forecast/items/${itemId}?history_days=60&horizon_days=14`)
      .then(setForecast)
      .catch((e) => setError(String(e)));
  }, [itemId]);

  return (
    <AppShell>
      <h1 className="text-2xl font-semibold mb-4">재고 예측</h1>

      <div className="bg-white p-4 rounded-lg border border-slate-200 mb-6 flex items-center gap-3">
        <span className="text-sm text-slate-600">품목</span>
        <select
          value={itemId}
          onChange={(e) => setItemId(e.target.value)}
          className="border rounded px-2 py-1 text-sm flex-1"
        >
          {items.map((i) => (
            <option key={i.id} value={i.id}>
              {i.sku} - {i.name}
            </option>
          ))}
        </select>
      </div>

      {error && <p className="text-red-600 text-sm mb-3">{error}</p>}

      {forecast && (
        <>
          <div className="grid grid-cols-2 md:grid-cols-5 gap-3 mb-6">
            <Stat label="현재 재고" value={forecast.item.stock_qty.toLocaleString()} />
            <Stat label="평균 일 출고" value={forecast.moving_avg_per_day} />
            <Stat label="추세 (일/일)" value={forecast.trend_per_day} />
            <Stat
              label="잔여 일수"
              value={forecast.days_of_stock_remaining ?? "—"}
              highlight={
                forecast.days_of_stock_remaining !== null &&
                forecast.days_of_stock_remaining < 14
              }
            />
            <Stat
              label="권장 재주문"
              value={forecast.suggested_reorder_qty}
              highlight={forecast.suggested_reorder_qty > 0}
            />
          </div>

          <div className="bg-white p-4 rounded-lg border border-slate-200">
            <h2 className="font-medium mb-2">14일 예측 (일별 출고량)</h2>
            <BarChart
              data={forecast.forecast.map((p) => ({
                label: p.day.slice(5),
                value: p.qty,
              }))}
            />
          </div>
        </>
      )}
    </AppShell>
  );
}

function Stat({
  label,
  value,
  highlight,
}: {
  label: string;
  value: string | number;
  highlight?: boolean;
}) {
  return (
    <div
      className={`bg-white p-3 rounded-lg border ${
        highlight ? "border-amber-300" : "border-slate-200"
      }`}
    >
      <div className="text-xs text-slate-500">{label}</div>
      <div
        className={`text-xl font-semibold mt-1 ${highlight ? "text-amber-700" : ""}`}
      >
        {value}
      </div>
    </div>
  );
}
