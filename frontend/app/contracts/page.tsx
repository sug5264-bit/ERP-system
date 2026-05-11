"use client";
import { useEffect, useState } from "react";
import AppShell from "@/components/AppShell";
import DataTable from "@/components/DataTable";
import Pager from "@/components/Pager";
import { Page, api } from "@/lib/api";
import { hasRole, useMe } from "@/lib/auth";

type Contract = {
  id: number;
  contract_no: string;
  title: string;
  type: string;
  counterparty: string;
  start_date: string;
  end_date: string;
  value: string;
  currency: string;
  renewal: string;
  notice_period_days: number;
  status: string;
};

type Renewal = {
  id: number;
  contract_no: string;
  title: string;
  type: string;
  counterparty: string;
  end_date: string;
  renewal: string;
  days_to_end: number;
  in_notice_window: boolean;
  value: number;
};

export default function ContractsPage() {
  const me = useMe();
  const isManager = hasRole(me, "manager");
  const isAdmin = hasRole(me, "admin");
  const [tab, setTab] = useState<"contracts" | "renewals">("contracts");
  const [error, setError] = useState("");
  return (
    <AppShell>
      <div className="flex justify-between items-center mb-4">
        <h1 className="text-2xl font-semibold">계약 관리</h1>
        <div className="flex gap-1">
          {(["contracts", "renewals"] as const).map((t) => (
            <button
              key={t}
              onClick={() => setTab(t)}
              className={`px-3 py-1 text-sm rounded ${
                tab === t ? "bg-slate-900 text-white" : "bg-slate-100 hover:bg-slate-200"
              }`}
            >
              {t === "contracts" ? "계약 목록" : "갱신 임박"}
            </button>
          ))}
        </div>
      </div>
      {error && <p className="text-red-600 text-sm mb-3">{error}</p>}
      {tab === "contracts" && <ContractsTab onError={setError} isManager={isManager} isAdmin={isAdmin} />}
      {tab === "renewals" && <RenewalsTab onError={setError} />}
    </AppShell>
  );
}

