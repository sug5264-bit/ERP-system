"use client";
import { useEffect, useState } from "react";
import AppShell from "@/components/AppShell";
import DataTable from "@/components/DataTable";
import { api } from "@/lib/api";
import { hasRole, useMe } from "@/lib/auth";

type Tab = "leave" | "payroll";

type LeaveRequest = {
  id: number;
  employee_id: number;
  type: "annual" | "sick" | "unpaid" | "special";
  start_date: string;
  end_date: string;
  days: string;
  reason: string | null;
  status: "pending" | "approved" | "rejected";
  decided_by_id: number | null;
  decided_comment: string | null;
};

type Payroll = {
  id: number;
  employee_id: number;
  period_code: string;
  base_salary: string;
  bonus: string;
  allowance: string;
  deduction: string;
  income_tax: string;
  net_pay: string;
  status: "draft" | "issued" | "paid";
  paid_at: string | null;
};

export default function PayrollPage() {
  const me = useMe();
  const isAdmin = hasRole(me, "admin");
  const isManager = hasRole(me, "manager");
  const [tab, setTab] = useState<Tab>("leave");
  const [error, setError] = useState("");

  return (
    <AppShell>
      <div className="flex justify-between items-center mb-4">
        <h1 className="text-2xl font-semibold">급여 / 휴가</h1>
        <div className="flex gap-1">
          {(["leave", "payroll"] as Tab[]).map((t) => (
            <button
              key={t}
              onClick={() => setTab(t)}
              className={`px-3 py-1 text-sm rounded ${
                tab === t
                  ? "bg-slate-900 text-white"
                  : "bg-slate-100 hover:bg-slate-200"
              }`}
            >
              {t === "leave" ? "휴가" : "급여"}
            </button>
          ))}
        </div>
      </div>

      {error && <p className="text-red-600 text-sm mb-3">{error}</p>}

      {tab === "leave" && <LeaveTab onError={setError} isManager={isManager} />}
      {tab === "payroll" && <PayrollTab onError={setError} isAdmin={isAdmin} />}
    </AppShell>
  );
}

