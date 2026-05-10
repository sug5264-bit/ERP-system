"use client";
import { useEffect, useState } from "react";
import AppShell from "@/components/AppShell";
import DataTable from "@/components/DataTable";
import Pager from "@/components/Pager";
import { Page, api } from "@/lib/api";
import { hasRole, useMe } from "@/lib/auth";

type QuoteLine = {
  id?: number;
  item_id: number;
  quantity: string;
  unit_price: string;
};
type Quote = {
  id: number;
  quote_no: string;
  customer_id: number;
  issued_date: string;
  expires_date: string | null;
  status: string;
  total: string;
  notes: string | null;
  converted_order_id: number | null;
  items: QuoteLine[];
};

type InvoiceLine = {
  id?: number;
  description: string;
  item_id: number | null;
  quantity: string;
  unit_price: string;
  line_total?: string;
};
type Invoice = {
  id: number;
  invoice_no: string;
  customer_id: number;
  sales_order_id: number | null;
  issued_date: string;
  due_date: string | null;
  status: string;
  subtotal: string;
  tax: string;
  total: string;
  paid_amount: string;
  notes: string | null;
  items: InvoiceLine[];
};

type Payment = {
  id: number;
  invoice_id: number;
  paid_at: string;
  amount: string;
  method: string;
  reference: string | null;
};

type Tab = "quotes" | "invoices" | "payments";

export default function BillingPage() {
  const me = useMe();
  const canManage = hasRole(me, "manager");
  const isAdmin = hasRole(me, "admin");
  const [tab, setTab] = useState<Tab>("quotes");
  const [error, setError] = useState("");

  return (
    <AppShell>
      <div className="flex justify-between items-center mb-4">
        <h1 className="text-2xl font-semibold">청구 / Billing</h1>
        <div className="flex gap-1">
          {(["quotes", "invoices", "payments"] as Tab[]).map((t) => (
            <button
              key={t}
              onClick={() => setTab(t)}
              className={`px-3 py-1 text-sm rounded ${
                tab === t
                  ? "bg-slate-900 text-white"
                  : "bg-slate-100 hover:bg-slate-200"
              }`}
            >
              {t === "quotes" ? "견적서" : t === "invoices" ? "청구서" : "수금"}
            </button>
          ))}
        </div>
      </div>

      {error && <p className="text-red-600 text-sm mb-3">{error}</p>}

      {tab === "quotes" && (
        <QuotesTab onError={setError} canManage={canManage} />
      )}
      {tab === "invoices" && (
        <InvoicesTab onError={setError} canManage={canManage} isAdmin={isAdmin} />
      )}
      {tab === "payments" && (
        <PaymentsTab onError={setError} canManage={canManage} />
      )}
    </AppShell>
  );
}

