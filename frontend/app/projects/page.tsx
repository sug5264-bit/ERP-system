"use client";
import { useEffect, useState } from "react";
import AppShell from "@/components/AppShell";
import DataTable from "@/components/DataTable";
import { Page, api } from "@/lib/api";
import { hasRole, useMe } from "@/lib/auth";

type Project = {
  id: number;
  code: string;
  name: string;
  customer_id: number | null;
  start_date: string | null;
  end_date: string | null;
  budget: string;
  status: "active" | "closed" | "cancelled";
};

type Profitability = {
  project_id: number;
  project_code: string;
  budget: number;
  revenue: number;
  labor_cost: number;
  expense_cost: number;
  total_cost: number;
  margin: number;
  margin_pct: number;
};

export default function ProjectsPage() {
  const me = useMe();
  const isManager = hasRole(me, "manager");
  const [rows, setRows] = useState<Project[]>([]);
  const [error, setError] = useState("");
  const [profit, setProfit] = useState<Profitability | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({
    code: "",
    name: "",
    start_date: "",
    end_date: "",
    budget: "0",
  });

  const load = async () => {
    try {
      const r = await api<Page<Project>>(
        "/api/projects/projects?page=1&size=100"
      );
      setRows(r.items);
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
      await api("/api/projects/projects", {
        method: "POST",
        body: JSON.stringify({
          code: form.code,
          name: form.name,
          start_date: form.start_date || null,
          end_date: form.end_date || null,
          budget: Number(form.budget),
        }),
      });
      setShowForm(false);
      setForm({ code: "", name: "", start_date: "", end_date: "", budget: "0" });
      await load();
    } catch (e) {
      setError(String(e));
    }
  };

  const close = async (id: number) => {
    if (!confirm("프로젝트를 마감하시겠습니까?")) return;
    try {
      await api(`/api/projects/projects/${id}/close`, { method: "POST" });
      await load();
    } catch (e) {
      setError(String(e));
    }
  };

  const showProfit = async (id: number) => {
    try {
      setProfit(
        await api<Profitability>(`/api/projects/projects/${id}/profitability`)
      );
    } catch (e) {
      setError(String(e));
    }
  };

  return (
    <AppShell>
      <div className="flex justify-between items-center mb-4">
        <h1 className="text-2xl font-semibold">프로젝트 / Job Costing</h1>
        {isManager && (
          <button
            onClick={() => setShowForm((s) => !s)}
            className="bg-slate-900 text-white px-3 py-1 rounded text-sm"
          >
            {showForm ? "닫기" : "+ 프로젝트"}
          </button>
        )}
      </div>
      {error && <p className="text-red-600 text-sm mb-3">{error}</p>}

      {showForm && (
        <form
          onSubmit={submit}
          className="bg-white p-4 rounded-lg border border-slate-200 grid grid-cols-1 md:grid-cols-5 gap-2 mb-4"
        >
          <input
            required
            placeholder="코드"
            value={form.code}
            onChange={(e) => setForm({ ...form, code: e.target.value })}
            className="border rounded px-2 py-1"
          />
          <input
            required
            placeholder="프로젝트명"
            value={form.name}
            onChange={(e) => setForm({ ...form, name: e.target.value })}
            className="border rounded px-2 py-1"
          />
          <input
            type="date"
            value={form.start_date}
            onChange={(e) => setForm({ ...form, start_date: e.target.value })}
            className="border rounded px-2 py-1"
          />
          <input
            type="date"
            value={form.end_date}
            onChange={(e) => setForm({ ...form, end_date: e.target.value })}
            className="border rounded px-2 py-1"
          />
          <input
            type="number"
            placeholder="예산"
            value={form.budget}
            onChange={(e) => setForm({ ...form, budget: e.target.value })}
            className="border rounded px-2 py-1"
          />
          <button className="bg-emerald-700 text-white rounded col-span-1 md:col-span-5">
            생성
          </button>
        </form>
      )}

      <DataTable<Project>
        columns={[
          { key: "code", header: "코드" },
          { key: "name", header: "프로젝트" },
          { key: "start_date", header: "시작" },
          { key: "end_date", header: "종료" },
          {
            key: "budget",
            header: "예산",
            render: (r) => Number(r.budget).toLocaleString(),
          },
          { key: "status", header: "상태" },
          {
            key: "_act",
            header: "관리",
            sortable: false,
            render: (r) => (
              <div className="flex gap-2">
                <button
                  onClick={() => showProfit(r.id)}
                  className="text-blue-700 text-xs hover:underline"
                >
                  손익
                </button>
                {isManager && r.status === "active" && (
                  <button
                    onClick={() => close(r.id)}
                    className="text-red-600 text-xs hover:underline"
                  >
                    마감
                  </button>
                )}
              </div>
            ),
          },
        ]}
        rows={rows}
      />

      {profit && (
        <div className="mt-4 bg-white p-4 rounded-lg border border-slate-200">
          <h2 className="text-lg font-medium mb-2">
            손익 — {profit.project_code}
          </h2>
          <div className="grid grid-cols-2 md:grid-cols-5 gap-3 text-center">
            <Stat label="매출" value={profit.revenue} color="text-emerald-700" />
            <Stat label="인건비" value={profit.labor_cost} />
            <Stat label="경비" value={profit.expense_cost} />
            <Stat label="총원가" value={profit.total_cost} color="text-red-600" />
            <Stat
              label={`이익 (${profit.margin_pct}%)`}
              value={profit.margin}
              color={profit.margin >= 0 ? "text-blue-700" : "text-red-600"}
            />
          </div>
        </div>
      )}
    </AppShell>
  );
}

function Stat({
  label,
  value,
  color,
}: {
  label: string;
  value: number;
  color?: string;
}) {
  return (
    <div className="border rounded p-3">
      <div className="text-xs text-slate-500">{label}</div>
      <div className={`text-base font-semibold ${color ?? ""}`}>
        {value.toLocaleString()}
      </div>
    </div>
  );
}