function LeaveTab({
  onError,
  isManager,
}: {
  onError: (s: string) => void;
  isManager: boolean;
}) {
  const [rows, setRows] = useState<LeaveRequest[]>([]);
  const [filter, setFilter] = useState<string>("");
  const [form, setForm] = useState({
    employee_id: "",
    type: "annual",
    start_date: "",
    end_date: "",
    reason: "",
  });

  const load = async () => {
    try {
      const q = filter ? `?status=${filter}` : "";
      setRows(await api<LeaveRequest[]>(`/api/hr/leave-requests${q}`));
    } catch (e) {
      onError(String(e));
    }
  };
  useEffect(() => {
    load();
  }, [filter]);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    onError("");
    try {
      await api("/api/hr/leave-requests", {
        method: "POST",
        body: JSON.stringify({
          employee_id: Number(form.employee_id),
          type: form.type,
          start_date: form.start_date,
          end_date: form.end_date,
          reason: form.reason || null,
        }),
      });
      setForm({
        employee_id: "",
        type: "annual",
        start_date: "",
        end_date: "",
        reason: "",
      });
      await load();
    } catch (e) {
      onError(String(e));
    }
  };

  const decide = async (id: number, action: "approve" | "reject") => {
    const comment = prompt(action === "approve" ? "승인 메모 (선택)" : "반려 사유");
    if (action === "reject" && !comment) return;
    try {
      await api(`/api/hr/leave-requests/${id}/${action}`, {
        method: "POST",
        body: JSON.stringify({ comment: comment || null }),
      });
      await load();
    } catch (e) {
      onError(String(e));
    }
  };

  return (
    <>
      <form
        onSubmit={submit}
        className="bg-white p-4 rounded-lg shadow-sm border border-slate-200 grid grid-cols-1 md:grid-cols-6 gap-2 mb-4"
      >
        <input
          required
          type="number"
          placeholder="직원 ID"
          value={form.employee_id}
          onChange={(e) => setForm({ ...form, employee_id: e.target.value })}
          className="border rounded px-2 py-1"
        />
        <select
          value={form.type}
          onChange={(e) => setForm({ ...form, type: e.target.value })}
          className="border rounded px-2 py-1"
        >
          <option value="annual">연차</option>
          <option value="sick">병가</option>
          <option value="unpaid">무급</option>
          <option value="special">경조</option>
        </select>
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
          placeholder="사유"
          value={form.reason}
          onChange={(e) => setForm({ ...form, reason: e.target.value })}
          className="border rounded px-2 py-1"
        />
        <button className="bg-slate-900 text-white px-3 rounded">신청</button>
      </form>

      <div className="mb-2 text-sm">
        상태 필터:
        <select
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          className="border rounded px-2 py-0.5 ml-2"
        >
          <option value="">전체</option>
          <option value="pending">대기</option>
          <option value="approved">승인</option>
          <option value="rejected">반려</option>
        </select>
      </div>

      <DataTable<LeaveRequest>
        columns={[
          { key: "id", header: "ID" },
          { key: "employee_id", header: "직원" },
          { key: "type", header: "유형" },
          { key: "start_date", header: "시작" },
          { key: "end_date", header: "종료" },
          { key: "days", header: "일수" },
          { key: "status", header: "상태" },
          { key: "reason", header: "사유" },
          { key: "decided_comment", header: "의견" },
          {
            key: "_act",
            header: "관리",
            sortable: false,
            render: (r) =>
              isManager && r.status === "pending" ? (
                <div className="flex gap-2">
                  <button
                    onClick={() => decide(r.id, "approve")}
                    className="text-emerald-700 text-xs hover:underline"
                  >
                    승인
                  </button>
                  <button
                    onClick={() => decide(r.id, "reject")}
                    className="text-red-600 text-xs hover:underline"
                  >
                    반려
                  </button>
                </div>
              ) : null,
          },
        ]}
        rows={rows}
      />
    </>
  );
}