function QuotesTab({
  onError,
  canManage,
}: {
  onError: (s: string) => void;
  canManage: boolean;
}) {
  const [rows, setRows] = useState<Quote[]>([]);
  const [page, setPage] = useState(1);
  const [meta, setMeta] = useState({ total: 0, pages: 1 });
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({
    quote_no: "",
    customer_id: "1",
    expires_date: "",
    notes: "",
    items: [{ item_id: "1", quantity: "1", unit_price: "0" }],
  });

  const load = async () => {
    try {
      const r = await api<Page<Quote>>(`/api/billing/quotes?page=${page}&size=20`);
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
      await api("/api/billing/quotes", {
        method: "POST",
        body: JSON.stringify({
          quote_no: form.quote_no,
          customer_id: Number(form.customer_id),
          expires_date: form.expires_date || null,
          notes: form.notes || null,
          items: form.items.map((l) => ({
            item_id: Number(l.item_id),
            quantity: Number(l.quantity),
            unit_price: Number(l.unit_price),
          })),
        }),
      });
      setShowForm(false);
      setForm({
        quote_no: "",
        customer_id: "1",
        expires_date: "",
        notes: "",
        items: [{ item_id: "1", quantity: "1", unit_price: "0" }],
      });
      await load();
    } catch (e) {
      onError(String(e));
    }
  };

  const convert = async (id: number) => {
    if (!confirm("견적서를 수주(SalesOrder)로 변환하시겠습니까?")) return;
    try {
      await api(`/api/billing/quotes/${id}/convert`, { method: "POST" });
      await load();
    } catch (e) {
      onError(String(e));
    }
  };

  return (
    <>
      {canManage && (
        <div className="mb-3">
          <button
            onClick={() => setShowForm((s) => !s)}
            className="bg-slate-900 text-white px-3 py-1 rounded text-sm"
          >
            {showForm ? "닫기" : "+ 견적서 추가"}
          </button>
        </div>
      )}
      {showForm && (
        <form
          onSubmit={submit}
          className="bg-white p-4 rounded-lg shadow-sm border border-slate-200 mb-4 space-y-3"
        >
          <div className="grid grid-cols-1 md:grid-cols-4 gap-2">
            <input
              required
              placeholder="견적번호"
              value={form.quote_no}
              onChange={(e) => setForm({ ...form, quote_no: e.target.value })}
              className="border rounded px-2 py-1"
            />
            <input
              required
              type="number"
              placeholder="고객 ID"
              value={form.customer_id}
              onChange={(e) =>
                setForm({ ...form, customer_id: e.target.value })
              }
              className="border rounded px-2 py-1"
            />
            <input
              type="date"
              placeholder="만료일"
              value={form.expires_date}
              onChange={(e) =>
                setForm({ ...form, expires_date: e.target.value })
              }
              className="border rounded px-2 py-1"
            />
            <input
              placeholder="비고"
              value={form.notes}
              onChange={(e) => setForm({ ...form, notes: e.target.value })}
              className="border rounded px-2 py-1"
            />
          </div>
          <div className="space-y-2">
            <p className="text-sm font-medium">품목</p>
            {form.items.map((l, i) => (
              <div key={i} className="grid grid-cols-4 gap-2">
                <input
                  required
                  type="number"
                  placeholder="품목 ID"
                  value={l.item_id}
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
                  value={l.quantity}
                  onChange={(e) => {
                    const items = [...form.items];
                    items[i].quantity = e.target.value;
                    setForm({ ...form, items });
                  }}
                  className="border rounded px-2 py-1"
                />
                <input
                  required
                  type="number"
                  placeholder="단가"
                  value={l.unit_price}
                  onChange={(e) => {
                    const items = [...form.items];
                    items[i].unit_price = e.target.value;
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
                  items: [
                    ...form.items,
                    { item_id: "1", quantity: "1", unit_price: "0" },
                  ],
                })
              }
              className="text-sm text-blue-700"
            >
              + 라인 추가
            </button>
          </div>
          <button className="bg-emerald-700 text-white px-4 py-1 rounded">
            저장
          </button>
        </form>
      )}

      <DataTable<Quote>
        columns={[
          { key: "quote_no", header: "견적번호" },
          { key: "customer_id", header: "고객" },
          { key: "issued_date", header: "발행일" },
          { key: "expires_date", header: "만료일" },
          { key: "status", header: "상태" },
          {
            key: "total",
            header: "합계",
            render: (r) => Number(r.total).toLocaleString(),
          },
          {
            key: "_act",
            header: "변환",
            sortable: false,
            render: (r) =>
              canManage && !r.converted_order_id ? (
                <button
                  onClick={() => convert(r.id)}
                  className="text-blue-700 text-xs hover:underline"
                >
                  → 수주
                </button>
              ) : r.converted_order_id ? (
                <span className="text-xs text-slate-500">
                  주문 #{r.converted_order_id}
                </span>
              ) : null,
          },
        ]}
        rows={rows}
      />
      <Pager page={page} pages={meta.pages} total={meta.total} onChange={setPage} />
    </>
  );
}

function InvoicesTab({
  onError,
  canManage,
  isAdmin,
}: {
  onError: (s: string) => void;
  canManage: boolean;
  isAdmin: boolean;
}) {
  const [rows, setRows] = useState<Invoice[]>([]);
  const [page, setPage] = useState(1);
  const [meta, setMeta] = useState({ total: 0, pages: 1 });
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({
    invoice_no: "",
    customer_id: "1",
    sales_order_id: "",
    due_date: "",
    tax_rate: "0.10",
    notes: "",
    items: [{ description: "", item_id: "", quantity: "1", unit_price: "0" }],
  });

  const load = async () => {
    try {
      const r = await api<Page<Invoice>>(`/api/billing/invoices?page=${page}&size=20`);
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
      await api("/api/billing/invoices", {
        method: "POST",
        body: JSON.stringify({
          invoice_no: form.invoice_no,
          customer_id: Number(form.customer_id),
          sales_order_id: form.sales_order_id
            ? Number(form.sales_order_id)
            : null,
          due_date: form.due_date || null,
          tax_rate: Number(form.tax_rate),
          notes: form.notes || null,
          items: form.items.map((l) => ({
            description: l.description,
            item_id: l.item_id ? Number(l.item_id) : null,
            quantity: Number(l.quantity),
            unit_price: Number(l.unit_price),
          })),
        }),
      });
      setShowForm(false);
      await load();
    } catch (e) {
      onError(String(e));
    }
  };

  const issue = async (id: number) => {
    try {
      await api(`/api/billing/invoices/${id}/issue`, { method: "POST" });
      await load();
    } catch (e) {
      onError(String(e));
    }
  };

  const cancel = async (id: number) => {
    if (!confirm("청구서를 취소하시겠습니까?")) return;
    try {
      await api(`/api/billing/invoices/${id}/cancel`, { method: "POST" });
      await load();
    } catch (e) {
      onError(String(e));
    }
  };

  return (
    <>
      {canManage && (
        <div className="mb-3">
          <button
            onClick={() => setShowForm((s) => !s)}
            className="bg-slate-900 text-white px-3 py-1 rounded text-sm"
          >
            {showForm ? "닫기" : "+ 청구서 추가"}
          </button>
        </div>
      )}
      {showForm && (
        <form
          onSubmit={submit}
          className="bg-white p-4 rounded-lg shadow-sm border border-slate-200 mb-4 space-y-3"
        >
          <div className="grid grid-cols-1 md:grid-cols-5 gap-2">
            <input
              required
              placeholder="청구번호"
              value={form.invoice_no}
              onChange={(e) => setForm({ ...form, invoice_no: e.target.value })}
              className="border rounded px-2 py-1"
            />
            <input
              required
              type="number"
              placeholder="고객 ID"
              value={form.customer_id}
              onChange={(e) =>
                setForm({ ...form, customer_id: e.target.value })
              }
              className="border rounded px-2 py-1"
            />
            <input
              type="number"
              placeholder="수주 ID"
              value={form.sales_order_id}
              onChange={(e) =>
                setForm({ ...form, sales_order_id: e.target.value })
              }
              className="border rounded px-2 py-1"
            />
            <input
              type="date"
              placeholder="만기일"
              value={form.due_date}
              onChange={(e) => setForm({ ...form, due_date: e.target.value })}
              className="border rounded px-2 py-1"
            />
            <input
              type="number"
              step="0.01"
              placeholder="세율 (0.10=10%)"
              value={form.tax_rate}
              onChange={(e) => setForm({ ...form, tax_rate: e.target.value })}
              className="border rounded px-2 py-1"
            />
          </div>
          <div className="space-y-2">
            <p className="text-sm font-medium">품목</p>
            {form.items.map((l, i) => (
              <div key={i} className="grid grid-cols-5 gap-2">
                <input
                  required
                  placeholder="설명"
                  value={l.description}
                  onChange={(e) => {
                    const items = [...form.items];
                    items[i].description = e.target.value;
                    setForm({ ...form, items });
                  }}
                  className="border rounded px-2 py-1 col-span-2"
                />
                <input
                  type="number"
                  placeholder="품목 ID(선택)"
                  value={l.item_id}
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
                  value={l.quantity}
                  onChange={(e) => {
                    const items = [...form.items];
                    items[i].quantity = e.target.value;
                    setForm({ ...form, items });
                  }}
                  className="border rounded px-2 py-1"
                />
                <input
                  required
                  type="number"
                  placeholder="단가"
                  value={l.unit_price}
                  onChange={(e) => {
                    const items = [...form.items];
                    items[i].unit_price = e.target.value;
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
                    { description: "", item_id: "", quantity: "1", unit_price: "0" },
                  ],
                })
              }
              className="text-sm text-blue-700"
            >
              + 라인 추가
            </button>
          </div>
          <button className="bg-emerald-700 text-white px-4 py-1 rounded">
            저장
          </button>
        </form>
      )}

      <DataTable<Invoice>
        columns={[
          { key: "invoice_no", header: "청구번호" },
          { key: "issued_date", header: "발행일" },
          { key: "due_date", header: "만기일" },
          { key: "status", header: "상태" },
          {
            key: "subtotal",
            header: "공급가액",
            render: (r) => Number(r.subtotal).toLocaleString(),
          },
          {
            key: "tax",
            header: "세액",
            render: (r) => Number(r.tax).toLocaleString(),
          },
          {
            key: "total",
            header: "합계",
            render: (r) => Number(r.total).toLocaleString(),
          },
          {
            key: "paid_amount",
            header: "수금액",
            render: (r) => Number(r.paid_amount).toLocaleString(),
          },
          {
            key: "_act",
            header: "관리",
            sortable: false,
            render: (r) => (
              <div className="flex gap-2">
                {canManage && r.status === "draft" && (
                  <button
                    onClick={() => issue(r.id)}
                    className="text-emerald-700 text-xs hover:underline"
                  >
                    발행
                  </button>
                )}
                {isAdmin && r.status !== "cancelled" && r.status !== "paid" && (
                  <button
                    onClick={() => cancel(r.id)}
                    className="text-red-600 text-xs hover:underline"
                  >
                    취소
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

function PaymentsTab({
  onError,
  canManage,
}: {
  onError: (s: string) => void;
  canManage: boolean;
}) {
  const [rows, setRows] = useState<Payment[]>([]);
  const [page, setPage] = useState(1);
  const [meta, setMeta] = useState({ total: 0, pages: 1 });
  const [form, setForm] = useState({
    invoice_id: "",
    amount: "0",
    paid_at: "",
    method: "bank_transfer",
    reference: "",
    notes: "",
  });

  const load = async () => {
    try {
      const r = await api<Page<Payment>>(`/api/billing/payments?page=${page}&size=20`);
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
      await api("/api/billing/payments", {
        method: "POST",
        body: JSON.stringify({
          invoice_id: Number(form.invoice_id),
          amount: Number(form.amount),
          paid_at: form.paid_at || null,
          method: form.method,
          reference: form.reference || null,
          notes: form.notes || null,
        }),
      });
      setForm({
        invoice_id: "",
        amount: "0",
        paid_at: "",
        method: "bank_transfer",
        reference: "",
        notes: "",
      });
      await load();
    } catch (e) {
      onError(String(e));
    }
  };

  return (
    <>
      {canManage && (
        <form
          onSubmit={submit}
          className="bg-white p-4 rounded-lg shadow-sm border border-slate-200 grid grid-cols-1 md:grid-cols-6 gap-2 mb-4"
        >
          <input
            required
            type="number"
            placeholder="청구서 ID"
            value={form.invoice_id}
            onChange={(e) => setForm({ ...form, invoice_id: e.target.value })}
            className="border rounded px-2 py-1"
          />
          <input
            required
            type="number"
            placeholder="금액"
            value={form.amount}
            onChange={(e) => setForm({ ...form, amount: e.target.value })}
            className="border rounded px-2 py-1"
          />
          <input
            type="date"
            value={form.paid_at}
            onChange={(e) => setForm({ ...form, paid_at: e.target.value })}
            className="border rounded px-2 py-1"
          />
          <select
            value={form.method}
            onChange={(e) => setForm({ ...form, method: e.target.value })}
            className="border rounded px-2 py-1"
          >
            <option value="bank_transfer">계좌이체</option>
            <option value="card">카드</option>
            <option value="cash">현금</option>
            <option value="check">수표</option>
          </select>
          <input
            placeholder="참조번호"
            value={form.reference}
            onChange={(e) => setForm({ ...form, reference: e.target.value })}
            className="border rounded px-2 py-1"
          />
          <button className="bg-slate-900 text-white px-3 rounded">기록</button>
        </form>
      )}
      <DataTable<Payment>
        columns={[
          { key: "id", header: "ID" },
          { key: "invoice_id", header: "청구서" },
          { key: "paid_at", header: "수금일" },
          {
            key: "amount",
            header: "금액",
            render: (r) => Number(r.amount).toLocaleString(),
          },
          { key: "method", header: "방법" },
          { key: "reference", header: "참조" },
        ]}
        rows={rows}
      />
      <Pager page={page} pages={meta.pages} total={meta.total} onChange={setPage} />
    </>
  );
}
