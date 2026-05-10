"use client";
import { useEffect, useState } from "react";
import AppShell from "@/components/AppShell";
import DataTable from "@/components/DataTable";
import Pager from "@/components/Pager";
import { Page, api } from "@/lib/api";
import { hasRole, useMe } from "@/lib/auth";

type Asset = {
  id: number;
  asset_no: string;
  name: string;
  category_id: number | null;
  acquired_date: string;
  acquired_cost: string;
  salvage_value: string;
  useful_life_months: number;
  method: "straight_line" | "declining_balance";
  accumulated_depreciation: string;
  book_value: string;
  status: "active" | "disposed";
  disposed_date: string | null;
};

type DepEntry = {
  id: number;
  asset_id: number;
  period_code: string;
  amount: number;
  journal_entry_id: number | null;
};

export default function AssetsPage() {
  const me = useMe();
  const isAdmin = hasRole(me, "admin");
  const [tab, setTab] = useState<"assets" | "deps">("assets");
  const [error, setError] = useState("");

  return (
    <AppShell>
      <div className="flex justify-between items-center mb-4">
        <h1 className="text-2xl font-semibold">자산 / 감가상각</h1>
        <div className="flex gap-1">
          {(["assets", "deps"] as const).map((t) => (
            <button
              key={t}
              onClick={() => setTab(t)}
              className={`px-3 py-1 text-sm rounded ${
                tab === t
                  ? "bg-slate-900 text-white"
                  : "bg-slate-100 hover:bg-slate-200"
              }`}
            >
              {t === "assets" ? "자산 대장" : "감가상각 내역"}
            </button>
          ))}
        </div>
      </div>
      {error && <p className="text-red-600 text-sm mb-3">{error}</p>}
      {tab === "assets" && <AssetsTab onError={setError} isAdmin={isAdmin} />}
      {tab === "deps" && <DepsTab onError={setError} isAdmin={isAdmin} />}
    </AppShell>
  );
}

function AssetsTab({
  onError,
  isAdmin,
}: {
  onError: (s: string) => void;
  isAdmin: boolean;
}) {
  const [rows, setRows] = useState<Asset[]>([]);
  const [page, setPage] = useState(1);
  const [meta, setMeta] = useState({ total: 0, pages: 1 });
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({
    asset_no: "",
    name: "",
    acquired_date: "",
    acquired_cost: "",
    salvage_value: "0",
    useful_life_months: "60",
    method: "straight_line",
  });

  const load = async () => {
    try {
      const r = await api<Page<Asset>>(`/api/assets/assets?page=${page}&size=20`);
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
      await api("/api/assets/assets", {
        method: "POST",
        body: JSON.stringify({
          ...form,
          acquired_cost: Number(form.acquired_cost),
          salvage_value: Number(form.salvage_value),
          useful_life_months: Number(form.useful_life_months),
        }),
      });
      setShowForm(false);
      setForm({
        asset_no: "",
        name: "",
        acquired_date: "",
        acquired_cost: "",
        salvage_value: "0",
        useful_life_months: "60",
        method: "straight_line",
      });
      await load();
    } catch (e) {
      onError(String(e));
    }
  };

  const dispose = async (id: number) => {
    if (!confirm("자산을 처분 처리하시겠습니까?")) return;
    try {
      await api(`/api/assets/assets/${id}/dispose`, { method: "POST" });
      await load();
    } catch (e) {
      onError(String(e));
    }
  };

  return (
    <>
      {isAdmin && (
        <div className="mb-3">
          <button
            onClick={() => setShowForm((s) => !s)}
            className="bg-slate-900 text-white px-3 py-1 rounded text-sm"
          >
            {showForm ? "닫기" : "+ 자산 등록"}
          </button>
        </div>
      )}
      {showForm && (
        <form
          onSubmit={submit}
          className="bg-white p-4 rounded-lg shadow-sm border border-slate-200 grid grid-cols-1 md:grid-cols-4 gap-2 mb-4"
        >
          <input
            required
            placeholder="자산번호"
            value={form.asset_no}
            onChange={(e) => setForm({ ...form, asset_no: e.target.value })}
            className="border rounded px-2 py-1"
          />
          <input
            required
            placeholder="명칭"
            value={form.name}
            onChange={(e) => setForm({ ...form, name: e.target.value })}
            className="border rounded px-2 py-1"
          />
          <input
            required
            type="date"
            value={form.acquired_date}
            onChange={(e) => setForm({ ...form, acquired_date: e.target.value })}
            className="border rounded px-2 py-1"
          />
          <input
            required
            type="number"
            placeholder="취득원가"
            value={form.acquired_cost}
            onChange={(e) => setForm({ ...form, acquired_cost: e.target.value })}
            className="border rounded px-2 py-1"
          />
          <input
            type="number"
            placeholder="잔존가치"
            value={form.salvage_value}
            onChange={(e) => setForm({ ...form, salvage_value: e.target.value })}
            className="border rounded px-2 py-1"
          />
          <input
            required
            type="number"
            placeholder="내용연수(월)"
            value={form.useful_life_months}
            onChange={(e) =>
              setForm({ ...form, useful_life_months: e.target.value })
            }
            className="border rounded px-2 py-1"
          />
          <select
            value={form.method}
            onChange={(e) => setForm({ ...form, method: e.target.value })}
            className="border rounded px-2 py-1"
          >
            <option value="straight_line">정액법</option>
            <option value="declining_balance">정률법</option>
          </select>
          <button className="bg-emerald-700 text-white rounded">저장</button>
        </form>
      )}
      <DataTable<Asset>
        columns={[
          { key: "asset_no", header: "번호" },
          { key: "name", header: "명칭" },
          { key: "acquired_date", header: "취득일" },
          {
            key: "acquired_cost",
            header: "취득원가",
            render: (r) => Number(r.acquired_cost).toLocaleString(),
          },
          {
            key: "accumulated_depreciation",
            header: "감가누계",
            render: (r) => Number(r.accumulated_depreciation).toLocaleString(),
          },
          {
            key: "book_value",
            header: "장부가",
            render: (r) => (
              <span className="font-semibold">
                {Number(r.book_value).toLocaleString()}
              </span>
            ),
          },
          { key: "method", header: "방법" },
          { key: "status", header: "상태" },
          {
            key: "_act",
            header: "관리",
            sortable: false,
            render: (r) =>
              isAdmin && r.status === "active" ? (
                <button
                  onClick={() => dispose(r.id)}
                  className="text-red-600 text-xs hover:underline"
                >
                  처분
                </button>
              ) : null,
          },
        ]}
        rows={rows}
      />
      <Pager page={page} pages={meta.pages} total={meta.total} onChange={setPage} />
    </>
  );
}

