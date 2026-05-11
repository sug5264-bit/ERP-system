"use client";
import { useEffect, useState } from "react";
import AppShell from "@/components/AppShell";
import DataTable from "@/components/DataTable";
import { api } from "@/lib/api";
import { hasRole, useMe } from "@/lib/auth";

type Lease = {
  id: number;
  lease_no: string;
  description: string;
  start_date: string;
  end_date: string;
  monthly_payment: string;
  annual_discount_rate: string;
  rou_asset: string;
  lease_liability: string;
  accumulated_depreciation: string;
  status: string;
  counterparty: string | null;
};

type ScheduleRow = {
  id: number;
  period_code: string;
  sequence: number;
  opening_liability: number;
  interest_expense: number;
  payment: number;
  principal: number;
  closing_liability: number;
  depreciation: number;
  posted: boolean;
  journal_entry_id: number | null;
};

export default function LeasePage() {
  const me = useMe();
  const isAdmin = hasRole(me, "admin");
  const [rows, setRows] = useState<Lease[]>([]);
  const [active, setActive] = useState<Lease | null>(null);
  const [schedule, setSchedule] = useState<ScheduleRow[]>([]);
  const [error, setError] = useState("");
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({
    lease_no: "", description: "", start_date: "", end_date: "",
    monthly_payment: "0", annual_discount_rate: "0.05",
    counterparty: "",
  });

  const load = async () => {
    try {
      setRows(await api<Lease[]>("/api/lease"));
    } catch (e) { setError(String(e)); }
  };
  useEffect(() => { load(); }, []);

  const loadSchedule = async (l: Lease) => {
    setActive(l);
    try {
      setSchedule(await api<ScheduleRow[]>(`/api/lease/${l.id}/schedule`));
    } catch (e) { setError(String(e)); }
  };

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    try {
      await api("/api/lease", {
        method: "POST",
        body: JSON.stringify({
          ...form,
          monthly_payment: Number(form.monthly_payment),
          annual_discount_rate: Number(form.annual_discount_rate),
          counterparty: form.counterparty || null,
        }),
      });
      setShowForm(false);
      await load();
    } catch (e) { setError(String(e)); }
  };

  const activate = async (id: number) => {
    if (!confirm("PV를 계산하고 amortization schedule을 생성합니다. 진행할까요?")) return;
    try {
      await api(`/api/lease/${id}/activate`, { method: "POST" });
      await load();
    } catch (e) { setError(String(e)); }
  };

  const postPeriod = async (l: Lease, period_code: string) => {
    try {
      const r = await api<any>(
        `/api/lease/${l.id}/post-period?period_code=${period_code}`,
        { method: "POST" }
      );
      alert(`분개 #${r.journal_entry_id} 생성 — 잔여부채 ${r.remaining_liability.toLocaleString()}`);
      await loadSchedule(l);
    } catch (e) { setError(String(e)); }
  };

  return (
    <AppShell>
      <div className="flex justify-between items-center mb-4">
        <h1 className="text-2xl font-semibold">Lease 회계 (IFRS 16)</h1>
        {isAdmin && (
          <button onClick={() => setShowForm((s) => !s)}
                  className="bg-slate-900 text-white px-3 py-1 rounded text-sm">
            {showForm ? "닫기" : "+ Lease 등록"}
          </button>
        )}
      </div>
      {error && <p className="text-red-600 text-sm mb-3">{error}</p>}

      {showForm && (
        <form onSubmit={submit} className="bg-white p-4 rounded-lg border border-slate-200 grid grid-cols-1 md:grid-cols-3 gap-2 mb-4">
          <input required placeholder="Lease no" value={form.lease_no}
                 onChange={(e) => setForm({ ...form, lease_no: e.target.value })}
                 className="border rounded px-2 py-1" />
          <input required placeholder="설명" value={form.description}
                 onChange={(e) => setForm({ ...form, description: e.target.value })}
                 className="border rounded px-2 py-1 col-span-2" />
          <input required type="date" value={form.start_date}
                 onChange={(e) => setForm({ ...form, start_date: e.target.value })}
                 className="border rounded px-2 py-1" />
          <input required type="date" value={form.end_date}
                 onChange={(e) => setForm({ ...form, end_date: e.target.value })}
                 className="border rounded px-2 py-1" />
          <input required type="number" placeholder="월 납입금" value={form.monthly_payment}
                 onChange={(e) => setForm({ ...form, monthly_payment: e.target.value })}
                 className="border rounded px-2 py-1" />
          <input type="number" step="0.001" placeholder="연 할인율" value={form.annual_discount_rate}
                 onChange={(e) => setForm({ ...form, annual_discount_rate: e.target.value })}
                 className="border rounded px-2 py-1" />
          <input placeholder="상대방" value={form.counterparty}
                 onChange={(e) => setForm({ ...form, counterparty: e.target.value })}
                 className="border rounded px-2 py-1 col-span-2" />
          <button className="bg-emerald-700 text-white rounded col-span-3">저장</button>
        </form>
      )}

      <DataTable<Lease>
        rows={rows}
        columns={[
          { key: "lease_no", header: "번호" },
          { key: "description", header: "설명" },
          { key: "end_date", header: "만기" },
          {
            key: "rou_asset", header: "ROU 자산",
            render: (r) => Number(r.rou_asset).toLocaleString(),
          },
          {
            key: "lease_liability", header: "리스부채",
            render: (r) => Number(r.lease_liability).toLocaleString(),
          },
          { key: "status", header: "상태" },
          {
            key: "_act", header: "관리", sortable: false,
            render: (r) => (
              <div className="flex gap-2">
                <button onClick={() => loadSchedule(r)}
                        className="text-blue-700 text-xs hover:underline">스케줄</button>
                {isAdmin && r.status === "draft" && (
                  <button onClick={() => activate(r.id)}
                          className="text-emerald-700 text-xs hover:underline">활성화</button>
                )}
              </div>
            ),
          },
        ]}
      />

      {active && (
        <div className="mt-4 bg-white p-4 rounded-lg border border-slate-200">
          <div className="flex justify-between items-center mb-2">
            <h2 className="text-lg font-medium">{active.lease_no} 스케줄</h2>
            <button onClick={() => setActive(null)}
                    className="text-slate-500 hover:text-slate-900">✕</button>
          </div>
          <div className="overflow-auto">
            <table className="w-full text-sm">
              <thead className="bg-slate-100">
                <tr>
                  <th className="px-2 py-1 text-left">기간</th>
                  <th className="px-2 py-1 text-right">개시부채</th>
                  <th className="px-2 py-1 text-right">이자</th>
                  <th className="px-2 py-1 text-right">납입</th>
                  <th className="px-2 py-1 text-right">원금</th>
                  <th className="px-2 py-1 text-right">감가</th>
                  <th className="px-2 py-1 text-right">종료부채</th>
                  <th className="px-2 py-1 text-left">분개</th>
                  <th className="px-2 py-1 text-left">관리</th>
                </tr>
              </thead>
              <tbody>
                {schedule.map((s) => (
                  <tr key={s.id} className="border-t">
                    <td className="px-2 py-1">{s.period_code}</td>
                    <td className="px-2 py-1 text-right">{s.opening_liability.toLocaleString()}</td>
                    <td className="px-2 py-1 text-right">{s.interest_expense.toLocaleString()}</td>
                    <td className="px-2 py-1 text-right">{s.payment.toLocaleString()}</td>
                    <td className="px-2 py-1 text-right">{s.principal.toLocaleString()}</td>
                    <td className="px-2 py-1 text-right">{s.depreciation.toLocaleString()}</td>
                    <td className="px-2 py-1 text-right">{s.closing_liability.toLocaleString()}</td>
                    <td className="px-2 py-1 text-xs">{s.posted ? `#${s.journal_entry_id ?? "-"}` : "-"}</td>
                    <td className="px-2 py-1">
                      {isAdmin && !s.posted && active.status === "active" && (
                        <button onClick={() => postPeriod(active, s.period_code)}
                                className="text-emerald-700 text-xs hover:underline">분개</button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </AppShell>
  );
}
