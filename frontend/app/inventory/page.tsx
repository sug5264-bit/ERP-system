"use client";
import { useEffect, useState } from "react";
import AppShell from "@/components/AppShell";
import DataTable from "@/components/DataTable";
import { api } from "@/lib/api";

type Item = {
  id: number;
  sku: string;
  name: string;
  unit: string;
  unit_price: string;
  stock_qty: string;
};

export default function InventoryPage() {
  const [items, setItems] = useState<Item[]>([]);
  const [form, setForm] = useState({ sku: "", name: "", unit: "EA", unit_price: "0" });
  const [error, setError] = useState("");

  const load = async () => setItems(await api<Item[]>("/api/inventory/items"));

  useEffect(() => {
    load().catch((e) => setError(String(e)));
  }, []);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    try {
      await api("/api/inventory/items", {
        method: "POST",
        body: JSON.stringify({ ...form, unit_price: Number(form.unit_price) }),
      });
      setForm({ sku: "", name: "", unit: "EA", unit_price: "0" });
      await load();
    } catch (e) {
      setError(String(e));
    }
  };

  const move = async (item_id: number, type: "inbound" | "outbound") => {
    const qty = prompt(`수량 (${type})`);
    if (!qty) return;
    try {
      await api("/api/inventory/movements", {
        method: "POST",
        body: JSON.stringify({ item_id, type, quantity: Number(qty) }),
      });
      await load();
    } catch (e) {
      setError(String(e));
    }
  };

  return (
    <AppShell>
      <h1 className="text-2xl font-semibold mb-4">재고 / 물류</h1>

      <form
        onSubmit={submit}
        className="bg-white p-4 rounded-lg shadow-sm border border-slate-200 grid grid-cols-1 md:grid-cols-5 gap-3 mb-6"
      >
        <input
          required
          placeholder="SKU"
          value={form.sku}
          onChange={(e) => setForm({ ...form, sku: e.target.value })}
          className="border rounded px-2 py-1"
        />
        <input
          required
          placeholder="품목명"
          value={form.name}
          onChange={(e) => setForm({ ...form, name: e.target.value })}
          className="border rounded px-2 py-1"
        />
        <input
          placeholder="단위"
          value={form.unit}
          onChange={(e) => setForm({ ...form, unit: e.target.value })}
          className="border rounded px-2 py-1"
        />
        <input
          type="number"
          placeholder="단가"
          value={form.unit_price}
          onChange={(e) => setForm({ ...form, unit_price: e.target.value })}
          className="border rounded px-2 py-1"
        />
        <button className="bg-slate-900 text-white px-3 rounded">품목 추가</button>
      </form>

      {error && <p className="text-red-600 text-sm mb-3">{error}</p>}

      <DataTable<Item>
        columns={[
          { key: "sku", header: "SKU" },
          { key: "name", header: "품목명" },
          { key: "unit", header: "단위" },
          { key: "unit_price", header: "단가" },
          { key: "stock_qty", header: "재고" },
          {
            key: "actions",
            header: "이동",
            render: (r) => (
              <div className="flex gap-2">
                <button
                  onClick={() => move(r.id, "inbound")}
                  className="px-2 py-1 bg-green-600 text-white rounded text-xs"
                >
                  입고
                </button>
                <button
                  onClick={() => move(r.id, "outbound")}
                  className="px-2 py-1 bg-red-600 text-white rounded text-xs"
                >
                  출고
                </button>
              </div>
            ),
          },
        ]}
        rows={items}
      />
    </AppShell>
  );
}
