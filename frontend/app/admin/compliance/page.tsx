"use client";
import { useEffect, useState } from "react";
import AppShell from "@/components/AppShell";
import { api } from "@/lib/api";
import { hasRole, useMe } from "@/lib/auth";

type Dashboard = {
  frameworks: {
    framework: string;
    implemented_pct: number;
    implemented: number;
    partial: number;
    not_implemented: number;
  }[];
  overdue_tests: {
    control_id: number;
    code: string;
    framework: string;
    next_due: string;
    days_overdue: number;
  }[];
  overdue_count: number;
};

type Control = {
  id: number;
  code: string;
  name: string;
  framework: string;
  category: string | null;
  description: string;
  status: string;
  test_frequency_days: number;
};

export default function CompliancePage() {
  const me = useMe();
  const isAdmin = hasRole(me, "admin");
  const [dash, setDash] = useState<Dashboard | null>(null);
  const [controls, setControls] = useState<Control[]>([]);
  const [error, setError] = useState("");

  const load = async () => {
    try {
      setDash(await api<Dashboard>("/api/compliance/dashboard"));
      setControls(await api<Control[]>("/api/compliance/controls"));
    } catch (e) { setError(String(e)); }
  };
  useEffect(() => { load(); }, []);

  const seed = async () => {
    if (!confirm("SOC2/ISO27001/PIPA 베이스라인 통제를 자동 등록합니다.")) return;
    try {
      const r = await api<any>("/api/compliance/seed-baseline", { method: "POST" });
      alert(`${r.inserted}개 추가됨 (총 ${r.total}개 베이스라인 중)`);
      await load();
    } catch (e) { setError(String(e)); }
  };

  const updateStatus = async (id: number, status: string) => {
    try {
      await api(`/api/compliance/controls/${id}/status?status=${status}`, {
        method: "PATCH",
      });
      await load();
    } catch (e) { setError(String(e)); }
  };

  return (
    <AppShell>
      <div className="flex justify-between items-center mb-4">
        <h1 className="text-2xl font-semibold">컴플라이언스 / 통제</h1>
        {isAdmin && (
          <button onClick={seed} className="bg-blue-700 text-white px-3 py-1 rounded text-sm">
            베이스라인 시드
          </button>
        )}
      </div>
      {error && <p className="text-red-600 text-sm mb-3">{error}</p>}

      {dash && (
        <>
          <div className="grid grid-cols-1 md:grid-cols-4 gap-3 mb-4">
            {dash.frameworks.map((f) => (
              <div key={f.framework} className="bg-white border border-slate-200 rounded-lg p-3">
                <div className="text-xs text-slate-500 uppercase">{f.framework}</div>
                <div className="text-2xl font-semibold text-emerald-700 mt-1">
                  {f.implemented_pct}%
                </div>
                <div className="text-xs text-slate-500 mt-1">
                  적용 {f.implemented} · 부분 {f.partial} · 미적용 {f.not_implemented}
                </div>
              </div>
            ))}
          </div>

          {dash.overdue_count > 0 && (
            <div className="bg-red-50 border border-red-200 rounded p-3 mb-4">
              <h3 className="font-medium text-red-700 mb-2">
                ⚠ 테스트 기한 초과 ({dash.overdue_count}건)
              </h3>
              <ul className="text-sm space-y-1">
                {dash.overdue_tests.slice(0, 10).map((o) => (
                  <li key={o.control_id}>
                    <span className="font-mono">{o.code}</span> · {o.framework} ·{" "}
                    <span className="text-red-700">{o.days_overdue}일 초과</span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </>
      )}

      <div className="bg-white border border-slate-200 rounded-lg overflow-auto">
        <table className="w-full text-sm">
          <thead className="bg-slate-100">
            <tr>
              <th className="px-2 py-2 text-left">코드</th>
              <th className="px-2 py-2 text-left">프레임워크</th>
              <th className="px-2 py-2 text-left">통제명</th>
              <th className="px-2 py-2 text-left">분류</th>
              <th className="px-2 py-2 text-left">상태</th>
            </tr>
          </thead>
          <tbody>
            {controls.map((c) => (
              <tr key={c.id} className="border-t">
                <td className="px-2 py-1 font-mono text-xs">{c.code}</td>
                <td className="px-2 py-1 uppercase text-xs">{c.framework}</td>
                <td className="px-2 py-1">{c.name}</td>
                <td className="px-2 py-1 text-xs">{c.category ?? "-"}</td>
                <td className="px-2 py-1">
                  {isAdmin ? (
                    <select value={c.status}
                            onChange={(e) => updateStatus(c.id, e.target.value)}
                            className="border rounded text-xs px-1">
                      <option value="not_implemented">미적용</option>
                      <option value="partial">부분</option>
                      <option value="implemented">적용</option>
                    </select>
                  ) : (
                    <span className={
                      c.status === "implemented" ? "text-emerald-700" :
                      c.status === "partial" ? "text-amber-700" : "text-red-600"
                    }>{c.status}</span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </AppShell>
  );
}
