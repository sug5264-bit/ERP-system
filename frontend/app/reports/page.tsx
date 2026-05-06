"use client";
import { useEffect, useState } from "react";
import AppShell from "@/components/AppShell";
import DataTable from "@/components/DataTable";
import { api } from "@/lib/api";

type Schedule = {
  id: number;
  name: string;
  report_type: string;
  frequency: string;
  recipients: string;
  next_run_at: string | null;
  last_run_at: string | null;
  enabled: boolean;
};

const REPORT_TYPES = [
  { value: "sales_by_month", label: "월별 매출" },
  { value: "employees_by_department", label: "부서별 직원" },
  { value: "top_items", label: "재고 가치 Top" },
  { value: "account_balances", label: "계정 잔액" },
];

const FREQUENCIES = [
  { value: "daily", label: "매일" },
  { value: "weekly", label: "매주" },
  { value: "monthly", label: "매월" },
];

export default function ReportsPage() {
  const [schedules, setSchedules] = useState<Schedule[]>([]);
  const [error, setError] = useState("");
  const [form, setForm] = useState({
    name: "",
    report_type: "sales_by_month",
    frequency: "monthly",
    recipients: "",
  });

  const load = () =>
    api<Schedule[]>("/api/reports/schedules")
      .then(setSchedules)
      .catch((e) => setError(String(e)));

  useEffect(() => {
    load();
  }, []);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    try {
      await api("/api/reports/schedules", {
        method: "POST",
        body: JSON.stringify({ ...form, enabled: true }),
      });
      setForm({ name: "", report_type: "sales_by_month", frequency: "monthly", recipients: "" });
      await load();
    } catch (e) {
      setError(String(e));
    }
  };

  const runNow = async (id: number) => {
    try {
      const result = await api<{ rows: number; emails_sent: number; pdf_path: string }>(
        `/api/reports/schedules/${id}/run-now`,
        { method: "POST" }
      );
      alert(
        `생성 완료: ${result.rows}건, 이메일 ${result.emails_sent}건 발송\n경로: ${result.pdf_path}`
      );
      await load();
    } catch (e) {
      setError(String(e));
    }
  };

  const remove = async (id: number) => {
    if (!confirm("삭제하시겠습니까?")) return;
    try {
      await api(`/api/reports/schedules/${id}`, { method: "DELETE" });
      await load();
    } catch (e) {
      setError(String(e));
    }
  };

  return (
    <AppShell>
      <h1 className="text-2xl font-semibold mb-4">예약 보고서</h1>

      <form
        onSubmit={submit}
        className="bg-white p-4 rounded-lg shadow-sm border border-slate-200 grid grid-cols-1 md:grid-cols-5 gap-3 mb-6"
      >
        <input
          required
          placeholder="이름 (예: 월간 매출 리포트)"
          value={form.name}
          onChange={(e) => setForm({ ...form, name: e.target.value })}
          className="border rounded px-2 py-1"
        />
        <select
          value={form.report_type}
          onChange={(e) => setForm({ ...form, report_type: e.target.value })}
          className="border rounded px-2 py-1"
        >
          {REPORT_TYPES.map((r) => (
            <option key={r.value} value={r.value}>
              {r.label}
            </option>
          ))}
        </select>
        <select
          value={form.frequency}
          onChange={(e) => setForm({ ...form, frequency: e.target.value })}
          className="border rounded px-2 py-1"
        >
          {FREQUENCIES.map((f) => (
            <option key={f.value} value={f.value}>
              {f.label}
            </option>
          ))}
        </select>
        <input
          placeholder="수신자 (콤마 구분)"
          value={form.recipients}
          onChange={(e) => setForm({ ...form, recipients: e.target.value })}
          className="border rounded px-2 py-1"
        />
        <button className="bg-slate-900 text-white px-3 rounded">예약 추가</button>
      </form>

      {error && <p className="text-red-600 text-sm mb-3">{error}</p>}

      <DataTable<Schedule>
        columns={[
          { key: "name", header: "이름" },
          {
            key: "report_type",
            header: "리포트",
            render: (r) =>
              REPORT_TYPES.find((t) => t.value === r.report_type)?.label ?? r.report_type,
          },
          {
            key: "frequency",
            header: "주기",
            render: (r) => FREQUENCIES.find((f) => f.value === r.frequency)?.label ?? r.frequency,
          },
          { key: "recipients", header: "수신자" },
          {
            key: "next_run_at",
            header: "다음 실행",
            render: (r) =>
              r.next_run_at ? new Date(r.next_run_at).toLocaleString() : "-",
          },
          {
            key: "last_run_at",
            header: "마지막 실행",
            render: (r) =>
              r.last_run_at ? new Date(r.last_run_at).toLocaleString() : "-",
          },
          {
            key: "actions",
            header: "",
            render: (r) => (
              <div className="flex gap-2">
                <button
                  onClick={() => runNow(r.id)}
                  className="px-2 py-1 bg-blue-600 text-white rounded text-xs"
                >
                  지금 실행
                </button>
                <button
                  onClick={() => remove(r.id)}
                  className="px-2 py-1 text-red-600 text-xs hover:underline"
                >
                  삭제
                </button>
              </div>
            ),
          },
        ]}
        rows={schedules}
      />
    </AppShell>
  );
}
