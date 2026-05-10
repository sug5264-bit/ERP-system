"use client";
import { useEffect, useState } from "react";
import AppShell from "@/components/AppShell";
import DataTable from "@/components/DataTable";
import Pager from "@/components/Pager";
import { Page, api } from "@/lib/api";
import { hasRole, useMe } from "@/lib/auth";

type PickList = {
  id: number;
  pick_no: string;
  sales_order_id: number;
  status: "pending" | "picking" | "picked" | "cancelled";
  picker_id: number | null;
  started_at: string | null;
  completed_at: string | null;
  items: {
    id: number;
    item_id: number;
    requested_qty: string;
    picked_qty: string;
    lot_id: number | null;
  }[];
};

type Shipment = {
  id: number;
  shipment_no: string;
  pick_list_id: number;
  sales_order_id: number;
  status: "pending" | "packed" | "shipped" | "delivered" | "returned";
  carrier: string | null;
  tracking_no: string | null;
  packed_at: string | null;
  shipped_at: string | null;
  delivered_at: string | null;
};

type Tab = "pick" | "ship";

export default function WMSPage() {
  const me = useMe();
  const isManager = hasRole(me, "manager");
  const [tab, setTab] = useState<Tab>("pick");
  const [error, setError] = useState("");
  return (
    <AppShell>
      <div className="flex justify-between items-center mb-4">
        <h1 className="text-2xl font-semibold">WMS / 출하 관리</h1>
        <div className="flex gap-1">
          {(["pick", "ship"] as Tab[]).map((t) => (
            <button
              key={t}
              onClick={() => setTab(t)}
              className={`px-3 py-1 text-sm rounded ${
                tab === t
                  ? "bg-slate-900 text-white"
                  : "bg-slate-100 hover:bg-slate-200"
              }`}
            >
              {t === "pick" ? "Pick List" : "Shipment"}
            </button>
          ))}
        </div>
      </div>
      {error && <p className="text-red-600 text-sm mb-3">{error}</p>}
      {tab === "pick" && <PickTab onError={setError} />}
      {tab === "ship" && <ShipTab onError={setError} isManager={isManager} />}
    </AppShell>
  );
}

