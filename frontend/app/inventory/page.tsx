"use client";
import { useEffect, useState } from "react";
import AppShell from "@/components/AppShell";
import DataTable from "@/components/DataTable";
import EditDeleteActions from "@/components/EditDeleteActions";
import ExportMenu from "@/components/ExportMenu";
import Pager from "@/components/Pager";
import { Page, api, downloadFile, uploadFile } from "@/lib/api";
import { useCurrency } from "@/lib/currency";

type Item = {
  id: number;
  sku: string;
  name: string;
  unit: string;
  unit_price: string;
  stock_qty: string;
};

type Lot = {
  id: number;
  item_id: number;
  lot_number: string;
  quantity: string;
  expiry_date: string | null;
  supplier: string | null;
  serial_number: string | null;
};

export default function InventoryPage() {
  const { format } = useCurrency();
  const [items, setItems] = useState<Item[]>([]);
  const [form, setForm] = useState({ sku: "", name: "", unit: "EA", unit_price: "0" });
  const [error, setError] = useState("");
  const [lotsItem, setLotsItem] = useState<Item | null>(null);
  const [lots, setLots] = useState<Lot[]>([]);
  const [lotForm, setLotForm] = useState({
    lot_number: "",
    quantity: "0",
    expiry_date: "",
    supplier: "",
    serial_number: "",
  });

  const [page, setPage] = useState(1);
  const [meta, setMeta] = useState({ total: 0, pages: 1 });

  const load = async () => {
    const res = await api<Page<Item>>(`/api/inventory/items?page=${page}&size=20`);
    setItems(res.items);
    setMeta({ total: res.total, pages: res.pages });
  };

  useEffect(() => {
    load().catch((e) => setError(String(e)));
  }, [page]);

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

  const openLots = async (item: Item) => {
    setLotsItem(item);
    setError("");
    try {
      setLots(await api<Lot[]>(`/api/inventory/items/${item.id}/lots`));
    } catch (e) {
      setError(String(e));
    }
  };

  const submitLot = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!lotsItem) return;
    try {
      await api(`/api/inventory/items/${lotsItem.id}/lots`, {
        method: "POST",
        body: JSON.stringify({
          lot_number: lotForm.lot_number,
          quantity: Number(lotForm.quantity),
          expiry_date: lotForm.expiry_date || null,
          supplier: lotForm.supplier || null,
          serial_number: lotForm.serial_number || null,
        }),
      });
      setLotForm({ lot_number: "", quantity: "0", expiry_date: "", supplier: "", serial_number: "" });
      await openLots(lotsItem);
    } catch (e) {
      setError(String(e));
    }
  };

  return (
    <AppShell>
      <div className="flex justify-between items-center mb-4">
        <h1 className="text-2xl font-semibold">재고 / 물류</h1>
        <div className="flex gap-2 items-center">
          <ImportMenu onComplete={load} onError={setError} />
          <ExportMenu endpoint="/api/inventory/items/export" filename="items" />
        </div>
      </div>

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
          {
            key: "unit_price",
            header: "단가",
            render: (r) => format(Number(r.unit_price)),
          },
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
                <button
                  onClick={() => openLots(r)}
                  className="px-2 py-1 bg-slate-700 text-white rounded text-xs"
                >
                  LOT
                </button>
              </div>
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
                  { key: "name", label: "품목명" },
                  { key: "unit", label: "단위" },
                  { key: "unit_price", label: "단가", type: "number" },
                ]}
                patchPath={(x) => `/api/inventory/items/${x.id}`}
                deletePath={(x) => `/api/inventory/items/${x.id}`}
                onChange={load}
                confirmText="이 품목을 삭제하시겠습니까? (재고가 0이고 이력이 없어야 함)"
              />
            ),
          },
        ]}
        rows={items}
      />
      <Pager page={page} pages={meta.pages} total={meta.total} onChange={setPage} />

      {lotsItem && (
        <div className="fixed inset-0 bg-black/30 flex items-center justify-center z-30">
          <div className="bg-white rounded-lg p-6 w-[36rem] space-y-3 max-h-[80vh] overflow-y-auto">
            <div className="flex justify-between items-center">
              <h2 className="text-lg font-medium">
                {lotsItem.sku} - {lotsItem.name} LOT
              </h2>
              <button
                onClick={() => setLotsItem(null)}
                className="text-slate-500 hover:text-slate-900"
              >
                ✕
              </button>
            </div>

            <form onSubmit={submitLot} className="grid grid-cols-1 md:grid-cols-3 gap-2">
              <input
                required
                placeholder="LOT 번호"
                value={lotForm.lot_number}
                onChange={(e) => setLotForm({ ...lotForm, lot_number: e.target.value })}
                className="border rounded px-2 py-1 text-sm"
              />
              <input
                type="number"
                placeholder="수량"
                value={lotForm.quantity}
                onChange={(e) => setLotForm({ ...lotForm, quantity: e.target.value })}
                className="border rounded px-2 py-1 text-sm"
              />
              <input
                type="date"
                placeholder="유효기간"
                value={lotForm.expiry_date}
                onChange={(e) => setLotForm({ ...lotForm, expiry_date: e.target.value })}
                className="border rounded px-2 py-1 text-sm"
              />
              <input
                placeholder="공급사"
                value={lotForm.supplier}
                onChange={(e) => setLotForm({ ...lotForm, supplier: e.target.value })}
                className="border rounded px-2 py-1 text-sm"
              />
              <input
                placeholder="시리얼 번호"
                value={lotForm.serial_number}
                onChange={(e) => setLotForm({ ...lotForm, serial_number: e.target.value })}
                className="border rounded px-2 py-1 text-sm"
              />
              <button className="bg-slate-900 text-white text-sm rounded">LOT 추가</button>
            </form>

            <table className="w-full text-sm">
              <thead className="bg-slate-100">
                <tr>
                  <th className="text-left px-2 py-1">LOT</th>
                  <th className="text-right px-2 py-1">수량</th>
                  <th className="text-left px-2 py-1">유효기간</th>
                  <th className="text-left px-2 py-1">공급사</th>
                  <th className="text-left px-2 py-1">시리얼</th>
                </tr>
              </thead>
              <tbody>
                {lots.length === 0 && (
                  <tr>
                    <td colSpan={5} className="text-center py-3 text-slate-500">
                      LOT 없음
                    </td>
                  </tr>
                )}
                {lots.map((l) => (
                  <tr key={l.id} className="border-t">
                    <td className="px-2 py-1">{l.lot_number}</td>
                    <td className="px-2 py-1 text-right">{l.quantity}</td>
                    <td className="px-2 py-1">{l.expiry_date ?? "-"}</td>
                    <td className="px-2 py-1">{l.supplier ?? "-"}</td>
                    <td className="px-2 py-1">{l.serial_number ?? "-"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </AppShell>
  );
}

function ImportMenu({
  onComplete,
  onError,
}: {
  onComplete: () => void;
  onError: (s: string) => void;
}) {
  const [busy, setBusy] = useState(false);

  const pick = () => {
    const input = document.createElement("input");
    input.type = "file";
    input.accept = ".xlsx,.csv,.xls";
    input.onchange = async () => {
      const f = input.files?.[0];
      if (!f) return;
      setBusy(true);
      try {
        const res = await uploadFile<{
          created: number;
          updated: number;
          skipped: number;
          errors: { row: number; reason: string }[];
          total_rows: number;
        }>("/api/inventory/items/import?upsert=true", f);
        const errMsg =
          res.errors.length > 0
            ? `\n실패 ${res.errors.length}건:\n` +
              res.errors
                .slice(0, 10)
                .map((e) => `  ${e.row}행: ${e.reason}`)
                .join("\n")
            : "";
        alert(
          `완료\n신규 ${res.created} · 갱신 ${res.updated} · 건너뜀 ${res.skipped} (총 ${res.total_rows}행)${errMsg}`
        );
        onComplete();
      } catch (e) {
        onError(String(e));
      } finally {
        setBusy(false);
      }
    };
    input.click();
  };

  const downloadTemplate = () => {
    downloadFile(
      "/api/inventory/items/import-template?format=xlsx",
      "품목_업로드양식.xlsx"
    ).catch((e) => onError(String(e)));
  };

  return (
    <div className="inline-flex rounded border border-emerald-300 overflow-hidden text-sm bg-emerald-50">
      <button
        onClick={pick}
        disabled={busy}
        className="px-3 py-1 hover:bg-emerald-100 disabled:opacity-50"
        title="Excel(.xlsx) 또는 CSV 업로드"
      >
        {busy ? "업로드 중..." : "↑ 업로드"}
      </button>
      <button
        onClick={downloadTemplate}
        className="px-3 py-1 hover:bg-emerald-100 border-l border-emerald-300"
        title="업로드 양식 다운로드"
      >
        양식
      </button>
    </div>
  );
}
