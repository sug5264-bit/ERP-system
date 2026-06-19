"use client";
import { useEffect, useState } from "react";
import AppShell from "@/components/AppShell";
import DataTable from "@/components/DataTable";
import EditDeleteActions from "@/components/EditDeleteActions";
import ExportMenu from "@/components/ExportMenu";
import Pager from "@/components/Pager";
import { Page, api } from "@/lib/api";

type Customer = { id: number; name: string; email: string | null; company: string | null };
type Item = { id: number; sku: string; name: string; unit_price: string; stock_qty: string };
type Order = {
  id: number;
  order_no: string;
  order_date: string;
  status: string;
  total: string;
  customer: Customer | null;
};

type OrderLineDraft = { item_id: string; quantity: string; unit_price: string };

const emptyLine: OrderLineDraft = { item_id: "", quantity: "1", unit_price: "0" };

export default function SalesPage() {
  const [customers, setCustomers] = useState<Customer[]>([]);
  const [items, setItems] = useState<Item[]>([]);
  const [orders, setOrders] = useState<Order[]>([]);
  const [error, setError] = useState("");

  const [custForm, setCustForm] = useState({
    name: "",
    email: "",
    company: "",
    business_no: "",
    representative: "",
    address: "",
    phone: "",
  });
  const [showCustExtra, setShowCustExtra] = useState(false);

  const [orderNo, setOrderNo] = useState("");
  const [customerId, setCustomerId] = useState("");
  const [orderLines, setOrderLines] = useState<OrderLineDraft[]>([{ ...emptyLine }]);

  const [orderPage, setOrderPage] = useState(1);
  const [orderMeta, setOrderMeta] = useState({ total: 0, pages: 1 });
  const [custPage, setCustPage] = useState(1);
  const [custMeta, setCustMeta] = useState({ total: 0, pages: 1 });

  const load = async () => {
    const [c, i, o] = await Promise.all([
      api<Page<Customer>>(`/api/sales/customers?page=${custPage}&size=20`),
      api<Page<Item>>("/api/inventory/items?page=1&size=200"),
      api<Page<Order>>(`/api/sales/orders?page=${orderPage}&size=20`),
    ]);
    setCustomers(c.items);
    setCustMeta({ total: c.total, pages: c.pages });
    setItems(i.items);
    setOrders(o.items);
    setOrderMeta({ total: o.total, pages: o.pages });
  };

  useEffect(() => {
    load().catch((e) => setError(String(e)));
  }, [orderPage, custPage]);

  const addCustomer = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    try {
      await api("/api/sales/customers", {
        method: "POST",
        body: JSON.stringify({
          name: custForm.name,
          email: custForm.email || null,
          company: custForm.company || null,
          business_no: custForm.business_no || null,
          representative: custForm.representative || null,
          address: custForm.address || null,
          phone: custForm.phone || null,
        }),
      });
      setCustForm({
        name: "",
        email: "",
        company: "",
        business_no: "",
        representative: "",
        address: "",
        phone: "",
      });
      await load();
    } catch (e) {
      setError(String(e));
    }
  };

  const updateLine = (idx: number, patch: Partial<OrderLineDraft>) => {
    setOrderLines((prev) =>
      prev.map((l, i) => {
        if (i !== idx) return l;
        const next = { ...l, ...patch };
        if (patch.item_id) {
          const it = items.find((x) => String(x.id) === patch.item_id);
          if (it) next.unit_price = it.unit_price;
        }
        return next;
      })
    );
  };

  const orderTotal = orderLines.reduce(
    (s, l) => s + Number(l.quantity || 0) * Number(l.unit_price || 0),
    0
  );

  const submitOrder = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    try {
      await api("/api/sales/orders", {
        method: "POST",
        body: JSON.stringify({
          order_no: orderNo,
          customer_id: Number(customerId),
          items: orderLines
            .filter((l) => l.item_id)
            .map((l) => ({
              item_id: Number(l.item_id),
              quantity: Number(l.quantity),
              unit_price: Number(l.unit_price),
            })),
        }),
      });
      setOrderNo("");
      setCustomerId("");
      setOrderLines([{ ...emptyLine }]);
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
      <div className="flex justify-between items-center mb-4">
        <h1 className="text-2xl font-semibold">영업 / CRM</h1>
        <ExportMenu endpoint="/api/sales/orders/export" filename="orders" />
      </div>
      {error && <p className="text-red-600 text-sm mb-3">{error}</p>}

      <h2 className="text-lg font-medium mb-2">고객 추가</h2>
      <form
        onSubmit={addCustomer}
        className="bg-white p-4 rounded-lg shadow-sm border border-slate-200 grid grid-cols-1 md:grid-cols-4 gap-3 mb-6"
      >
        <input
          required
          placeholder="이름"
          value={custForm.name}
          onChange={(e) => setCustForm({ ...custForm, name: e.target.value })}
          className="border rounded px-2 py-1"
        />
        <input
          type="email"
          placeholder="이메일"
          value={custForm.email}
          onChange={(e) => setCustForm({ ...custForm, email: e.target.value })}
          className="border rounded px-2 py-1"
        />
        <input
          placeholder="회사 / 상호"
          value={custForm.company}
          onChange={(e) => setCustForm({ ...custForm, company: e.target.value })}
          className="border rounded px-2 py-1"
        />
        <button className="bg-slate-900 text-white px-3 rounded">추가</button>
        <button
          type="button"
          onClick={() => setShowCustExtra(!showCustExtra)}
          className="col-span-1 md:col-span-4 text-xs text-emerald-700 hover:underline text-left"
        >
          {showCustExtra ? "▼" : "▶"} 세금계산서/거래명세표용 추가 정보
        </button>
        {showCustExtra && (
          <>
            <input
              placeholder="사업자등록번호 (123-45-67890)"
              value={custForm.business_no}
              onChange={(e) =>
                setCustForm({ ...custForm, business_no: e.target.value })
              }
              className="border rounded px-2 py-1"
            />
            <input
              placeholder="대표자"
              value={custForm.representative}
              onChange={(e) =>
                setCustForm({ ...custForm, representative: e.target.value })
              }
              className="border rounded px-2 py-1"
            />
            <input
              placeholder="사업장 주소"
              value={custForm.address}
              onChange={(e) =>
                setCustForm({ ...custForm, address: e.target.value })
              }
              className="border rounded px-2 py-1 md:col-span-2"
            />
            <input
              placeholder="전화"
              value={custForm.phone}
              onChange={(e) => setCustForm({ ...custForm, phone: e.target.value })}
              className="border rounded px-2 py-1"
            />
          </>
        )}
      </form>

      <h2 className="text-lg font-medium mb-2">주문 생성</h2>
      <form
        onSubmit={submitOrder}
        className="bg-white p-4 rounded-lg shadow-sm border border-slate-200 mb-6 space-y-3"
      >
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          <input
            required
            placeholder="주문번호 (예: SO-2026-001)"
            value={orderNo}
            onChange={(e) => setOrderNo(e.target.value)}
            className="border rounded px-2 py-1"
          />
          <select
            required
            value={customerId}
            onChange={(e) => setCustomerId(e.target.value)}
            className="border rounded px-2 py-1"
          >
            <option value="">고객 선택</option>
            {customers.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name}
                {c.company ? ` (${c.company})` : ""}
              </option>
            ))}
          </select>
        </div>

        <table className="w-full text-sm">
          <thead className="bg-slate-100">
            <tr>
              <th className="text-left px-2 py-1">품목</th>
              <th className="text-right px-2 py-1">수량</th>
              <th className="text-right px-2 py-1">단가</th>
              <th className="text-right px-2 py-1">소계</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {orderLines.map((line, idx) => (
              <tr key={idx}>
                <td className="px-2 py-1">
                  <select
                    value={line.item_id}
                    onChange={(e) => updateLine(idx, { item_id: e.target.value })}
                    className="border rounded px-2 py-1 w-full"
                  >
                    <option value="">선택</option>
                    {items.map((i) => (
                      <option key={i.id} value={i.id}>
                        {i.sku} - {i.name} (재고: {i.stock_qty})
                      </option>
                    ))}
                  </select>
                </td>
                <td className="px-2 py-1">
                  <input
                    type="number"
                    value={line.quantity}
                    onChange={(e) => updateLine(idx, { quantity: e.target.value })}
                    className="border rounded px-2 py-1 w-full text-right"
                  />
                </td>
                <td className="px-2 py-1">
                  <input
                    type="number"
                    value={line.unit_price}
                    onChange={(e) => updateLine(idx, { unit_price: e.target.value })}
                    className="border rounded px-2 py-1 w-full text-right"
                  />
                </td>
                <td className="px-2 py-1 text-right">
                  {(Number(line.quantity || 0) * Number(line.unit_price || 0)).toLocaleString()}
                </td>
                <td className="px-2 py-1">
                  {orderLines.length > 1 && (
                    <button
                      type="button"
                      onClick={() => setOrderLines(orderLines.filter((_, i) => i !== idx))}
                      className="text-red-600 text-xs"
                    >
                      삭제
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
          <tfoot>
            <tr className="font-medium border-t">
              <td colSpan={3} className="px-2 py-1 text-right">
                총액
              </td>
              <td className="px-2 py-1 text-right">{orderTotal.toLocaleString()}</td>
              <td></td>
            </tr>
          </tfoot>
        </table>

        <div className="flex gap-2">
          <button
            type="button"
            onClick={() => setOrderLines([...orderLines, { ...emptyLine }])}
            className="px-3 py-1 border rounded text-sm"
          >
            + 라인 추가
          </button>
          <button type="submit" className="px-4 py-1 bg-slate-900 text-white rounded">
            주문 생성
          </button>
        </div>
      </form>

      <h2 className="text-lg font-medium mb-2">고객 ({customers.length})</h2>
      <div className="mb-6">
        <DataTable<Customer>
          columns={[
            { key: "name", header: "이름" },
            { key: "email", header: "이메일" },
            { key: "company", header: "회사" },
            {
              key: "_edit",
              header: "관리",
              sortable: false,
              render: (r) => (
                <EditDeleteActions
                  row={r}
                  fields={[
                    { key: "name", label: "이름" },
                    { key: "email", label: "이메일", type: "email" },
                    { key: "phone", label: "전화" },
                    { key: "company", label: "회사" },
                  ]}
                  patchPath={(x) => `/api/sales/customers/${x.id}`}
                  deletePath={(x) => `/api/sales/customers/${x.id}`}
                  onChange={load}
                  confirmText="고객을 삭제하시겠습니까? (주문이 있으면 거부됨)"
                />
              ),
            },
          ]}
          rows={customers}
        />
        <Pager page={custPage} pages={custMeta.pages} total={custMeta.total} onChange={setCustPage} />
      </div>

      <h2 className="text-lg font-medium mb-2">주문 ({orderMeta.total})</h2>
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
          {
            key: "total",
            header: "금액",
            render: (r) => Number(r.total).toLocaleString(),
          },
          {
            key: "action",
            header: "",
            sortable: false,
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
          {
            key: "_edit",
            header: "관리",
            sortable: false,
            render: (r) =>
              r.status === "draft" ? (
                <EditDeleteActions
                  row={r}
                  fields={[
                    { key: "customer_id", label: "고객 ID", type: "number" },
                    { key: "order_date", label: "주문일자" },
                  ]}
                  patchPath={(x) => `/api/sales/orders/${x.id}`}
                  deletePath={(x) => `/api/sales/orders/${x.id}`}
                  onChange={load}
                  confirmText="이 주문을 삭제하시겠습니까? (draft 상태만 가능)"
                />
              ) : (
                <span className="text-xs text-slate-400">{r.status}</span>
              ),
          },
        ]}
        rows={orders}
        empty="주문이 없습니다"
      />
      <Pager
        page={orderPage}
        pages={orderMeta.pages}
        total={orderMeta.total}
        onChange={setOrderPage}
      />
    </AppShell>
  );
}
