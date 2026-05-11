"use client";
import { useEffect, useState } from "react";
import AppShell from "@/components/AppShell";
import DataTable from "@/components/DataTable";
import { api } from "@/lib/api";
import { hasRole, useMe } from "@/lib/auth";

type RFQ = {
  id: number;
  rfq_no: string;
  title: string;
  due_date: string | null;
  status: "draft" | "sent" | "closed" | "cancelled";
  awarded_response_id: number | null;
  items: { id: number; item_id: number; quantity: string }[];
};

type Response = {
  id: number;
  rfq_id: number;
  supplier_id: number;
  total: string;
  lead_time_days: number | null;
  status: "pending" | "submitted" | "awarded" | "rejected";
  lines: { rfq_item_id: number; unit_price: string }[];
};

type Scorecard = {
  supplier_id: number;
  supplier_code: string;
  supplier_name: string;
  po_count: number;
  on_time_rate: number | null;
  avg_lead_time_days: number | null;
  match_rate: number | null;
  total_value: number;
};

export default function RFQPage() {
  const me = useMe();
  const isManager = hasRole(me, "manager");
  const [tab, setTab] = useState<"rfqs" | "scorecard">("rfqs");
  const [error, setError] = useState("");
  return (
    <AppShell>
      <div className="flex justify-between items-center mb-4">
        <h1 className="text-2xl font-semibold">RFQ / 공급사 평가</h1>
        <div className="flex gap-1">
          {(["rfqs", "scorecard"] as const).map((t) => (
            <button
              key={t}
              onClick={() => setTab(t)}
              className={`px-3 py-1 text-sm rounded ${
                tab === t
                  ? "bg-slate-900 text-white"
                  : "bg-slate-100 hover:bg-slate-200"
              }`}
            >
              {t === "rfqs" ? "RFQ" : "공급사 스코어카드"}
            </button>
          ))}
        </div>
      </div>
      {error && <p className="text-red-600 text-sm mb-3">{error}</p>}
      {tab === "rfqs" && <RFQTab onError={setError} isManager={isManager} />}
      {tab === "scorecard" && <ScorecardTab onError={setError} />}
    </AppShell>
  );
}

