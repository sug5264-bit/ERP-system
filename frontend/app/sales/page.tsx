"use client";
import { useEffect, useState } from "react";
import AppShell from "@/components/AppShell";
import DataTable from "@/components/DataTable";
import { api } from "@/lib/api";

type Customer = { id: number; name: string; email: string | null; company: string | null };
type Order = {
  id: number;
  order_no: string;
  order_date: string;
  status: string;
  total: string;
  customer: Customer | null;
};

export default function SalesPage() {
  const [customers, setCustomers] = useState<Customer[]>([]);
  const [orders, setOrders] = useState<Order[]>([]);
  const [form, setForm] = useState({ name: "", email: "", company: "" });
  const [error, setError] = useState("");

  const load = async () => {
    const [c, o] = await Promise.all([
      api<Customer[]>("/api/sales/customers"),
      api<Order[]>("/api/sales/orders"),
    ]);
    setCustomers(c);
    setOrders(o);
  };

  useEffect(() => {
    load().catch((e) => setError(String(e)));
  }, []);

  const addCustomer = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    try {
      await api("/api/sales/customers", {
        method: "POST",
        body: JSON.stringify({
          name: form.name,
          email: form.email || null,
          company: form.company || null,
        }),
      });
      setForm({ name: "", email: "", company: "" });
      await load();
    } catch (e) {
      setError(String(e));
    }
  };

  const confirmOrder = async (id: number) => {
    try {
      await api(`/api/sales/orders/${id}/confirm`, { method: "POST" });
      await load();
    } catch (e) {
      setError(String(e));
    }
  };

  return (
    <AppShell>
      <h1 className="text-2xl font-semibold mb-4">영업 / CRM</h1>

      <h2 className="text-lg font-medium mb-2">고객 추가</h2>
      <form
        onSubmit={addCustomer}
        className="bg-white p-4 rounded-lg shadow-sm border border-slate-200 grid grid-cols-1 md:grid-cols-4 gap-3 mb-6"
      >
        <input
          required
          placeholder="이름"
          value={form.name}
          onChange={(e) => setForm({ ...form, name: e.target.value })}
          className="border rounded px-2 py-1"
        />
        <input
          type="email"
          placeholder="이메일"
          value={form.email}
          onChange={(e) => setForm({ ...form, email: e.target.value })}
          className="border rounded px-2 py-1"
        />
        <input
          placeholder="회사"
          value={form.company}
          onChange={(e) => setForm({ ...form, company: e.target.value })}
          className="border rounded px-2 py-1"
        />
        <button className="bg-slate-900 text-white px-3 rounded">추가</button>
      </form>

      {error && <p className="text-red-600 text-sm mb-3">{error}</p>}

      <h2 className="text-lg font-medium mb-2">고객 ({customers.length})</h2>
      <div className="mb-6">
        <DataTable<Customer>
          columns={[
            { key: "name", header: "이름" },
            { key: "email", header: "이메일" },
            { key: "company", header: "회사" },
          ]}
          rows={customers}
        />
      </div>

      <h2 className="text-lg font-medium mb-2">주문</h2>
      <DataTable<Order>
        columns={[
          { key: "order_no", header: "주문번호" },
          { key: "order_date", header: "일자" },
          {
            key: "customer",
            header: "고객",
            render: (r) => r.customer?.name ?? "-",
          },
          { key: "status", header: "상태" },
          { key: "total", header: "금액" },
          {
            key: "action",
            header: "",
            render: (r) =>
              r.status === "draft" ? (
                <button
                  onClick={() => confirmOrder(r.id)}
                  className="px-2 py-1 bg-blue-600 text-white rounded text-xs"
                >
                  확정 (재고차감)
                </button>
              ) : null,
          },
        ]}
        rows={orders}
        empty="주문이 없습니다"
      />
    </AppShell>
  );
}