function PayrollTab({
  onError,
  isAdmin,
}: {
  onError: (s: string) => void;
  isAdmin: boolean;
}) {
  const [rows, setRows] = useState<Payroll[]>([]);
  const [filter, setFilter] = useState({ period: "", employee: "" });
  const [form, setForm] = useState({
    employee_id: "",
    period_code: "",
    base_salary: "",
    bonus: "0",
    allowance: "0",
    deduction: "0",
  });

  const load = async () => {
    try {
      const params = new URLSearchParams();
      if (filter.period) params.set("period_code", filter.period);
      if (filter.employee) params.set("employee_id", filter.employee);
      const q = params.toString() ? `?${params}` : "";
      setRows(await api<Payroll[]>(`/api/hr/payrolls${q}`));
    } catch (e) {
      onError(String(e));
    }
  };
  useEffect(() => {
    load();
  }, [filter]);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    onError("");
    try {
      await api("/api/hr/payrolls", {
        method: "POST",
        body: JSON.stringify({
          employee_id: Number(form.employee_id),
          period_code: form.period_code,
          base_salary: form.base_salary ? Number(form.base_salary) : null,
          bonus: Number(form.bonus),
          allowance: Number(form.allowance),
          deduction: Number(form.deduction),
        }),
      });
      setForm({
        employee_id: "",
        period_code: "",
        base_salary: "",
        bonus: "0",
        allowance: "0",
        deduction: "0",
      });
      await load();
    } catch (e) {
      onError(String(e));
    }
  };

  const transition = async (id: number, action: "issue" | "mark-paid") => {
    try {
      await api(`/api/hr/payrolls/${id}/${action}`, { method: "POST" });
      await load();
    } catch (e) {
      onError(String(e));
    }
  };

  return (
    <>
      {isAdmin && (
        <form
          onSubmit={submit}
          className="bg-white p-4 rounded-lg shadow-sm border border-slate-200 grid grid-cols-1 md:grid-cols-6 gap-2 mb-4"
        >
          <input
            required
            type="number"
            placeholder="직원 ID"
            value={form.employee_id}
            onChange={(e) => setForm({ ...form, employee_id: e.target.value })}
            className="border rounded px-2 py-1"
          />
          <input
            required
            placeholder="기간 (예: 2026-05)"
            value={form.period_code}
            onChange={(e) => setForm({ ...form, period_code: e.target.value })}
            className="border rounded px-2 py-1"
          />
          <input
            type="number"
            placeholder="기본급 (선택)"
            value={form.base_salary}
            onChange={(e) => setForm({ ...form, base_salary: e.target.value })}
            className="border rounded px-2 py-1"
          />
          <input
            type="number"
            placeholder="상여"
            value={form.bonus}
            onChange={(e) => setForm({ ...form, bonus: e.target.value })}
            className="border rounded px-2 py-1"
          />
          <input
            type="number"
            placeholder="수당"
            value={form.allowance}
            onChange={(e) => setForm({ ...form, allowance: e.target.value })}
            className="border rounded px-2 py-1"
          />
          <div className="flex gap-2">
            <input
              type="number"
              placeholder="공제"
              value={form.deduction}
              onChange={(e) => setForm({ ...form, deduction: e.target.value })}
              className="border rounded px-2 py-1 w-full"
            />
            <button className="bg-slate-900 text-white px-3 rounded">생성</button>
          </div>
        </form>
      )}

      <div className="mb-2 text-sm flex gap-2">
        <input
          placeholder="기간 필터"
          value={filter.period}
          onChange={(e) => setFilter({ ...filter, period: e.target.value })}
          className="border rounded px-2 py-0.5"
        />
        <input
          type="number"
          placeholder="직원 ID"
          value={filter.employee}
          onChange={(e) => setFilter({ ...filter, employee: e.target.value })}
          className="border rounded px-2 py-0.5"
        />
      </div>

      <DataTable<Payroll>
        columns={[
          { key: "id", header: "ID" },
          { key: "employee_id", header: "직원" },
          { key: "period_code", header: "기간" },
          {
            key: "base_salary",
            header: "기본급",
            render: (r) => Number(r.base_salary).toLocaleString(),
          },
          {
            key: "bonus",
            header: "상여",
            render: (r) => Number(r.bonus).toLocaleString(),
          },
          {
            key: "allowance",
            header: "수당",
            render: (r) => Number(r.allowance).toLocaleString(),
          },
          {
            key: "deduction",
            header: "공제",
            render: (r) => Number(r.deduction).toLocaleString(),
          },
          {
            key: "income_tax",
            header: "소득세",
            render: (r) => Number(r.income_tax).toLocaleString(),
          },
          {
            key: "net_pay",
            header: "실수령",
            render: (r) => (
              <span className="font-semibold">
                {Number(r.net_pay).toLocaleString()}
              </span>
            ),
          },
          { key: "status", header: "상태" },
          { key: "paid_at", header: "지급일" },
          {
            key: "_act",
            header: "관리",
            sortable: false,
            render: (r) =>
              isAdmin ? (
                <div className="flex gap-2">
                  {r.status === "draft" && (
                    <button
                      onClick={() => transition(r.id, "issue")}
                      className="text-blue-700 text-xs hover:underline"
                    >
                      발행
                    </button>
                  )}
                  {r.status === "issued" && (
                    <button
                      onClick={() => transition(r.id, "mark-paid")}
                      className="text-emerald-700 text-xs hover:underline"
                    >
                      지급완료
                    </button>
                  )}
                </div>
              ) : null,
          },
        ]}
        rows={rows}
      />
    </>
  );
}
