"use client";
import { useEffect, useState } from "react";
import AppShell from "@/components/AppShell";
import { api } from "@/lib/api";

type KPIDef = { code: string; label: string; unit: string };
type KPIResult = {
  code: string;
  label: string;
  unit: string;
  value: number;
  breakdown: { dimension: string; value: number }[];
};

export default function KPIPage() {
  const [kpis, setKpis] = useState<KPIDef[]>([]);
  const [results, setResults] = useState<Record<string, KPIResult>>({});
  const [active, setActive] = useState<KPIResult | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    (async () => {
      try {
        const list = await api<{ kpis: KPIDef[] }>("/api/kpi/list");
        setKpis(list.kpis);
        // Run all in parallel
        const out: Record<string, KPIResult> = {};
        await Promise.all(
          list.kpis.map(async (k) => {
            try {
              out[k.code] = await api<KPIResult>(`/api/kpi/run/${k.code}`);
            } catch (e) {
              /* skip */
            }
          })
        );
        setResults(out);
      } catch (e) {
        setError(String(e));
      }
    })();
  }, []);

  return (
    <AppShell>
      <h1 className="text-2xl font-semibold mb-4">KPI 라이브러리</h1>
      {error && <p className="text-red-600 text-sm mb-3">{error}</p>}

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-4">
        {kpis.map((k) => {
          const r = results[k.code];
          return (
            <button
              key={k.code}
              onClick={() => r && setActive(r)}
              className="bg-white border border-slate-200 rounded-lg p-4 text-left hover:border-emerald-700 transition"
            >
              <div className="text-xs text-slate-500">{k.label}</div>
              <div className="text-xl font-semibold text-emerald-700 mt-1">
                {r ? r.value.toLocaleString() : "..."}
              </div>
              <div className="text-xs text-slate-400 mt-1">{k.unit}</div>
            </button>
          );
        })}
      </div>

      {active && (
        <div className="bg-white border border-slate-200 rounded-lg p-4">
          <div className="flex justify-between items-center mb-3">
            <h2 className="text-lg font-medium">
              Drill-down — {active.label}
            </h2>
            <button
              onClick={() => setActive(null)}
              className="text-slate-500 hover:text-slate-900"
            >
              ✕
            </button>
          </div>
          {active.breakdown.length === 0 ? (
            <p className="text-sm text-slate-500">상세 데이터 없음</p>
          ) : (
            <table className="w-full text-sm">
              <thead className="bg-slate-100">
                <tr>
                  <th className="px-2 py-1 text-left">차원</th>
                  <th className="px-2 py-1 text-right">값</th>
                </tr>
              </thead>
              <tbody>
                {active.breakdown.map((b, i) => (
                  <tr key={i} className="border-t">
                    <td className="px-2 py-1">{b.dimension}</td>
                    <td className="px-2 py-1 text-right font-medium">
                      {b.value.toLocaleString()}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}
    </AppShell>
  );
}
