"use client";
import { useEffect, useState } from "react";
import AppShell from "@/components/AppShell";
import { api } from "@/lib/api";

type PassRate = {
  window_days: number;
  stages: { stage: string; total: number; passed: number; pass_rate: number }[];
};

type Pareto = {
  defects: { defect_type: string; count: number; quantity: number; cumulative_pct: number }[];
  total_quantity: number;
};

export default function QCPage() {
  const [pr, setPr] = useState<PassRate | null>(null);
  const [pareto, setPareto] = useState<Pareto | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    (async () => {
      try {
        setPr(await api<PassRate>("/api/qc/pass-rate?days=30"));
        setPareto(await api<Pareto>("/api/qc/defect-pareto?days=30"));
      } catch (e) { setError(String(e)); }
    })();
  }, []);

  return (
    <AppShell>
      <h1 className="text-2xl font-semibold mb-4">품질관리 / QC</h1>
      {error && <p className="text-red-600 text-sm mb-3">{error}</p>}

      <div className="bg-white p-4 rounded-lg border border-slate-200 mb-4">
        <h2 className="text-lg font-medium mb-3">단계별 합격률 (최근 30일)</h2>
        {pr ? (
          <div className="grid grid-cols-3 gap-3">
            {pr.stages.map((s) => (
              <div key={s.stage} className="border rounded p-3 text-center">
                <div className="text-xs text-slate-500">{s.stage}</div>
                <div className="text-2xl font-semibold text-emerald-700">
                  {(s.pass_rate * 100).toFixed(1)}%
                </div>
                <div className="text-xs text-slate-500 mt-1">
                  {s.passed} / {s.total}
                </div>
              </div>
            ))}
            {pr.stages.length === 0 && (
              <p className="text-sm text-slate-500 col-span-3">검사 이력 없음</p>
            )}
          </div>
        ) : (
          <p className="text-sm text-slate-500">로딩중...</p>
        )}
      </div>

      <div className="bg-white p-4 rounded-lg border border-slate-200">
        <h2 className="text-lg font-medium mb-3">결함 Pareto (최근 30일)</h2>
        {pareto && pareto.defects.length > 0 ? (
          <table className="w-full text-sm">
            <thead className="bg-slate-100">
              <tr>
                <th className="px-2 py-1 text-left">결함 유형</th>
                <th className="px-2 py-1 text-right">건수</th>
                <th className="px-2 py-1 text-right">수량</th>
                <th className="px-2 py-1 text-right">누적 %</th>
              </tr>
            </thead>
            <tbody>
              {pareto.defects.map((d, i) => (
                <tr key={i} className="border-t">
                  <td className="px-2 py-1">{d.defect_type}</td>
                  <td className="px-2 py-1 text-right">{d.count}</td>
                  <td className="px-2 py-1 text-right">{d.quantity.toLocaleString()}</td>
                  <td className="px-2 py-1 text-right">
                    <span className={d.cumulative_pct >= 80 ? "text-red-600 font-medium" : ""}>
                      {d.cumulative_pct}%
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <p className="text-sm text-slate-500">결함 이력 없음</p>
        )}
      </div>
    </AppShell>
  );
}