function DepsTab({
  onError,
  isAdmin,
}: {
  onError: (s: string) => void;
  isAdmin: boolean;
}) {
  const [rows, setRows] = useState<DepEntry[]>([]);
  const [period, setPeriod] = useState("");
  const [runResult, setRunResult] = useState<any>(null);

  const load = async () => {
    try {
      const q = period ? `?period_code=${period}` : "";
      setRows(await api<DepEntry[]>(`/api/assets/depreciation${q}`));
    } catch (e) {
      onError(String(e));
    }
  };
  useEffect(() => {
    load();
  }, [period]);

  const run = async () => {
    onError("");
    if (!period) {
      onError("기간(YYYY-MM)을 입력하세요");
      return;
    }
    try {
      setRunResult(
        await api(`/api/assets/depreciation/run?period_code=${period}`, {
          method: "POST",
        })
      );
      await load();
    } catch (e) {
      onError(String(e));
    }
  };

  return (
    <>
      <div className="bg-white p-4 rounded-lg shadow-sm border border-slate-200 mb-4 flex gap-2 items-center">
        <input
          placeholder="기간 (YYYY-MM)"
          value={period}
          onChange={(e) => setPeriod(e.target.value)}
          className="border rounded px-2 py-1"
        />
        {isAdmin && (
          <button
            onClick={run}
            className="bg-emerald-700 text-white px-3 py-1 rounded text-sm"
          >
            ▶ 감가상각 실행
          </button>
        )}
        {runResult && (
          <span className="text-sm text-slate-600">
            신규 {runResult.new_entries}건 / 스킵 {runResult.skipped}건 / 합계{" "}
            {runResult.total_amount?.toLocaleString()}원
          </span>
        )}
      </div>
      <table className="text-sm w-full bg-white">
        <thead className="bg-slate-100">
          <tr>
            <th className="px-2 py-1 text-left">자산 ID</th>
            <th className="px-2 py-1 text-left">기간</th>
            <th className="px-2 py-1 text-right">금액</th>
            <th className="px-2 py-1 text-left">분개 ID</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.id} className="border-t">
              <td className="px-2 py-1">{r.asset_id}</td>
              <td className="px-2 py-1">{r.period_code}</td>
              <td className="px-2 py-1 text-right">
                {r.amount.toLocaleString()}
              </td>
              <td className="px-2 py-1">{r.journal_entry_id ?? "-"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </>
  );
}
