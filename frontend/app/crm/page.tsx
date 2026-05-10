"use client";
import { useEffect, useState } from "react";
import AppShell from "@/components/AppShell";
import DataTable from "@/components/DataTable";
import Pager from "@/components/Pager";
import { Page, api } from "@/lib/api";

type Lead = {
  id: number;
  name: string;
  company: string | null;
  email: string | null;
  phone: string | null;
  source: string | null;
  status: "new" | "contacted" | "qualified" | "disqualified" | "converted";
  converted_opportunity_id: number | null;
  notes: string | null;
};

type Opportunity = {
  id: number;
  name: string;
  customer_id: number | null;
  lead_id: number | null;
  stage:
    | "prospecting"
    | "qualification"
    | "proposal"
    | "negotiation"
    | "won"
    | "lost";
  amount: string;
  probability: number;
  expected_close_date: string | null;
  notes: string | null;
};

const STAGES = [
  "prospecting",
  "qualification",
  "proposal",
  "negotiation",
  "won",
  "lost",
] as const;

export default function CRMPage() {
  const [tab, setTab] = useState<"leads" | "pipeline">("leads");
  const [error, setError] = useState("");
  return (
    <AppShell>
      <div className="flex justify-between items-center mb-4">
        <h1 className="text-2xl font-semibold">CRM 파이프라인</h1>
        <div className="flex gap-1">
          {(["leads", "pipeline"] as const).map((t) => (
            <button
              key={t}
              onClick={() => setTab(t)}
              className={`px-3 py-1 text-sm rounded ${
                tab === t
                  ? "bg-slate-900 text-white"
                  : "bg-slate-100 hover:bg-slate-200"
              }`}
            >
              {t === "leads" ? "리드" : "영업기회"}
            </button>
          ))}
        </div>
      </div>
      {error && <p className="text-red-600 text-sm mb-3">{error}</p>}
      {tab === "leads" && <LeadsTab onError={setError} />}
      {tab === "pipeline" && <PipelineTab onError={setError} />}
    </AppShell>
  );
}

function LeadsTab({ onError }: { onError: (s: string) => void }) {
  const [rows, setRows] = useState<Lead[]>([]);
  const [page, setPage] = useState(1);
  const [meta, setMeta] = useState({ total: 0, pages: 1 });
  const [form, setForm] = useState({
    name: "",
    company: "",
    email: "",
    phone: "",
    source: "",
  });

  const load = async () => {
    try {
      const r = await api<Page<Lead>>(`/api/crm/leads?page=${page}&size=20`);
      setRows(r.items);
      setMeta({ total: r.total, pages: r.pages });
    } catch (e) {
      onError(String(e));
    }
  };
  useEffect(() => {
    load();
  }, [page]);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    onError("");
    try {
      await api("/api/crm/leads", {
        method: "POST",
        body: JSON.stringify({
          name: form.name,
          company: form.company || null,
          email: form.email || null,
          phone: form.phone || null,
          source: form.source || null,
        }),
      });
      setForm({ name: "", company: "", email: "", phone: "", source: "" });
      await load();
    } catch (e) {
      onError(String(e));
    }
  };

  const convert = async (id: number) => {
    if (!confirm("이 리드를 영업기회로 전환하시겠습니까?")) return;
    try {
      await api(`/api/crm/leads/${id}/convert`, { method: "POST" });
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
          placeholder="이름"
          value={form.name}
          onChange={(e) => setForm({ ...form, name: e.target.value })}
          className="border rounded px-2 py-1"
        />
        <input
          placeholder="회사"
          value={form.company}
          onChange={(e) => setForm({ ...form, company: e.target.value })}
          className="border rounded px-2 py-1"
        />
        <input
          placeholder="이메일"
          value={form.email}
          onChange={(e) => setForm({ ...form, email: e.target.value })}
          className="border rounded px-2 py-1"
        />
        <input
          placeholder="전화"
          value={form.phone}
          onChange={(e) => setForm({ ...form, phone: e.target.value })}
          className="border rounded px-2 py-1"
        />
        <input
          placeholder="소스 (referral, web …)"
          value={form.source}
          onChange={(e) => setForm({ ...form, source: e.target.value })}
          className="border rounded px-2 py-1"
        />
        <button className="bg-slate-900 text-white px-3 rounded">+ 등록</button>
      </form>

      <DataTable<Lead>
        columns={[
          { key: "name", header: "이름" },
          { key: "company", header: "회사" },
          { key: "email", header: "이메일" },
          { key: "source", header: "소스" },
          { key: "status", header: "상태" },
          {
            key: "_act",
            header: "전환",
            sortable: false,
            render: (r) =>
              r.status !== "converted" ? (
                <button
                  onClick={() => convert(r.id)}
                  className="text-blue-700 text-xs hover:underline"
                >
                  → 영업기회
                </button>
              ) : (
                <span className="text-xs text-slate-500">
                  Opp #{r.converted_opportunity_id}
                </span>
              ),
          },
        ]}
        rows={rows}
      />
      <Pager page={page} pages={meta.pages} total={meta.total} onChange={setPage} />
    </>
  );
}

