"use client";
import { useEffect, useState } from "react";
import AppShell from "@/components/AppShell";
import DataTable from "@/components/DataTable";
import EditDeleteActions from "@/components/EditDeleteActions";
import Pager from "@/components/Pager";
import { Page, api, downloadFile } from "@/lib/api";

type Supplier = {
  id: number;
  code: string;
  name: string;
  contact_email: string | null;
  is_active: boolean;
};

type POItem = { item_id: number; quantity: string; unit_price: string; received_qty: string };
type PO = {
  id: number;
  po_no: string;
  supplier_id: number;
  order_date: string;
  status: "draft" | "sent" | "acknowledged" | "shipped" | "received" | "cancelled";
  total: string;
  items: POItem[];
  supplier: Supplier | null;
};

type Item = { id: number; sku: string; name: string; unit_price: string };

const STATUS_COLOR: Record<string, string> = {
  draft: "bg-slate-100 text-slate-700",
  sent: "bg-blue-100 text-blue-700",
  acknowledged: "bg-indigo-100 text-indigo-700",
  shipped: "bg-amber-100 text-amber-700",
  received: "bg-brand-100 text-brand-800",
  cancelled: "bg-red-100 text-red-700",
};

export default function SuppliersPage() {
  const [tab, setTab] = useState<"suppliers" | "orders">("suppliers");
  const [suppliers, setSuppliers] = useState<Supplier[]>([]);
  const [orders, setOrders] = useState<PO[]>([]);
  const [items, setItems] = useState<Item[]>([]);
  const [error, setError] = useState("");

  const [supForm, setSupForm] = useState({
    code: "",
    name: "",
    contact_email: "",
    business_no: "",
    representative: "",
    address: "",
    phone: "",
  });
  const [showSupExtra, setShowSupExtra] = useState(false);
  const [portalForm, setPortalForm] = useState({
    code: "",
    name: "",
    contact_email: "",
    portal_full_name: "",
    portal_password: "",
  });
  const [portalCreated, setPortalCreated] = useState<string | null>(null);
  const [poForm, setPoForm] = useState({
    po_no: "",
    supplier_id: "",
    items: [{ item_id: "", quantity: "1", unit_price: "0" }],
  });

  const [page, setPage] = useState(1);
  const [meta, setMeta] = useState({ total: 0, pages: 1 });

  const load = async () => {
    try {
      const [s, o, i] = await Promise.all([
        api<Page<Supplier>>(`/api/suppliers?page=${page}&size=20`),
        api<Page<PO>>(`/api/suppliers/orders?page=1&size=50`),
        api<Page<Item>>("/api/inventory/items?page=1&size=200"),
      ]);
      setSuppliers(s.items);
      setMeta({ total: s.total, pages: s.pages });
      setOrders(o.items);
      setItems(i.items);
    } catch (e) {
      setError(String(e));
    }
  };

  useEffect(() => {
    load();
  }, [page]);

  const addSupplier = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    try {
      await api("/api/suppliers", {
        method: "POST",
        body: JSON.stringify(supForm),
      });
      setSupForm({
        code: "",
        name: "",
        contact_email: "",
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

  const addSupplierWithPortal = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setPortalCreated(null);
    try {
      const res = await api<{ id: number; portal_user_id: number | null }>(
        "/api/suppliers/with-portal-user",
        { method: "POST", body: JSON.stringify(portalForm) }
      );
      setPortalCreated(
        `공급사 + 포털 계정 생성 완료 (이메일: ${portalForm.contact_email})`
      );
      setPortalForm({
        code: "",
        name: "",
        contact_email: "",
        portal_full_name: "",
        portal_password: "",
      });
      await load();
    } catch (e) {
      setError(String(e));
    }
  };

  const addPO = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    try {
      await api("/api/suppliers/orders", {
        method: "POST",
        body: JSON.stringify({
          po_no: poForm.po_no,
          supplier_id: Number(poForm.supplier_id),
          items: poForm.items
            .filter((l) => l.item_id)
            .map((l) => ({
              item_id: Number(l.item_id),
              quantity: Number(l.quantity),
              unit_price: Number(l.unit_price),
            })),
        }),
      });
      setPoForm({
        po_no: "",
        supplier_id: "",
        items: [{ item_id: "", quantity: "1", unit_price: "0" }],
      });
      await load();
    } catch (e) {
      setError(String(e));
    }
  };

  const action = async (id: number, kind: "send" | "acknowledge" | "ship" | "cancel") => {
    try {
      await api(`/api/suppliers/orders/${id}/${kind}`, { method: "POST" });
      await load();
    } catch (e) {
      setError(String(e));
    }
  };

  const receive = async (po: PO) => {
    if (!confirm(`${po.po_no} 입고 처리합니다 (재고 자동 증가).`)) return;
    try {
      await api(`/api/suppliers/orders/${po.id}/receive`, {
        method: "POST",
        body: JSON.stringify({
          lines: po.items.map((l) => ({
            item_id: l.item_id,
            quantity: Number(l.quantity) - Number(l.received_qty),
          })),
        }),
      });
      await load();
    } catch (e) {
      setError(String(e));
    }
  };

  return (
    <AppShell>
      <h1 className="text-2xl font-semibold mb-4">공급사 / 발주</h1>

      <div className="flex gap-2 mb-4 border-b border-slate-200">
        {(["suppliers", "orders"] as const).map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`px-4 py-2 text-sm ${
              tab === t
                ? "border-b-2 border-brand-700 dark:border-brand-300 font-medium"
                : "text-slate-500"
            }`}
          >
            {t === "suppliers" ? "공급사" : "발주서"}
          </button>
        ))}
      </div>

      {error && <p className="text-red-600 text-sm mb-3">{error}</p>}

      {tab === "suppliers" && (
        <>
          <form
            onSubmit={addSupplier}
            className="bg-white p-4 rounded-lg shadow-sm border border-slate-200 grid grid-cols-1 md:grid-cols-4 gap-3 mb-6"
          >
            <input
              required
              placeholder="코드 (SUP-001)"
              value={supForm.code}
              onChange={(e) => setSupForm({ ...supForm, code: e.target.value })}
              className="border rounded px-2 py-1"
            />
            <input
              required
              placeholder="공급사명"
              value={supForm.name}
              onChange={(e) => setSupForm({ ...supForm, name: e.target.value })}
              className="border rounded px-2 py-1"
            />
            <input
              type="email"
              placeholder="이메일"
              value={supForm.contact_email}
              onChange={(e) =>
                setSupForm({ ...supForm, contact_email: e.target.value })
              }
              className="border rounded px-2 py-1"
            />
            <button className="bg-slate-900 text-white px-3 rounded">공급사 추가</button>
            <button
              type="button"
              onClick={() => setShowSupExtra(!showSupExtra)}
              className="col-span-1 md:col-span-4 text-xs text-emerald-700 hover:underline text-left"
            >
              {showSupExtra ? "▼" : "▶"} 발주서/세금계산서용 추가 정보
            </button>
            {showSupExtra && (
              <>
                <input
                  placeholder="사업자등록번호 (123-45-67890)"
                  value={supForm.business_no}
                  onChange={(e) =>
                    setSupForm({ ...supForm, business_no: e.target.value })
                  }
                  className="border rounded px-2 py-1"
                />
                <input
                  placeholder="대표자"
                  value={supForm.representative}
                  onChange={(e) =>
                    setSupForm({ ...supForm, representative: e.target.value })
                  }
                  className="border rounded px-2 py-1"
                />
                <input
                  placeholder="전화"
                  value={supForm.phone}
                  onChange={(e) =>
                    setSupForm({ ...supForm, phone: e.target.value })
                  }
                  className="border rounded px-2 py-1"
                />
                <input
                  placeholder="사업장 주소"
                  value={supForm.address}
                  onChange={(e) =>
                    setSupForm({ ...supForm, address: e.target.value })
                  }
                  className="border rounded px-2 py-1 md:col-span-4"
                />
              </>
            )}
          </form>

          <form
            onSubmit={addSupplierWithPortal}
            className="bg-white p-4 rounded-lg shadow-sm border border-slate-200 mb-6 space-y-3"
          >
            <h2 className="text-lg font-medium">공급사 + 포털 계정 동시 생성</h2>
            <p className="text-xs text-slate-500">
              공급사 사용자는 포털에서 자기 PO만 조회·승인·출하할 수 있고 다른 모듈은 차단됩니다.
            </p>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
              <input
                required
                placeholder="공급사 코드 (SUP-002)"
                value={portalForm.code}
                onChange={(e) =>
                  setPortalForm({ ...portalForm, code: e.target.value })
                }
                className="border rounded px-2 py-1"
              />
              <input
                required
                placeholder="공급사명"
                value={portalForm.name}
                onChange={(e) =>
                  setPortalForm({ ...portalForm, name: e.target.value })
                }
                className="border rounded px-2 py-1"
              />
              <input
                required
                type="email"
                placeholder="포털 로그인 이메일"
                value={portalForm.contact_email}
                onChange={(e) =>
                  setPortalForm({ ...portalForm, contact_email: e.target.value })
                }
                className="border rounded px-2 py-1"
              />
              <input
                required
                placeholder="포털 사용자 이름"
                value={portalForm.portal_full_name}
                onChange={(e) =>
                  setPortalForm({ ...portalForm, portal_full_name: e.target.value })
                }
                className="border rounded px-2 py-1"
              />
              <input
                required
                type="password"
                minLength={8}
                placeholder="초기 비밀번호 (8자 이상)"
                value={portalForm.portal_password}
                onChange={(e) =>
                  setPortalForm({ ...portalForm, portal_password: e.target.value })
                }
                className="border rounded px-2 py-1"
              />
              <button className="bg-brand-700 text-white px-3 rounded text-sm">
                생성 + 계정 발급
              </button>
            </div>
            {portalCreated && (
              <p className="text-brand-700 text-sm">{portalCreated}</p>
            )}
          </form>

          <DataTable<Supplier>
            columns={[
              { key: "code", header: "코드" },
              { key: "name", header: "공급사명" },
              { key: "contact_email", header: "이메일" },
              {
                key: "is_active",
                header: "상태",
                render: (s) =>
                  s.is_active ? (
                    <span className="text-brand-700 text-xs">활성</span>
                  ) : (
                    <span className="text-slate-400 text-xs">비활성</span>
                  ),
              },
              {
                key: "_edit",
                header: "관리",
                sortable: false,
                render: (r) => (
                  <EditDeleteActions
                    row={r}
                    fields={[
                      { key: "name", label: "공급사명" },
                      { key: "contact_email", label: "이메일", type: "email" },
                      { key: "phone", label: "전화" },
                      { key: "business_no", label: "사업자번호" },
                    ]}
                    patchPath={(x) => `/api/suppliers/${x.id}`}
                    deletePath={(x) => `/api/suppliers/${x.id}`}
                    onChange={load}
                    confirmText="공급사를 삭제하시겠습니까? (PO가 있으면 거부됨)"
                  />
                ),
              },
            ]}
            rows={suppliers}
          />
          <Pager
            page={page}
            pages={meta.pages}
            total={meta.total}
            onChange={setPage}
          />
        </>
      )}

      {tab === "orders" && (
        <>
          <form
            onSubmit={addPO}
            className="bg-white p-4 rounded-lg shadow-sm border border-slate-200 mb-6 space-y-3"
          >
            <h2 className="text-lg font-medium">새 발주서</h2>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              <input
                required
                placeholder="발주번호 (PO-2026-001)"
                value={poForm.po_no}
                onChange={(e) => setPoForm({ ...poForm, po_no: e.target.value })}
                className="border rounded px-2 py-1"
              />
              <select
                required
                value={poForm.supplier_id}
                onChange={(e) => setPoForm({ ...poForm, supplier_id: e.target.value })}
                className="border rounded px-2 py-1"
              >
                <option value="">공급사 선택</option>
                {suppliers.map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.code} - {s.name}
                  </option>
                ))}
              </select>
            </div>
            {poForm.items.map((line, idx) => (
              <div key={idx} className="grid grid-cols-12 gap-2">
                <select
                  value={line.item_id}
                  onChange={(e) => {
                    const next = [...poForm.items];
                    next[idx] = { ...next[idx], item_id: e.target.value };
                    const it = items.find((i) => String(i.id) === e.target.value);
                    if (it) next[idx].unit_price = it.unit_price;
                    setPoForm({ ...poForm, items: next });
                  }}
                  className="border rounded px-2 py-1 col-span-6"
                >
                  <option value="">품목</option>
                  {items.map((i) => (
                    <option key={i.id} value={i.id}>
                      {i.sku} - {i.name}
                    </option>
                  ))}
                </select>
                <input
                  type="number"
                  placeholder="수량"
                  value={line.quantity}
                  onChange={(e) => {
                    const next = [...poForm.items];
                    next[idx] = { ...next[idx], quantity: e.target.value };
                    setPoForm({ ...poForm, items: next });
                  }}
                  className="border rounded px-2 py-1 col-span-2"
                />
                <input
                  type="number"
                  placeholder="단가"
                  value={line.unit_price}
                  onChange={(e) => {
                    const next = [...poForm.items];
                    next[idx] = { ...next[idx], unit_price: e.target.value };
                    setPoForm({ ...poForm, items: next });
                  }}
                  className="border rounded px-2 py-1 col-span-3"
                />
                <button
                  type="button"
                  onClick={() =>
                    setPoForm({
                      ...poForm,
                      items: poForm.items.filter((_, i) => i !== idx),
                    })
                  }
                  className="text-red-600 text-xs"
                  disabled={poForm.items.length === 1}
                >
                  ✕
                </button>
              </div>
            ))}
            <div className="flex gap-2">
              <button
                type="button"
                onClick={() =>
                  setPoForm({
                    ...poForm,
                    items: [
                      ...poForm.items,
                      { item_id: "", quantity: "1", unit_price: "0" },
                    ],
                  })
                }
                className="px-3 py-1 border rounded text-sm"
              >
                + 라인
              </button>
              <button className="bg-slate-900 text-white px-4 rounded">
                발주 생성
              </button>
            </div>
          </form>

          <DataTable<PO>
            columns={[
              { key: "po_no", header: "발주번호" },
              { key: "order_date", header: "일자" },
              {
                key: "supplier",
                header: "공급사",
                render: (r) => r.supplier?.name ?? "-",
              },
              {
                key: "status",
                header: "상태",
                render: (r) => (
                  <span
                    className={`px-2 py-0.5 rounded text-xs uppercase ${STATUS_COLOR[r.status] || ""}`}
                  >
                    {r.status}
                  </span>
                ),
              },
              {
                key: "total",
                header: "총액",
                render: (r) => Number(r.total).toLocaleString(),
              },
              {
                key: "actions",
                header: "",
                render: (r) => (
                  <div className="flex gap-1 flex-wrap">
                    <button
                      onClick={() =>
                        downloadFile(
                          `/api/suppliers/orders/${r.id}/purchase-order.pdf`
                        ).catch((e) => setError(String(e)))
                      }
                      className="px-2 py-1 bg-emerald-700 text-white rounded text-xs"
                      title="발주서 PDF"
                    >
                      발주서
                    </button>
                    {r.status === "draft" && (
                      <button
                        onClick={() => action(r.id, "send")}
                        className="px-2 py-1 bg-blue-600 text-white rounded text-xs"
                      >
                        발송
                      </button>
                    )}
                    {r.status === "sent" && (
                      <button
                        onClick={() => action(r.id, "acknowledge")}
                        className="px-2 py-1 bg-indigo-600 text-white rounded text-xs"
                      >
                        승인 (공급사)
                      </button>
                    )}
                    {(r.status === "acknowledged" || r.status === "sent") && (
                      <button
                        onClick={() => action(r.id, "ship")}
                        className="px-2 py-1 bg-amber-600 text-white rounded text-xs"
                      >
                        출하
                      </button>
                    )}
                    {(r.status === "shipped" ||
                      r.status === "acknowledged" ||
                      r.status === "sent") && (
                      <button
                        onClick={() => receive(r)}
                        className="px-2 py-1 bg-brand-700 text-white rounded text-xs"
                      >
                        입고
                      </button>
                    )}
                    {(r.status === "draft" ||
                      r.status === "sent" ||
                      r.status === "acknowledged") && (
                      <button
                        onClick={() => action(r.id, "cancel")}
                        className="px-2 py-1 text-red-600 text-xs hover:underline"
                      >
                        취소
                      </button>
                    )}
                  </div>
                ),
              },
            ]}
            rows={orders}
          />
        </>
      )}
    </AppShell>
  );
}
