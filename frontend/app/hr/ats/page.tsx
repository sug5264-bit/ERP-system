"use client";
import { useEffect, useState } from "react";
import AppShell from "@/components/AppShell";
import DataTable from "@/components/DataTable";
import Pager from "@/components/Pager";
import { Page, api } from "@/lib/api";
import { hasRole, useMe } from "@/lib/auth";

type Job = {
  id: number;
  code: string;
  title: string;
  status: "open" | "on_hold" | "filled" | "cancelled";
  headcount: number;
  opened_at: string;
};

type App = {
  id: number;
  job_posting_id: number;
  candidate_id: number;
  stage: "applied" | "screening" | "interview" | "offer" | "hired" | "rejected" | "withdrawn";
  rating: number | null;
  notes: string | null;
};

const STAGES = ["applied", "screening", "interview", "offer", "hired", "rejected", "withdrawn"] as const;

export default function ATSPage() {
  const me = useMe();
  const isManager = hasRole(me, "manager");
  const isAdmin = hasRole(me, "admin");
  const [tab, setTab] = useState<"jobs" | "apps">("jobs");
  const [error, setError] = useState("");
  return (
    <AppShell>
      <div className="flex justify-between items-center mb-4">
        <h1 className="text-2xl font-semibold">ATS / 채용</h1>
        <div className="flex gap-1">
          {(["jobs", "apps"] as const).map((t) => (
            <button
              key={t}
              onClick={() => setTab(t)}
              className={`px-3 py-1 text-sm rounded ${
                tab === t ? "bg-slate-900 text-white" : "bg-slate-100 hover:bg-slate-200"
              }`}
            >
              {t === "jobs" ? "채용공고" : "지원자 파이프라인"}
            </button>
          ))}
        </div>
      </div>
      {error && <p className="text-red-600 text-sm mb-3">{error}</p>}
      {tab === "jobs" && <JobsTab onError={setError} isManager={isManager} />}
      {tab === "apps" && <AppsTab onError={setError} isManager={isManager} isAdmin={isAdmin} />}
    </AppShell>
  );
}

function JobsTab({ onError, isManager }: { onError: (s: string) => void; isManager: boolean }) {
  const [rows, setRows] = useState<Job[]>([]);
  const [page, setPage] = useState(1);
  const [meta, setMeta] = useState({ total: 0, pages: 1 });
  const [form, setForm] = useState({ code: "", title: "", headcount: "1" });

  const load = async () => {
    try {
      const r = await api<Page<Job>>(`/api/ats/jobs?page=${page}&size=20`);
      setRows(r.items);
      setMeta({ total: r.total, pages: r.pages });
    } catch (e) { onError(String(e)); }
  };
  useEffect(() => { load(); }, [page]);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    onError("");
    try {
      await api("/api/ats/jobs", {
        method: "POST",
        body: JSON.stringify({
          code: form.code, title: form.title, headcount: Number(form.headcount),
        }),
      });
      setForm({ code: "", title: "", headcount: "1" });
      await load();
    } catch (e) { onError(String(e)); }
  };

  return (
    <>
      {isManager && (
        <form onSubmit={submit} className="bg-white p-4 rounded-lg border border-slate-200 grid grid-cols-1 md:grid-cols-4 gap-2 mb-4">
          <input required placeholder="코드" value={form.code}
                 onChange={(e) => setForm({ ...form, code: e.target.value })}
                 className="border rounded px-2 py-1" />
          <input required placeholder="포지션" value={form.title}
                 onChange={(e) => setForm({ ...form, title: e.target.value })}
                 className="border rounded px-2 py-1 col-span-2" />
          <input required type="number" placeholder="모집인원" value={form.headcount}
                 onChange={(e) => setForm({ ...form, headcount: e.target.value })}
                 className="border rounded px-2 py-1" />
          <button className="bg-slate-900 text-white rounded col-span-4">+ 공고 생성</button>
        </form>
      )}
      <DataTable<Job> rows={rows} columns={[
        { key: "code", header: "코드" },
        { key: "title", header: "포지션" },
        { key: "headcount", header: "모집" },
        { key: "status", header: "상태" },
        { key: "opened_at", header: "오픈일" },
      ]} />
      <Pager page={page} pages={meta.pages} total={meta.total} onChange={setPage} />
    </>
  );
}

function AppsTab({ onError, isManager, isAdmin }: { onError: (s: string) => void; isManager: boolean; isAdmin: boolean }) {
  const [rows, setRows] = useState<App[]>([]);
  const [page, setPage] = useState(1);
  const [meta, setMeta] = useState({ total: 0, pages: 1 });

  const load = async () => {
    try {
      const r = await api<Page<App>>(`/api/ats/applications?page=${page}&size=50`);
      setRows(r.items);
      setMeta({ total: r.total, pages: r.pages });
    } catch (e) { onError(String(e)); }
  };
  useEffect(() => { load(); }, [page]);

  const move = async (id: number, stage: string) => {
    try {
      await api(`/api/ats/applications/${id}/move-stage`, {
        method: "POST",
        body: JSON.stringify({ stage }),
      });
      await load();
    } catch (e) { onError(String(e)); }
  };

  const hire = async (id: number) => {
    const employee_no = prompt("사번");
    const salary = prompt("연봉");
    if (!employee_no || !salary) return;
    try {
      await api(`/api/ats/applications/${id}/hire`, {
        method: "POST",
        body: JSON.stringify({ employee_no, salary: Number(salary) }),
      });
      await load();
    } catch (e) { onError(String(e)); }
  };

  return (
    <>
      <DataTable<App> rows={rows} columns={[
        { key: "id", header: "ID" },
        { key: "job_posting_id", header: "공고" },
        { key: "candidate_id", header: "지원자" },
        { key: "stage", header: "단계" },
        { key: "rating", header: "평점" },
        {
          key: "_act",
          header: "관리",
          sortable: false,
          render: (r) => (
            <div className="flex gap-2">
              {isManager && !["hired","rejected","withdrawn"].includes(r.stage) && (
                <select
                  value={r.stage}
                  onChange={(e) => move(r.id, e.target.value)}
                  className="border rounded text-xs px-1"
                >
                  {STAGES.map(s => <option key={s} value={s}>{s}</option>)}
                </select>
              )}
              {isAdmin && r.stage === "offer" && (
                <button onClick={() => hire(r.id)} className="text-emerald-700 text-xs hover:underline">채용 확정</button>
              )}
            </div>
          ),
        },
      ]} />
      <Pager page={page} pages={meta.pages} total={meta.total} onChange={setPage} />
    </>
  );
}