function PipelineTab({ onError }: { onError: (s: string) => void }) {
  const [rows, setRows] = useState<Opportunity[]>([]);
  const [summary, setSummary] = useState<any[]>([]);

  const load = async () => {
    try {
      const r = await api<Page<Opportunity>>(
        `/api/crm/opportunities?page=1&size=200`
      );
      setRows(r.items);
      const s = await api<{ stages: any[] }>("/api/crm/pipeline/summary");
      setSummary(s.stages);
    } catch (e) {
      onError(String(e));
    }
  };
  useEffect(() => {
    load();
  }, []);

  const move = async (id: number, to: string) => {
    try {
      await api(`/api/crm/opportunities/${id}/stage`, {
        method: "POST",
        body: JSON.stringify({ to_stage: to, comment: null }),
      });
      await load();
    } catch (e) {
      onError(String(e));
    }
  };

  return (
    <>
      {/* Summary */}
      <div className="grid grid-cols-2 md:grid-cols-6 gap-2 mb-4">
        {STAGES.map((s) => {
          const item = summary.find((x) => x.stage === s);
          return (
            <div
              key={s}
              className="bg-white p-3 rounded border border-slate-200 text-center"
            >
              <div className="text-xs text-slate-500">{s}</div>
              <div className="text-lg font-semibold">
                {item?.count ?? 0}건
              </div>
              <div className="text-xs text-emerald-700">
                {(item?.weighted_amount ?? 0).toLocaleString()}
              </div>
            </div>
          );
        })}
      </div>

      {/* Kanban */}
      <div className="grid grid-cols-1 md:grid-cols-6 gap-2">
        {STAGES.map((stage) => (
          <div
            key={stage}
            className="bg-slate-50 rounded p-2 min-h-[200px]"
          >
            <div className="text-xs font-medium text-slate-600 mb-2">
              {stage}
            </div>
            {rows
              .filter((o) => o.stage === stage)
              .map((o) => (
                <div
                  key={o.id}
                  className="bg-white border border-slate-200 rounded p-2 mb-2 text-xs"
                >
                  <div className="font-medium">{o.name}</div>
                  <div className="text-slate-500">
                    {Number(o.amount).toLocaleString()} · {o.probability}%
                  </div>
                  <select
                    value={o.stage}
                    onChange={(e) => move(o.id, e.target.value)}
                    className="border rounded px-1 mt-1 text-xs w-full"
                  >
                    {STAGES.map((s) => (
                      <option key={s} value={s}>
                        → {s}
                      </option>
                    ))}
                  </select>
                </div>
              ))}
          </div>
        ))}
      </div>
    </>
  );
}