function RFQTab({ onError, isManager }: { onError: (s: string) => void; isManager: boolean }) {
  const [rows, setRows] = useState<RFQ[]>([]);
  const [responses, setResponses] = useState<Response[]>([]);
  const [active, setActive] = useState<RFQ | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({
    rfq_no: "",
    title: "",
    due_date: "",
    items: [{ item_id: "", quantity: "1" }],
  });

  const load = async () => {
    try {
      setRows(await api<RFQ[]>("/api/suppliers/rfqs"));
    } catch (e) {
      onError(String(e));
    }
  };
  useEffect(() => {
    load();
  }, []);

  const loadResponses = async (rfq: RFQ) => {
    setActive(rfq);
    try {
      setResponses(await api<Response[]>(`/api/suppliers/rfqs/${rfq.id}/responses`));
    } catch (e) {
      onError(String(e));
    }
  };

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    onError("");
    try {
      await api("/api/suppliers/rfqs", {
        method: "POST",
        body: JSON.stringify({
          rfq_no: form.rfq_no,
          title: form.title,
          due_date: form.due_date || null,
          items: form.items.map((it) => ({
            item_id: Number(it.item_id),
            quantity: Number(it.quantity),
          })),
        }),
      });
      setShowForm(false);
      setForm({ rfq_no: "", title: "", due_date: "", items: [{ item_id: "", quantity: "1" }] });
      await load();
    } catch (e) {
      onError(String(e));
    }
  };

  const send = async (id: number) => {
    try {
      await api(`/api/suppliers/rfqs/${id}/send`, { method: "POST" });
      await load();
    } catch (e) {
      onError(String(e));
    }
  };

  const award = async (rfq_id: number, response_id: number) => {
    if (!confirm(`응답 #${response_id}를 낙찰하면 PO가 자동 생성됩니다. 진행할까요?`)) return;
    try {
      const res = await api<any>(
        `/api/suppliers/rfqs/${rfq_id}/award/${response_id}`,
        { method: "POST" }
      );
      alert(`PO ${res.po_no} 생성 완료`);
      await load();
      setActive(null);
    } catch (e) {
      onError(String(e));
    }
  };

  return (
    <>
      {isManager && (
        <div className="mb-3">
          <button
            onClick={() => setShowForm((s) => !s)}
            className="bg-slate-900 text-white px-3 py-1 rounded text-sm"
          >
            {showForm ? "닫기" : "+ RFQ 생성"}
          </button>
        </div>
      )}
      {showForm && (
        <form
          onSubmit={submit}
          className="bg-white p-4 rounded-lg border border-slate-200 mb-4 space-y-2"
        >
          <div className="grid grid-cols-1 md:grid-cols-3 gap-2">
            <input
              required
              placeholder="RFQ 번호"
              value={form.rfq_no}
              onChange={(e) => setForm({ ...form, rfq_no: e.target.value })}
              className="border rounded px-2 py-1"
            />
            <input
              required
              placeholder="제목"
              value={form.title}
              onChange={(e) => setForm({ ...form, title: e.target.value })}
              className="border rounded px-2 py-1"
            />
            <input
              type="date"
              value={form.due_date}
              onChange={(e) => setForm({ ...form, due_date: e.target.value })}
              className="border rounded px-2 py-1"
            />
          </div>
          {form.items.map((it, i) => (
            <div key={i} className="grid grid-cols-3 gap-2">
              <input
                required
                type="number"
                placeholder="품목 ID"
                value={it.item_id}
                onChange={(e) => {
                  const items = [...form.items];
                  items[i].item_id = e.target.value;
                  setForm({ ...form, items });
                }}
                className="border rounded px-2 py-1"
              />
              <input
                required
                type="number"
                placeholder="수량"
                value={it.quantity}
                onChange={(e) => {
                  const items = [...form.items];
                  items[i].quantity = e.target.value;
                  setForm({ ...form, items });
                }}
                className="border rounded px-2 py-1"
              />
              <button
                type="button"
                onClick={() => {
                  const items = form.items.filter((_, j) => j !== i);
                  setForm({ ...form, items: items.length ? items : form.items });
                }}
                className="text-red-600 text-sm"
              >
                삭제
              </button>
            </div>
          ))}
          <button
            type="button"
            onClick={() =>
              setForm({
                ...form,
                items: [...form.items, { item_id: "", quantity: "1" }],
              })
            }
            className="text-xs text-blue-700"
          >
            + 품목 추가
          </button>
          <button className="bg-emerald-700 text-white rounded px-4 py-1 block">
            저장
          </button>
        </form>
      )}

      <DataTable<RFQ>
        columns={[
          { key: "rfq_no", header: "RFQ" },
          { key: "title", header: "제목" },
          { key: "due_date", header: "마감일" },
          { key: "status", header: "상태" },
          {
            key: "items",
            header: "품목수",
            render: (r) => r.items.length,
          },
          {
            key: "_act",
            header: "관리",
            sortable: false,
            render: (r) => (
              <div className="flex gap-2">
                <button
                  onClick={() => loadResponses(r)}
                  className="text-blue-700 text-xs hover:underline"
                >
                  응답 보기
                </button>
                {isManager && r.status === "draft" && (
                  <button
                    onClick={() => send(r.id)}
                    className="text-emerald-700 text-xs hover:underline"
                  >
                    발송
                  </button>
                )}
              </div>
            ),
          },
        ]}
        rows={rows}
      />

      {active && (
        <div className="mt-4 bg-white p-4 rounded-lg border border-slate-200">
          <div className="flex justify-between items-center mb-2">
            <h2 className="text-lg font-medium">
              응답 — {active.rfq_no} (총액 오름차순)
            </h2>
            <button
              onClick={() => setActive(null)}
              className="text-slate-500 hover:text-slate-900"
            >
              ✕
            </button>
          </div>
          <table className="w-full text-sm">
            <thead className="bg-slate-100">
              <tr>
                <th className="px-2 py-1 text-left">공급사</th>
                <th className="px-2 py-1 text-right">총액</th>
                <th className="px-2 py-1 text-right">리드타임</th>
                <th className="px-2 py-1 text-left">상태</th>
                <th className="px-2 py-1 text-left">낙찰</th>
              </tr>
            </thead>
            <tbody>
              {responses.map((r) => (
                <tr key={r.id} className="border-t">
                  <td className="px-2 py-1">#{r.supplier_id}</td>
                  <td className="px-2 py-1 text-right font-semibold">
                    {Number(r.total).toLocaleString()}
                  </td>
                  <td className="px-2 py-1 text-right">
                    {r.lead_time_days ? `${r.lead_time_days}일` : "-"}
                  </td>
                  <td className="px-2 py-1">{r.status}</td>
                  <td className="px-2 py-1">
                    {isManager &&
                      active.status !== "closed" &&
                      r.status === "submitted" && (
                        <button
                          onClick={() => award(active.id, r.id)}
                          className="text-emerald-700 text-xs hover:underline"
                        >
                          → 낙찰 + PO
                        </button>
                      )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}

function ScorecardTab({ onError }: { onError: (s: string) => void }) {
  const [rows, setRows] = useState<Scorecard[]>([]);

  const load = async () => {
    try {
      const res = await api<{ scorecard: Scorecard[] }>("/api/suppliers/scorecard");
      setRows(res.scorecard);
    } catch (e) {
      onError(String(e));
    }
  };
  useEffect(() => {
    load();
  }, []);

  return (
    <DataTable<Scorecard>
      columns={[
        { key: "supplier_code", header: "코드" },
        { key: "supplier_name", header: "공급사" },
        { key: "po_count", header: "PO 수" },
        {
          key: "on_time_rate",
          header: "정시납기율",
          render: (r) =>
            r.on_time_rate !== null
              ? `${(r.on_time_rate * 100).toFixed(1)}%`
              : "-",
        },
        {
          key: "avg_lead_time_days",
          header: "평균리드(일)",
          render: (r) => r.avg_lead_time_days ?? "-",
        },
        {
          key: "match_rate",
          header: "매칭율",
          render: (r) =>
            r.match_rate !== null ? `${(r.match_rate * 100).toFixed(1)}%` : "-",
        },
        {
          key: "total_value",
          header: "거래액",
          render: (r) => r.total_value.toLocaleString(),
        },
      ]}
      rows={rows}
    />
  );
}