function ContractsTab({
  onError, isManager, isAdmin,
}: { onError: (s: string) => void; isManager: boolean; isAdmin: boolean }) {
  const [rows, setRows] = useState<Contract[]>([]);
  const [page, setPage] = useState(1);
  const [meta, setMeta] = useState({ total: 0, pages: 1 });
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({
    contract_no: "", title: "", type: "customer", counterparty: "",
    start_date: "", end_date: "", value: "0", currency: "KRW",
    renewal: "manual", notice_period_days: "30",
  });

  const load = async () => {
    try {
      const r = await api<Page<Contract>>(`/api/contracts?page=${page}&size=20`);
      setRows(r.items);
      setMeta({ total: r.total, pages: r.pages });
    } catch (e) { onError(String(e)); }
  };
  useEffect(() => { load(); }, [page]);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    onError("");
    try {
      await api("/api/contracts", {
        method: "POST",
        body: JSON.stringify({
          ...form,
          value: Number(form.value),
          notice_period_days: Number(form.notice_period_days),
        }),
      });
      setShowForm(false);
      await load();
    } catch (e) { onError(String(e)); }
  };

  const activate = async (id: number) => {
    try {
      await api(`/api/contracts/${id}/activate`, { method: "POST" });
      await load();
    } catch (e) { onError(String(e)); }
  };

  const terminate = async (id: number) => {
    const reason = prompt("해지 사유");
    if (!reason) return;
    try {
      await api(`/api/contracts/${id}/terminate?reason=${encodeURIComponent(reason)}`, {
        method: "POST",
      });
      await load();
    } catch (e) { onError(String(e)); }
  };

  return (
    <>
      {isManager && (
        <div className="mb-3">
          <button
            onClick={() => setShowForm((s) => !s)}
            className="bg-slate-900 text-white px-3 py-1 rounded text-sm"
          >
            {showForm ? "닫기" : "+ 계약 등록"}
          </button>
        </div>
      )}
      {showForm && (
        <form onSubmit={submit} className="bg-white p-4 rounded-lg border border-slate-200 grid grid-cols-1 md:grid-cols-4 gap-2 mb-4">
          <input required placeholder="계약번호" value={form.contract_no}
                 onChange={(e) => setForm({ ...form, contract_no: e.target.value })}
                 className="border rounded px-2 py-1" />
          <input required placeholder="제목" value={form.title}
                 onChange={(e) => setForm({ ...form, title: e.target.value })}
                 className="border rounded px-2 py-1 col-span-2" />
          <select value={form.type} onChange={(e) => setForm({ ...form, type: e.target.value })}
                  className="border rounded px-2 py-1">
            <option value="customer">매출</option>
            <option value="supplier">매입</option>
            <option value="employment">고용</option>
            <option value="lease">임대</option>
            <option value="other">기타</option>
          </select>
          <input required placeholder="상대방" value={form.counterparty}
                 onChange={(e) => setForm({ ...form, counterparty: e.target.value })}
                 className="border rounded px-2 py-1" />
          <input required type="date" value={form.start_date}
                 onChange={(e) => setForm({ ...form, start_date: e.target.value })}
                 className="border rounded px-2 py-1" />
          <input required type="date" value={form.end_date}
                 onChange={(e) => setForm({ ...form, end_date: e.target.value })}
                 className="border rounded px-2 py-1" />
          <input type="number" placeholder="계약가" value={form.value}
                 onChange={(e) => setForm({ ...form, value: e.target.value })}
                 className="border rounded px-2 py-1" />
          <select value={form.renewal} onChange={(e) => setForm({ ...form, renewal: e.target.value })}
                  className="border rounded px-2 py-1">
            <option value="manual">수동 갱신</option>
            <option value="auto">자동 갱신</option>
            <option value="none">갱신 없음</option>
          </select>
          <input type="number" placeholder="통보기간(일)" value={form.notice_period_days}
                 onChange={(e) => setForm({ ...form, notice_period_days: e.target.value })}
                 className="border rounded px-2 py-1" />
          <button className="bg-emerald-700 text-white rounded col-span-4">저장</button>
        </form>
      )}
      <DataTable<Contract>
        rows={rows}
        columns={[
          { key: "contract_no", header: "번호" },
          { key: "title", header: "제목" },
          { key: "type", header: "유형" },
          { key: "counterparty", header: "상대방" },
          { key: "end_date", header: "만기" },
          { key: "renewal", header: "갱신" },
          {
            key: "value", header: "계약가",
            render: (r) => Number(r.value).toLocaleString(),
          },
          {
            key: "status", header: "상태",
            render: (r) => (
              <span className={
                r.status === "active" ? "text-emerald-700 font-medium" :
                r.status === "expired" ? "text-red-600 font-medium" : ""
              }>{r.status}</span>
            ),
          },
          {
            key: "_act", header: "관리", sortable: false,
            render: (r) => (
              <div className="flex gap-2">
                {isManager && r.status === "draft" && (
                  <button onClick={() => activate(r.id)}
                          className="text-emerald-700 text-xs hover:underline">활성화</button>
                )}
                {isAdmin && r.status === "active" && (
                  <button onClick={() => terminate(r.id)}
                          className="text-red-600 text-xs hover:underline">해지</button>
                )}
              </div>
            ),
          },
        ]}
      />
      <Pager page={page} pages={meta.pages} total={meta.total} onChange={setPage} />
    </>
  );
}

function RenewalsTab({ onError }: { onError: (s: string) => void }) {
  const [rows, setRows] = useState<Renewal[]>([]);
  const [within, setWithin] = useState("60");

  const load = async () => {
    try {
      const r = await api<{ contracts: Renewal[] }>(
        `/api/contracts/renewals-due?within_days=${within}`
      );
      setRows(r.contracts);
    } catch (e) { onError(String(e)); }
  };
  useEffect(() => { load(); }, [within]);

  return (
    <>
      <div className="bg-white p-4 rounded-lg border border-slate-200 mb-4 flex gap-2 items-center">
        <label className="text-sm">조회 기간 (일):</label>
        <input type="number" value={within} onChange={(e) => setWithin(e.target.value)}
               className="border rounded px-2 py-1 w-24" />
      </div>
      <DataTable<Renewal>
        rows={rows}
        columns={[
          { key: "contract_no", header: "번호" },
          { key: "title", header: "제목" },
          { key: "counterparty", header: "상대방" },
          { key: "end_date", header: "만기" },
          {
            key: "days_to_end", header: "잔여일",
            render: (r) => (
              <span className={r.days_to_end <= 30 ? "text-red-600 font-medium" : ""}>
                {r.days_to_end}일
              </span>
            ),
          },
          { key: "renewal", header: "갱신유형" },
          {
            key: "in_notice_window", header: "통보기간",
            render: (r) => r.in_notice_window
              ? <span className="text-orange-700 font-medium">진입</span>
              : <span className="text-slate-500">미진입</span>,
          },
          {
            key: "value", header: "계약가",
            render: (r) => r.value.toLocaleString(),
          },
        ]}
      />
    </>
  );
}
