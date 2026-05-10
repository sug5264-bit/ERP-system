"use client";
import { useEffect, useState } from "react";
import AppShell from "@/components/AppShell";
import DataTable from "@/components/DataTable";
import Pager from "@/components/Pager";
import { Page, api } from "@/lib/api";
import { hasRole, useMe } from "@/lib/auth";

type GR = {
  id: number;
  gr_no: string;
  po_id: number;
  received_date: string;
  status: "draft" | "posted";
  notes: string | null;
  items: { id: number; po_item_id: number; received_qty: string; lot_id: number | null }[];
};

type SupInv = {
  id: number;
  supplier_id: number;
  po_id: number | null;
  vendor_invoice_no: string;
  invoice_date: string;
  subtotal: string;
  tax: string;
  total: string;
  status: "pending" | "matched" | "rejected" | "paid";
  match_notes: string | null;
};

type Tab = "gr" | "si";

export default function MatchingPage() {
  const me = useMe();
  const isAdmin = hasRole(me, "admin");
  const isManager = hasRole(me, "manager");
  const [tab, setTab] = useState<Tab>("gr");
  const [error, setError] = useState("");
  return (
    <AppShell>
      <div className="flex justify-between items-center mb-4">
        <h1 className="text-2xl font-semibold">3-way 매칭 (입고 / 매입세금)</h1>
        <div className="flex gap-1">
          {(["gr", "si"] as Tab[]).map((t) => (
            <button
              key={t}
              onClick={() => setTab(t)}
              className={`px-3 py-1 text-sm rounded ${
                tab === t
                  ? "bg-slate-900 text-white"
                  : "bg-slate-100 hover:bg-slate-200"
              }`}
            >
              {t === "gr" ? "입고증 (GR)" : "매입 세금계산서"}
            </button>
          ))}
        </div>
      </div>
      {error && <p className="text-red-600 text-sm mb-3">{error}</p>}
      {tab === "gr" && <GRTab onError={setError} isManager={isManager} />}
      {tab === "si" && (
        <SITab onError={setError} isManager={isManager} isAdmin={isAdmin} />
      )}
    </AppShell>
  );
}