function PickTab({ onError }: { onError: (s: string) => void }) {
  const [rows, setRows] = useState<PickList[]>([]);
  const [page, setPage] = useState(1);
  const [meta, setMeta] = useState({ total: 0, pages: 1 });
  const [orderId, setOrderId] = useState("");

  const load = async () => {
    try {
      const r = await api<Page<PickList>>(`/api/wms/pick-lists?page=${page}&size=20`);
      setRows(r.items);
      setMeta({ total: r.total, pages: r.pages });
    } catch (e) {
      onError(String(e));
    }
  };
  useEffect(() => {
    load();
  }, [page]);

  const generate = async () => {
    if (!orderId) return;
    onError("");
    try {
      await api(`/api/wms/pick-lists/from-order/${orderId}`, { method: "POST" });
      setOrderId("");
      await load();
    } catch (e) {
      onError(String(e));
    }
  };

  const start = async (id: number) => {
    try {
      await api(`/api/wms/pick-lists/${id}/start`, { method: "POST" });
      await load();
    } catch (e) {
      onError(String(e));
    }
  };

  const complete = async (pl: PickList) => {
    const items = pl.items.map((it) => {
      const v = prompt(
        `품목 ${it.item_id} 실제 picked 수량 (요청 ${it.requested_qty})`,
        it.requested_qty
      );
      return v ? { item_id: it.item_id, picked_qty: Number(v) } : null;
    });
    if (items.some((x) => x === null)) return;
    try {
      await api(`/api/wms/pick-lists/${pl.id}/complete`, {
        method: "POST",
        body: JSON.stringify({ items }),
      });
      await load();
    } catch (e) {
      onError(String(e));
    }
  };

  return (
    <>
      <div className="bg-white p-4 rounded-lg border border-slate-200 mb-4 flex gap-2">
        <input
          type="number"
          placeholder="확정 주문 ID"
          value={orderId}
          onChange={(e) => setOrderId(e.target.value)}
          className="border rounded px-2 py-1"
        />
        <button
          onClick={generate}
          className="bg-emerald-700 text-white px-3 py-1 rounded text-sm"
        >
          + Pick List 생성
        </button>
      </div>

      <DataTable<PickList>
        columns={[
          { key: "pick_no", header: "PL 번호" },
          { key: "sales_order_id", header: "주문" },
          { key: "status", header: "상태" },
          {
            key: "items",
            header: "라인",
            render: (r) => `${r.items.length}건`,
          },
          { key: "started_at", header: "시작" },
          { key: "completed_at", header: "완료" },
          {
            key: "_act",
            header: "관리",
            sortable: false,
            render: (r) => (
              <div className="flex gap-2">
                {r.status === "pending" && (
                  <button
                    onClick={() => start(r.id)}
                    className="text-blue-700 text-xs hover:underline"
                  >
                    시작
                  </button>
                )}
                {r.status === "picking" && (
                  <button
                    onClick={() => complete(r)}
                    className="text-emerald-700 text-xs hover:underline"
                  >
                    완료
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

function ShipTab({
  onError,
  isManager,
}: {
  onError: (s: string) => void;
  isManager: boolean;
}) {
  const [rows, setRows] = useState<Shipment[]>([]);
  const [page, setPage] = useState(1);
  const [meta, setMeta] = useState({ total: 0, pages: 1 });
  const [form, setForm] = useState({
    shipment_no: "",
    pick_list_id: "",
    carrier: "",
    tracking_no: "",
    weight_kg: "",
    address_to: "",
  });

  const load = async () => {
    try {
      const r = await api<Page<Shipment>>(`/api/wms/shipments?page=${page}&size=20`);
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
      await api("/api/wms/shipments", {
        method: "POST",
        body: JSON.stringify({
          shipment_no: form.shipment_no,
          pick_list_id: Number(form.pick_list_id),
          carrier: form.carrier || null,
          tracking_no: form.tracking_no || null,
          weight_kg: form.weight_kg ? Number(form.weight_kg) : null,
          address_to: form.address_to || null,
        }),
      });
      setForm({
        shipment_no: "",
        pick_list_id: "",
        carrier: "",
        tracking_no: "",
        weight_kg: "",
        address_to: "",
      });
      await load();
    } catch (e) {
      onError(String(e));
    }
  };

  const transition = async (id: number, action: "ship" | "deliver" | "return") => {
    if (action === "return" && !confirm("반품 처리 시 재고로 복구됩니다. 진행할까요?"))
      return;
    try {
      await api(`/api/wms/shipments/${id}/${action}`, { method: "POST" });
      await load();
    } catch (e) {
      onError(String(e));
    }
  };

  return (
    <>
      <form
        onSubmit={submit}
        className="bg-white p-4 rounded-lg border border-slate-200 grid grid-cols-1 md:grid-cols-3 gap-2 mb-4"
      >
        <input
          required
          placeholder="송장번호"
          value={form.shipment_no}
          onChange={(e) => setForm({ ...form, shipment_no: e.target.value })}
          className="border rounded px-2 py-1"
        />
        <input
          required
          type="number"
          placeholder="Pick List ID (picked 상태)"
          value={form.pick_list_id}
          onChange={(e) => setForm({ ...form, pick_list_id: e.target.value })}
          className="border rounded px-2 py-1"
        />
        <input
          placeholder="택배사"
          value={form.carrier}
          onChange={(e) => setForm({ ...form, carrier: e.target.value })}
          className="border rounded px-2 py-1"
        />
        <input
          placeholder="운송장번호"
          value={form.tracking_no}
          onChange={(e) => setForm({ ...form, tracking_no: e.target.value })}
          className="border rounded px-2 py-1"
        />
        <input
          type="number"
          step="0.1"
          placeholder="무게 (kg)"
          value={form.weight_kg}
          onChange={(e) => setForm({ ...form, weight_kg: e.target.value })}
          className="border rounded px-2 py-1"
        />
        <input
          placeholder="배송주소"
          value={form.address_to}
          onChange={(e) => setForm({ ...form, address_to: e.target.value })}
          className="border rounded px-2 py-1"
        />
        <button className="bg-slate-900 text-white rounded col-span-1 md:col-span-3">
          + 패킹/출하 등록
        </button>
      </form>

      <DataTable<Shipment>
        columns={[
          { key: "shipment_no", header: "송장" },
          { key: "sales_order_id", header: "주문" },
          { key: "status", header: "상태" },
          { key: "carrier", header: "택배사" },
          { key: "tracking_no", header: "추적번호" },
          { key: "shipped_at", header: "출하시각" },
          { key: "delivered_at", header: "배송시각" },
          {
            key: "_act",
            header: "관리",
            sortable: false,
            render: (r) =>
              isManager ? (
                <div className="flex gap-2">
                  {r.status === "packed" && (
                    <button
                      onClick={() => transition(r.id, "ship")}
                      className="text-blue-700 text-xs hover:underline"
                    >
                      출하
                    </button>
                  )}
                  {r.status === "shipped" && (
                    <button
                      onClick={() => transition(r.id, "deliver")}
                      className="text-emerald-700 text-xs hover:underline"
                    >
                      배송완료
                    </button>
                  )}
                  {(r.status === "shipped" || r.status === "delivered") && (
                    <button
                      onClick={() => transition(r.id, "return")}
                      className="text-red-600 text-xs hover:underline"
                    >
                      반품
                    </button>
                  )}
                </div>
              ) : null,
          },
        ]}
        rows={rows}
      />
      <Pager page={page} pages={meta.pages} total={meta.total} onChange={setPage} />
    </>
  );
}
