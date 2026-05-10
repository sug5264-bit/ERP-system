"use client";
import { useEffect, useState } from "react";
import AppShell from "@/components/AppShell";
import { api } from "@/lib/api";

type Dashboard = {
  id: number;
  code: string;
  name: string;
  description: string | null;
  is_public: boolean;
  widgets: { id: number; title: string; chart_type: string }[];
};

type RunResult = {
  dashboard: { id: number; code: string; name: string };
  widgets: {
    id: number;
    title: string;
    chart_type: string;
    data?: { columns: string[]; rows: any[]; count: number };
    error?: string;
  }[];
};

export default function DashboardsPage() {
  const [dashboards, setDashboards] = useState<Dashboard[]>([]);
  const [active, setActive] = useState<RunResult | null>(null);
  const [error, setError] = useState("");

  const load = async () => {
    try {
      setDashboards(await api<Dashboard[]>("/api/dashboards"));
    } catch (e) {
      setError(String(e));
    }
  };
  useEffect(() => {
    load();
  }, []);

  const run = async (id: number) => {
    setError("");
    try {
      setActive(await api<RunResult>(`/api/dashboards/${id}/run`));
    } catch (e) {
      setError(String(e));
    }
  };

  return (
    <AppShell>
      <h1 className="text-2xl font-semibold mb-4">대시보드</h1>
      {error && <p className="text-red-600 text-sm mb-3">{error}</p>}

      <div className="flex gap-2 mb-4 flex-wrap">
        {dashboards.map((d) => (
          <button
            key={d.id}
            onClick={() => run(d.id)}
            className={`px-3 py-1 rounded text-sm border ${
              active?.dashboard.id === d.id
                ? "bg-slate-900 text-white border-slate-900"
                : "bg-white border-slate-200"
            }`}
          >
            {d.name}
          </button>
        ))}
        {dashboards.length === 0 && (
          <p className="text-sm text-slate-500">
            저장된 대시보드가 없습니다. 백엔드 /api/dashboards 로 등록 후 노출됩니다.
          </p>
        )}
      </div>

      {active && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {active.widgets.map((w) => (
            <div
              key={w.id}
              className="bg-white border border-slate-200 rounded-lg p-4"
            >
              <h2 className="text-base font-medium mb-2">{w.title}</h2>
              {w.error && (
                <p className="text-red-600 text-sm">{w.error}</p>
              )}
              {w.data && w.chart_type === "kpi" && w.data.rows[0] && (
                <div className="text-3xl font-semibold text-emerald-700">
                  {Object.values(w.data.rows[0])[0]?.toLocaleString?.() ??
                    String(Object.values(w.data.rows[0])[0])}
                </div>
              )}
              {w.data && w.chart_type !== "kpi" && (
                <div className="overflow-auto">
                  <table className="text-sm w-full">
                    <thead className="bg-slate-100">
                      <tr>
                        {w.data.columns.map((c) => (
                          <th key={c} className="px-2 py-1 text-left">
                            {c}
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {w.data.rows.slice(0, 20).map((r, i) => (
                        <tr key={i} className="border-t">
                          {w.data!.columns.map((c) => (
                            <td key={c} className="px-2 py-1">
                              {r[c] === null || r[c] === undefined
                                ? "-"
                                : String(r[c])}
                            </td>
                          ))}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </AppShell>
  );
}