function GRTab({
  onError,
  isManager,
}: {
  onError: (s: string) => void;
  isManager: boolean;
}) {
  const [rows, setRows] = useState<GR[]>([]);
  const [page, setPage] = useState(1);
  const [meta, setMeta] = useState({ total: 0, pages: 1 });
  const [form, setForm] = useState({
    gr_no: "",
    po_id: "",
    received_date: "",
    items: [{ po_item_id: "", received_qty: "1", lot_id: "" }],
  });

  const load = async () => {
    try {
      const r = await api<Page<GR>>(
        `/api/suppliers/goods-receipts?page=${page}&size=20`
      );
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
      await api("/api/suppliers/goods-receipts", {
        method: "POST",
        body: JSON.stringify({
          gr_no: form.gr_no,
          po_id: Number(form.po_id),
          received_date: form.received_date || null,
          items: form.items.map((i) => ({
            po_item_id: Number(i.po_item_id),
            received_qty: Number(i.received_qty),
            lot_id: i.lot_id ? Number(i.lot_id) : null,
          })),
        }),
      });
      setForm({
        gr_no: "",
        po_id: "",
        received_date: "",
        items: [{ po_item_id: "", received_qty: "1", lot_id: "" }],
      });
      await load();
    } catch (e) {
      onError(String(e));
    }
  };

  const post = async (id: number) => {
    if (!confirm("입고증을 확정(posting)하면 재고에 반영됩니다. 진행할까요?")) return;
    try {
      await api(`/api/suppliers/goods-receipts/${id}/post`, { method: "POST" });
      await load();
    } catch (e) {
      onError(String(e));
    }
  };

  return (
    <>
      <form
        onSubmit={submit}
        className="bg-white p-4 rounded-lg shadow-sm border border-slate-200 mb-4 space-y-2"
      >
        <div className="grid grid-cols-1 md:grid-cols-4 gap-2">
          <input
            required
            placeholder="GR 번호"
            value={form.gr_no}
            onChange={(e) => setForm({ ...form, gr_no: e.target.value })}
            className="border rounded px-2 py-1"
          />
          <input
            required
            type="number"
            placeholder="PO ID"
            value={form.po_id}
            onChange={(e) => setForm({ ...form, po_id: e.target.value })}
            className="border rounded px-2 py-1"
          />
          <input
            type="date"
            value={form.received_date}
            onChange={(e) =>
              setForm({ ...form, received_date: e.target.value })
            }
            className="border rounded px-2 py-1"
          />
          <button className="bg-emerald-700 text-white rounded">
            + GR 생성
          </button>
        </div>
        <p className="text-xs text-slate-500">PO 라인별 수령</p>
        {form.items.map((it, i) => (
          <div key={i} className="grid grid-cols-3 gap-2">
            <input
              required
              type="number"
              placeholder="PO 라인 ID"
              value={it.po_item_id}
              onChange={(e) => {
                const items = [...form.items];
                items[i].po_item_id = e.target.value;
                setForm({ ...form, items });
              }}
              className="border rounded px-2 py-1"
            />
            <input
              required
              type="number"
              placeholder="수령 수량"
              value={it.received_qty}
              onChange={(e) => {
                const items = [...form.items];
                items[i].received_qty = e.target.value;
                setForm({ ...form, items });
              }}
              className="border rounded px-2 py-1"
            />
            <input
              type="number"
              placeholder="Lot ID (선택)"
              value={it.lot_id}
              onChange={(e) => {
                const items = [...form.items];
                items[i].lot_id = e.target.value;
                setForm({ ...form, items });
              }}
              className="border rounded px-2 py-1"
            />
          </div>
        ))}
        <button
          type="button"
          onClick={() =>
            setForm({
              ...form,
              items: [
                ...form.items,
                { po_item_id: "", received_qty: "1", lot_id: "" },
              ],
            })
          }
          className="text-xs text-blue-700"
        >
          + 라인 추가
        </button>
      </form>

      <DataTable<GR>
        columns={[
          { key: "gr_no", header: "GR" },
          { key: "po_id", header: "PO" },
          { key: "received_date", header: "수령일" },
          { key: "status", header: "상태" },
          {
            key: "items",
            header: "라인",
            render: (r) => `${r.items.length}건`,
          },
          {
            key: "_act",
            header: "관리",
            sortable: false,
            render: (r) =>
              isManager && r.status === "draft" ? (
                <button
                  onClick={() => post(r.id)}
                  className="text-emerald-700 text-xs hover:underline"
                >
                  Post (재고반영)
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

function SITab({
  onError,
  isManager,
  isAdmin,
}: {
  onError: (s: string) => void;
  isManager: boolean;
  isAdmin: boolean;
}) {
  const [rows, setRows] = useState<SupInv[]>([]);
  const [page, setPage] = useState(1);
  const [meta, setMeta] = useState({ total: 0, pages: 1 });
  const [form, setForm] = useState({
    supplier_id: "",
    po_id: "",
    vendor_invoice_no: "",
    invoice_date: "",
    subtotal: "0",
    tax: "0",
    total: "0",
  });

  const load = async () => {
    try {
      const r = await api<Page<SupInv>>(
        `/api/suppliers/supplier-invoices?page=${page}&size=20`
      );
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
      await api("/api/suppliers/supplier-invoices", {
        method: "POST",
        body: JSON.stringify({
          supplier_id: Number(form.supplier_id),
          po_id: form.po_id ? Number(form.po_id) : null,
          vendor_invoice_no: form.vendor_invoice_no,
          invoice_date: form.invoice_date,
          subtotal: Number(form.subtotal),
          tax: Number(form.tax),
          total: Number(form.total),
        }),
      });
      setForm({
        supplier_id: "",
        po_id: "",
        vendor_invoice_no: "",
        invoice_date: "",
        subtotal: "0",
        tax: "0",
        total: "0",
      });
      await load();
    } catch (e) {
      onError(String(e));
    }
  };

  const matchNow = async (id: number) => {
    try {
      await api(`/api/suppliers/supplier-invoices/${id}/match`, {
        method: "POST",
      });
      await load();
    } catch (e) {
      onError(String(e));
    }
  };

  const markPaid = async (id: number) => {
    if (!confirm("매입 인보이스를 지급 완료로 표시할까요?")) return;
    try {
      await api(`/api/suppliers/supplier-invoices/${id}/mark-paid`, {
        method: "POST",
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
        className="bg-white p-4 rounded-lg shadow-sm border border-slate-200 grid grid-cols-1 md:grid-cols-4 gap-2 mb-4"
      >
        <input
          required
          type="number"
          placeholder="공급사 ID"
          value={form.supplier_id}
          onChange={(e) => setForm({ ...form, supplier_id: e.target.value })}
          className="border rounded px-2 py-1"
        />
        <input
          type="number"
          placeholder="PO ID (선택)"
          value={form.po_id}
          onChange={(e) => setForm({ ...form, po_id: e.target.value })}
          className="border rounded px-2 py-1"
        />
        <input
          required
          placeholder="공급사 송장번호"
          value={form.vendor_invoice_no}
          onChange={(e) =>
            setForm({ ...form, vendor_invoice_no: e.target.value })
          }
          className="border rounded px-2 py-1"
        />
        <input
          required
          type="date"
          value={form.invoice_date}
          onChange={(e) => setForm({ ...form, invoice_date: e.target.value })}
          className="border rounded px-2 py-1"
        />
        <input
          type="number"
          placeholder="공급가액"
          value={form.subtotal}
          onChange={(e) => setForm({ ...form, subtotal: e.target.value })}
          className="border rounded px-2 py-1"
        />
        <input
          type="number"
          placeholder="세액"
          value={form.tax}
          onChange={(e) => setForm({ ...form, tax: e.target.value })}
          className="border rounded px-2 py-1"
        />
        <input
          type="number"
          placeholder="합계"
          value={form.total}
          onChange={(e) => setForm({ ...form, total: e.target.value })}
          className="border rounded px-2 py-1"
        />
        <button className="bg-slate-900 text-white rounded">+ 등록</button>
      </form>

      <DataTable<SupInv>
        columns={[
          { key: "vendor_invoice_no", header: "송장번호" },
          { key: "invoice_date", header: "발행일" },
          { key: "supplier_id", header: "공급사" },
          { key: "po_id", header: "PO" },
          {
            key: "total",
            header: "합계",
            render: (r) => Number(r.total).toLocaleString(),
          },
          {
            key: "status",
            header: "상태",
            render: (r) => (
              <span
                className={
                  r.status === "matched"
                    ? "text-emerald-700 font-medium"
                    : r.status === "rejected"
                    ? "text-red-600 font-medium"
                    : r.status === "paid"
                    ? "text-blue-700 font-medium"
                    : ""
                }
              >
                {r.status}
              </span>
            ),
          },
          { key: "match_notes", header: "비고" },
          {
            key: "_act",
            header: "관리",
            sortable: false,
            render: (r) => (
              <div className="flex gap-2">
                {isManager &&
                  (r.status === "pending" || r.status === "rejected") && (
                    <button
                      onClick={() => matchNow(r.id)}
                      className="text-blue-700 text-xs hover:underline"
                    >
                      3-way 매칭
                    </button>
                  )}
                {isAdmin && r.status === "matched" && (
                  <button
                    onClick={() => markPaid(r.id)}
                    className="text-emerald-700 text-xs hover:underline"
                  >
                    지급완료
                  </button>
                )}
              </div>
            ),
          },
        ]}
        rows={rows}
      />
      <Pager page={page} pages={meta.pages} total={meta.total} onChange={setPage} />
    </>
  );
}
