"use client";
import { useEffect, useState } from "react";
import AppShell from "@/components/AppShell";
import DataTable from "@/components/DataTable";
import { api } from "@/lib/api";

type Attendance = {
  id: number;
  employee_id: number;
  date: string;
  clock_in: string | null;
  clock_out: string | null;
  worked_minutes: number;
  overtime_minutes: number;
  note: string | null;
};

export default function AttendancePage() {
  const [rows, setRows] = useState<Attendance[]>([]);
  const [empId, setEmpId] = useState("");
  const [period, setPeriod] = useState("");
  const [error, setError] = useState("");
  const [summary, setSummary] = useState<any>(null);
  const [form, setForm] = useState({ employee_id: "", date: "", time: "" });

  const load = async () => {
    try {
      const params = new URLSearchParams();
      if (empId) params.set("employee_id", empId);
      if (period) params.set("period", period);
      const q = params.toString() ? `?${params}` : "";
      setRows(await api<Attendance[]>(`/api/hr/attendance${q}`));
    } catch (e) {
      setError(String(e));
    }
  };

  useEffect(() => {
    load();
  }, [empId, period]);

  const action = async (path: "clock-in" | "clock-out") => {
    setError("");
    try {
      await api(`/api/hr/attendance/${path}`, {
        method: "POST",
        body: JSON.stringify({
          employee_id: Number(form.employee_id),
          date: form.date || null,
          time: form.time || null,
        }),
      });
      await load();
    } catch (e) {
      setError(String(e));
    }
  };

  const fetchSummary = async () => {
    if (!empId || !period) {
      setError("직원 ID와 기간(YYYY-MM)을 입력하세요");
      return;
    }
    try {
      setSummary(
        await api(
          `/api/hr/attendance/summary?employee_id=${empId}&period=${period}`
        )
      );
    } catch (e) {
      setError(String(e));
    }
  };

  return (
    <AppShell>
      <h1 className="text-2xl font-semibold mb-4">근태 / 출퇴근</h1>
      {error && <p className="text-red-600 text-sm mb-3">{error}</p>}

      <div className="bg-white p-4 rounded-lg border border-slate-200 mb-4 grid grid-cols-1 md:grid-cols-5 gap-2">
        <input
          placeholder="직원 ID"
          type="number"
          value={form.employee_id}
          onChange={(e) => setForm({ ...form, employee_id: e.target.value })}
          className="border rounded px-2 py-1"
        />
        <input
          type="date"
          value={form.date}
          onChange={(e) => setForm({ ...form, date: e.target.value })}
          className="border rounded px-2 py-1"
        />
        <input
          placeholder="HH:MM:SS (선택)"
          value={form.time}
          onChange={(e) => setForm({ ...form, time: e.target.value })}
          className="border rounded px-2 py-1"
        />
        <button
          onClick={() => action("clock-in")}
          className="bg-emerald-700 text-white rounded"
        >
          출근
        </button>
        <button
          onClick={() => action("clock-out")}
          className="bg-slate-900 text-white rounded"
        >
          퇴근
        </button>
      </div>

      <div className="bg-white p-4 rounded-lg border border-slate-200 mb-4 flex gap-2 items-center flex-wrap">
        <input
          type="number"
          placeholder="조회 직원 ID"
          value={empId}
          onChange={(e) => setEmpId(e.target.value)}
          className="border rounded px-2 py-1"
        />
        <input
          placeholder="YYYY-MM"
          value={period}
          onChange={(e) => setPeriod(e.target.value)}
          className="border rounded px-2 py-1"
        />
        <button
          onClick={fetchSummary}
          className="bg-blue-700 text-white px-3 py-1 rounded text-sm"
        >
          기간 합계
        </button>
        {summary && (
          <span className="text-sm text-slate-700">
            {summary.days}일 / 총 {summary.total_hours}h / 연장 {summary.overtime_hours}h
          </span>
        )}
      </div>

      <DataTable<Attendance>
        columns={[
          { key: "date", header: "일자" },
          { key: "employee_id", header: "직원" },
          { key: "clock_in", header: "출근" },
          { key: "clock_out", header: "퇴근" },
          {
            key: "worked_minutes",
            header: "근무(시간)",
            render: (r) => (r.worked_minutes / 60).toFixed(1),
          },
          {
            key: "overtime_minutes",
            header: "연장(시간)",
            render: (r) =>
              r.overtime_minutes > 0 ? (
                <span className="text-orange-700 font-medium">
                  {(r.overtime_minutes / 60).toFixed(1)}
                </span>
              ) : (
                "-"
              ),
          },
          { key: "note", header: "메모" },
        ]}
        rows={rows}
      />
    </AppShell>
  );
}
