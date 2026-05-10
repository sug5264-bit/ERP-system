"use client";
import { useEffect, useState } from "react";
import AppShell from "@/components/AppShell";
import DataTable from "@/components/DataTable";
import Pager from "@/components/Pager";
import { Page, api } from "@/lib/api";
import { hasRole, useMe } from "@/lib/auth";

type ETax = {
  id: number;
  type: "sales" | "purchase";
  status: "draft" | "submitted" | "accepted" | "rejected" | "cancelled";
  nts_no: string | null;
  invoice_id: number | null;
  supplier_invoice_id: number | null;
  issued_date: string;
  supplier_business_no: string;
  supplier_name: string;
  buyer_business_no: string;
  buyer_name: string;
  item_summary: string;
  subtotal: string;
  tax: string;
  total: string;
  submitted_at: string | null;
  response_message: string | null;
};

export default function ETaxPage() {
  const me = useMe();
  const isManager = hasRole(me, "manager");
  const isAdmin = hasRole(me, "admin");
  const [rows, setRows] = useState<ETax[]>([]);
  const [page, setPage] = useState(1);
  const [meta, setMeta] = useState({ total: 0, pages: 1 });
  const [error, setError] = useState("");
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({
    type: "sales",
    issued_date: "",
    supplier_business_no: "",
    supplier_name: "",
    buyer_business_no: "",
    buyer_name: "",
    item_summary: "",
    subtotal: "0",
    tax: "0",
    total: "0",
  });

  const load = async () => {
    try {
      const r = await api<Page<ETax>>(`/api/etax?page=${page}&size=20`);
      setRows(r.items);
      setMeta({ total: r.total, pages: r.pages });
    } catch (e) {
      setError(String(e));
    }
  };
  useEffect(() => {
    load();
  }, [page]);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    try {
      await api("/api/etax", {
        method: "POST",
        body: JSON.stringify({
          ...form,
          subtotal: Number(form.subtotal),
          tax: Number(form.tax),
          total: Number(form.total),
        }),
      });
      setShowForm(false);
      await load();
    } catch (e) {
      setError(String(e));
    }
  };

  const submitToNTS = async (id: number) => {
    if (!confirm("국세청 홈택스에 제출할까요?")) return;
    try {
      await api(`/api/etax/${id}/submit`, { method: "POST" });
      await load();
    } catch (e) {
      setError(String(e));
    }
  };

  const cancel = async (id: number) => {
    if (!confirm("취소하시겠습니까?")) return;
    try {
      await api(`/api/etax/${id}/cancel`, { method: "POST" });
      await load();
    } catch (e) {
      setError(String(e));
    }
  };

  return (
    <AppShell>
      <div className="flex justify-between items-center mb-4">
        <h1 className="text-2xl font-semibold">전자세금계산서</h1>
        <button
          onClick={() => setShowForm((s) => !s)}
          className="bg-slate-900 text-white px-3 py-1 rounded text-sm"
        >
          {showForm ? "닫기" : "+ 신규 작성"}
        </button>
      </div>
      {error && <p className="text-red-600 text-sm mb-3">{error}</p>}

      {showForm && (
        <form
          onSubmit={submit}
          className="bg-white p-4 rounded-lg border border-slate-200 mb-4 grid grid-cols-1 md:grid-cols-3 gap-2"
        >
          <select
            value={form.type}
            onChange={(e) => setForm({ ...form, type: e.target.value })}
            className="border rounded px-2 py-1"
          >
            <option value="sales">매출 (sales)</option>
            <option value="purchase">매입 (purchase)</option>
          </select>
          <input
            required
            type="date"
            value={form.issued_date}
            onChange={(e) => setForm({ ...form, issued_date: e.target.value })}
            className="border rounded px-2 py-1"
          />
          <input
            required
            placeholder="공급자 사업자번호 (10자리)"
            value={form.supplier_business_no}
            onChange={(e) =>
              setForm({ ...form, supplier_business_no: e.target.value })
            }
            className="border rounded px-2 py-1"
          />
          <input
            required
            placeholder="공급자명"
            value={form.supplier_name}
            onChange={(e) => setForm({ ...form, supplier_name: e.target.value })}
            className="border rounded px-2 py-1"
          />
          <input
            required
            placeholder="공급받는자 사업자번호"
            value={form.buyer_business_no}
            onChange={(e) =>
              setForm({ ...form, buyer_business_no: e.target.value })
            }
            className="border rounded px-2 py-1"
          />
          <input
            required
            placeholder="공급받는자명"
            value={form.buyer_name}
            onChange={(e) => setForm({ ...form, buyer_name: e.target.value })}
            className="border rounded px-2 py-1"
          />
          <input
            required
            placeholder="품목 요약"
            value={form.item_summary}
            onChange={(e) => setForm({ ...form, item_summary: e.target.value })}
            className="border rounded px-2 py-1 col-span-1 md:col-span-3"
          />
          <input
            required
            type="number"
            placeholder="공급가액"
            value={form.subtotal}
            onChange={(e) => setForm({ ...form, subtotal: e.target.value })}
            className="border rounded px-2 py-1"
          />
          <input
            required
            type="number"
            placeholder="세액"
            value={form.tax}
            onChange={(e) => setForm({ ...form, tax: e.target.value })}
            className="border rounded px-2 py-1"
          />
          <input
            required
            type="number"
            placeholder="합계"
            value={form.total}
            onChange={(e) => setForm({ ...form, total: e.target.value })}
            className="border rounded px-2 py-1"
          />
          <button className="bg-emerald-700 text-white rounded col-span-1 md:col-span-3">
            저장
          </button>
        </form>
      )}

      <DataTable<ETax>
        columns={[
          { key: "issued_date", header: "발행일" },
          { key: "type", header: "구분" },
          { key: "supplier_name", header: "공급자" },
          { key: "buyer_name", header: "공급받는자" },
          {
            key: "total",
            header: "합계",
            render: (r) => Number(r.total).toLocaleString(),
          },
          { key: "nts_no", header: "NTS 승인번호" },
          {
            key: "status",
            header: "상태",
            render: (r) => (
              <span
                className={
                  r.status === "accepted"
                    ? "text-emerald-700 font-medium"
                    : r.status === "rejected"
                    ? "text-red-600 font-medium"
                    : ""
                }
              >
                {r.status}
              </span>
            ),
          },
          {
            key: "_act",
            header: "관리",
            sortable: false,
            render: (r) => (
              <div className="flex gap-2">
                {isManager && r.status === "draft" && (
                  <button
                    onClick={() => submitToNTS(r.id)}
                    className="text-blue-700 text-xs hover:underline"
                  >
                    NTS 제출
                  </button>
                )}
                {isAdmin && r.status !== "cancelled" && (
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
    </AppShell>
  );
}
