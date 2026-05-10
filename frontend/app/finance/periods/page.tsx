"use client";
import { useEffect, useState } from "react";
import AppShell from "@/components/AppShell";
import DataTable from "@/components/DataTable";
import { api } from "@/lib/api";
import { hasRole, useMe } from "@/lib/auth";

type Period = {
  id: number;
  code: string;
  start_date: string;
  end_date: string;
  is_closed: boolean;
  closed_by_id: number | null;
  notes: string | null;
};

type TBLine = {
  code: string;
  name: string;
  type: string;
  debit: number;
  credit: number;
  balance: number;
};

type IS = {
  start: string;
  end: string;
  revenue: number;
  expense: number;
  net_income: number;
};

export default function FiscalPeriodsPage() {
  const me = useMe();
  const isAdmin = hasRole(me, "admin");

  const [periods, setPeriods] = useState<Period[]>([]);
  const [error, setError] = useState("");
  const [form, setForm] = useState({
    code: "",
    start_date: "",
    end_date: "",
    notes: "",
  });

  const [tbAsOf, setTbAsOf] = useState("");
  const [tb, setTb] = useState<{ as_of: string; lines: TBLine[] } | null>(null);

  const [isRange, setIsRange] = useState({ start: "", end: "" });
  const [isResult, setIsResult] = useState<IS | null>(null);

  const load = async () => {
    try {
      setPeriods(await api<Period[]>("/api/finance/periods"));
    } catch (e) {
      setError(String(e));
    }
  };
  useEffect(() => {
    load();
  }, []);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    try {
      await api("/api/finance/periods", {
        method: "POST",
        body: JSON.stringify({ ...form, notes: form.notes || null }),
      });
      setForm({ code: "", start_date: "", end_date: "", notes: "" });
      await load();
    } catch (e) {
      setError(String(e));
    }
  };

  const close = async (id: number) => {
    if (!confirm("이 회계기간을 마감하시겠습니까? 마감 후에는 해당 기간의 분개를 신규 등록할 수 없습니다."))
      return;
    try {
      await api(`/api/finance/periods/${id}/close`, { method: "POST" });
      await load();
    } catch (e) {
      setError(String(e));
    }
  };

  const reopen = async (id: number) => {
    if (!confirm("기간을 재개방하시겠습니까?")) return;
    try {
      await api(`/api/finance/periods/${id}/reopen`, { method: "POST" });
      await load();
    } catch (e) {
      setError(String(e));
    }
  };

  const runTB = async () => {
    setError("");
    try {
      const q = tbAsOf ? `?as_of=${tbAsOf}` : "";
      setTb(await api(`/api/finance/trial-balance${q}`));
    } catch (e) {
      setError(String(e));
    }
  };

  const runIS = async () => {
    setError("");
    if (!isRange.start || !isRange.end) {
      setError("기간을 선택하세요");
      return;
    }
    try {
      setIsResult(
        await api(
          `/api/finance/income-statement?start=${isRange.start}&end=${isRange.end}`
        )
      );
    } catch (e) {
      setError(String(e));
    }
  };

  return (
    <AppShell>
      <h1 className="text-2xl font-semibold mb-4">회계기간 / 결산</h1>
      {error && <p className="text-red-600 text-sm mb-3">{error}</p>}

      {isAdmin && (
        <form
          onSubmit={submit}
          className="bg-white p-4 rounded-lg shadow-sm border border-slate-200 grid grid-cols-1 md:grid-cols-5 gap-2 mb-4"
        >
          <input
            required
            placeholder="기간 코드 (예: 2026-Q1)"
            value={form.code}
            onChange={(e) => setForm({ ...form, code: e.target.value })}
            className="border rounded px-2 py-1"
          />
          <input
            required
            type="date"
            value={form.start_date}
            onChange={(e) => setForm({ ...form, start_date: e.target.value })}
            className="border rounded px-2 py-1"
          />
          <input
            required
            type="date"
            value={form.end_date}
            onChange={(e) => setForm({ ...form, end_date: e.target.value })}
            className="border rounded px-2 py-1"
          />
          <input
            placeholder="비고"
            value={form.notes}
            onChange={(e) => setForm({ ...form, notes: e.target.value })}
            className="border rounded px-2 py-1"
          />
          <button className="bg-slate-900 text-white px-3 rounded">기간 생성</button>
        </form>
      )}

      <DataTable<Period>
        columns={[
          { key: "code", header: "코드" },
          { key: "start_date", header: "시작" },
          { key: "end_date", header: "종료" },
          {
            key: "is_closed",
            header: "상태",
            render: (r) =>
              r.is_closed ? (
                <span className="text-red-600 font-medium">🔒 마감</span>
              ) : (
                <span className="text-emerald-700">개방</span>
              ),
          },
          { key: "closed_by_id", header: "마감자" },
          { key: "notes", header: "비고" },
          {
            key: "_act",
            header: "관리",
            sortable: false,
            render: (r) =>
              isAdmin ? (
                r.is_closed ? (
                  <button
                    onClick={() => reopen(r.id)}
                    className="text-blue-700 text-xs hover:underline"
                  >
                    재개방
                  </button>
                ) : (
                  <button
                    onClick={() => close(r.id)}
                    className="text-red-600 text-xs hover:underline"
                  >
                    마감
                  </button>
                )
              ) : null,
          },
        ]}
        rows={periods}
      />

      {/* Trial balance */}
      <div className="mt-6 bg-white p-4 rounded-lg shadow-sm border border-slate-200">
        <h2 className="text-lg font-medium mb-2">시산표</h2>
        <div className="flex gap-2 mb-3">
          <input
            type="date"
            value={tbAsOf}
            onChange={(e) => setTbAsOf(e.target.value)}
            className="border rounded px-2 py-1"
          />
          <button
            onClick={runTB}
            className="bg-emerald-700 text-white px-3 py-1 rounded text-sm"
          >
            실행
          </button>
        </div>
        {tb && (
          <table className="text-sm w-full">
            <thead>
              <tr className="bg-slate-100">
                <th className="px-2 py-1 text-left">계정</th>
                <th className="px-2 py-1 text-left">유형</th>
                <th className="px-2 py-1 text-right">차변</th>
                <th className="px-2 py-1 text-right">대변</th>
                <th className="px-2 py-1 text-right">잔액</th>
              </tr>
            </thead>
            <tbody>
              {tb.lines.map((l) => (
                <tr key={l.code} className="border-t">
                  <td className="px-2 py-1">
                    {l.code} {l.name}
                  </td>
                  <td className="px-2 py-1">{l.type}</td>
                  <td className="px-2 py-1 text-right">
                    {l.debit.toLocaleString()}
                  </td>
                  <td className="px-2 py-1 text-right">
                    {l.credit.toLocaleString()}
                  </td>
                  <td className="px-2 py-1 text-right">
                    {l.balance.toLocaleString()}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* Income statement */}
      <div className="mt-4 bg-white p-4 rounded-lg shadow-sm border border-slate-200">
        <h2 className="text-lg font-medium mb-2">손익계산서</h2>
        <div className="flex gap-2 mb-3 flex-wrap">
          <input
            type="date"
            value={isRange.start}
            onChange={(e) => setIsRange({ ...isRange, start: e.target.value })}
            className="border rounded px-2 py-1"
          />
          <span className="self-center">~</span>
          <input
            type="date"
            value={isRange.end}
            onChange={(e) => setIsRange({ ...isRange, end: e.target.value })}
            className="border rounded px-2 py-1"
          />
          <button
            onClick={runIS}
            className="bg-emerald-700 text-white px-3 py-1 rounded text-sm"
          >
            실행
          </button>
        </div>
        {isResult && (
          <div className="grid grid-cols-3 gap-3 text-center">
            <div className="border rounded p-3">
              <div className="text-xs text-slate-500">매출</div>
              <div className="text-lg font-semibold text-emerald-700">
                {isResult.revenue.toLocaleString()}
              </div>
            </div>
            <div className="border rounded p-3">
              <div className="text-xs text-slate-500">비용</div>
              <div className="text-lg font-semibold text-red-600">
                {isResult.expense.toLocaleString()}
              </div>
            </div>
            <div className="border rounded p-3">
              <div className="text-xs text-slate-500">순이익</div>
              <div
                className={`text-lg font-semibold ${
                  isResult.net_income >= 0 ? "text-blue-700" : "text-red-600"
                }`}
              >
                {isResult.net_income.toLocaleString()}
              </div>
            </div>
          </div>
        )}
      </div>
    </AppShell>
  );
}
