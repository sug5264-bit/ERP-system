"use client";
import { useEffect, useState } from "react";
import AppShell from "@/components/AppShell";
import DataTable from "@/components/DataTable";
import { api } from "@/lib/api";
import { hasRole, useMe } from "@/lib/auth";

type Suggestion = {
  item_id: number;
  sku: string;
  name: string;
  stock_qty: number;
  reorder_point: number;
  safety_stock: number;
  suggested_qty: number;
  preferred_supplier_id: number | null;
  abc_class: string | null;
};

export default function ReorderPage() {
  const me = useMe();
  const isManager = hasRole(me, "manager");
  const [rows, setRows] = useState<Suggestion[]>([]);
  const [error, setError] = useState("");
  const [classifyResult, setClassifyResult] = useState<any>(null);
  const [createdPOs, setCreatedPOs] = useState<any[]>([]);

  const load = async () => {
    try {
      setRows(await api<Suggestion[]>("/api/inventory/reorder-suggestions"));
    } catch (e) {
      setError(String(e));
    }
  };
  useEffect(() => {
    load();
  }, []);

  const classify = async () => {
    setError("");
    try {
      setClassifyResult(
        await api("/api/inventory/abc-classify?days=365", { method: "POST" })
      );
      await load();
    } catch (e) {
      setError(String(e));
    }
  };

  const generatePOs = async () => {
    if (!confirm("선호 공급사가 지정된 항목으로 자동 PO를 생성하시겠습니까?")) return;
    try {
      const res = await api<any>("/api/inventory/auto-purchase-orders", {
        method: "POST",
      });
      setCreatedPOs(res.created || []);
      await load();
    } catch (e) {
      setError(String(e));
    }
  };

  return (
    <AppShell>
      <div className="flex justify-between items-center mb-4">
        <h1 className="text-2xl font-semibold">재고 보충 / ABC</h1>
        {isManager && (
          <div className="flex gap-2">
            <button
              onClick={classify}
              className="bg-blue-700 text-white px-3 py-1 rounded text-sm"
            >
              ABC 재분류 (1년)
            </button>
            <button
              onClick={generatePOs}
              className="bg-emerald-700 text-white px-3 py-1 rounded text-sm"
            >
              자동 PO 생성
            </button>
          </div>
        )}
      </div>
      {error && <p className="text-red-600 text-sm mb-3">{error}</p>}

      {classifyResult && (
        <div className="bg-blue-50 border border-blue-200 rounded p-3 mb-4 text-sm">
          분류: A {classifyResult.A}건 / B {classifyResult.B}건 / C {classifyResult.C}건
          (총 {classifyResult.classified}건)
        </div>
      )}
      {createdPOs.length > 0 && (
        <div className="bg-emerald-50 border border-emerald-200 rounded p-3 mb-4 text-sm">
          생성된 PO:{" "}
          {createdPOs.map((p) => `${p.po_no} (라인 ${p.lines})`).join(", ")}
        </div>
      )}

      <DataTable<Suggestion>
        columns={[
          { key: "sku", header: "SKU" },
          { key: "name", header: "품목" },
          { key: "abc_class", header: "ABC" },
          {
            key: "stock_qty",
            header: "재고",
            render: (r) => (
              <span className="text-red-600">{r.stock_qty.toLocaleString()}</span>
            ),
          },
          {
            key: "reorder_point",
            header: "재발주점",
            render: (r) => r.reorder_point.toLocaleString(),
          },
          {
            key: "suggested_qty",
            header: "제안 수량",
            render: (r) => (
              <span className="font-semibold">
                {r.suggested_qty.toLocaleString()}
              </span>
            ),
          },
          {
            key: "preferred_supplier_id",
            header: "선호공급사",
            render: (r) =>
              r.preferred_supplier_id ? `#${r.preferred_supplier_id}` : (
                <span className="text-amber-600">미지정</span>
              ),
          },
        ]}
        rows={rows}
      />
    </AppShell>
  );
}
