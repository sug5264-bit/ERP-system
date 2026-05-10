"use client";
import { useEffect, useState } from "react";
import AppShell from "@/components/AppShell";
import DataTable from "@/components/DataTable";
import Pager from "@/components/Pager";
import { Page, api } from "@/lib/api";
import { hasRole, useMe } from "@/lib/auth";

type BomComponent = {
  id?: number;
  component_item_id: number;
  quantity_per: string;
  notes: string | null;
};
type Bom = {
  id: number;
  finished_item_id: number;
  version: string;
  output_quantity: string;
  notes: string | null;
  is_active: boolean;
  components: BomComponent[];
};
type WorkOrder = {
  id: number;
  wo_no: string;
  bom_id: number;
  quantity: string;
  status: string;
  started_at: string | null;
  completed_at: string | null;
  notes: string | null;
};

type Tab = "boms" | "wo";

export default function ManufacturingPage() {
  const me = useMe();
  const isAdmin = hasRole(me, "admin");
  const canManage = hasRole(me, "manager");
  const [tab, setTab] = useState<Tab>("boms");
  const [error, setError] = useState("");

  return (
    <AppShell>
      <div className="flex justify-between items-center mb-4">
        <h1 className="text-2xl font-semibold">제조 / Manufacturing</h1>
        <div className="flex gap-1">
          {(["boms", "wo"] as Tab[]).map((t) => (
            <button
              key={t}
              onClick={() => setTab(t)}
              className={`px-3 py-1 text-sm rounded ${
                tab === t
                  ? "bg-slate-900 text-white"
                  : "bg-slate-100 hover:bg-slate-200"
              }`}
            >
              {t === "boms" ? "BOM" : "작업지시"}
            </button>
          ))}
        </div>
      </div>

      {error && <p className="text-red-600 text-sm mb-3">{error}</p>}
      {tab === "boms" && <BomTab onError={setError} isAdmin={isAdmin} />}
      {tab === "wo" && <WoTab onError={setError} canManage={canManage} />}
    </AppShell>
  );
}

function BomTab({
  onError,
  isAdmin,
}: {
  onError: (s: string) => void;
  isAdmin: boolean;
}) {
  const [rows, setRows] = useState<Bom[]>([]);
  const [page, setPage] = useState(1);
  const [meta, setMeta] = useState({ total: 0, pages: 1 });
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({
    finished_item_id: "",
    version: "v1",
    output_quantity: "1",
    notes: "",
    components: [{ component_item_id: "", quantity_per: "1" }],
  });

  const load = async () => {
    try {
      const r = await api<Page<Bom>>(`/api/manufacturing/boms?page=${page}&size=20`);
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
      await api("/api/manufacturing/boms", {
        method: "POST",
        body: JSON.stringify({
          finished_item_id: Number(form.finished_item_id),
          version: form.version,
          output_quantity: Number(form.output_quantity),
          notes: form.notes || null,
          components: form.components.map((c) => ({
            component_item_id: Number(c.component_item_id),
            quantity_per: Number(c.quantity_per),
          })),
        }),
      });
      setShowForm(false);
      setForm({
        finished_item_id: "",
        version: "v1",
        output_quantity: "1",
        notes: "",
        components: [{ component_item_id: "", quantity_per: "1" }],
      });
      await load();
    } catch (e) {
      onError(String(e));
    }
  };

  return (
    <>
      {isAdmin && (
        <div className="mb-3">
          <button
            onClick={() => setShowForm((s) => !s)}
            className="bg-slate-900 text-white px-3 py-1 rounded text-sm"
          >
            {showForm ? "닫기" : "+ BOM 추가"}
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
              type="number"
              placeholder="완제품 ID"
              value={form.finished_item_id}
              onChange={(e) =>
                setForm({ ...form, finished_item_id: e.target.value })
              }
              className="border rounded px-2 py-1"
            />
            <input
              placeholder="버전"
              value={form.version}
              onChange={(e) => setForm({ ...form, version: e.target.value })}
              className="border rounded px-2 py-1"
            />
            <input
              type="number"
              placeholder="산출량"
              value={form.output_quantity}
              onChange={(e) =>
                setForm({ ...form, output_quantity: e.target.value })
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
            <p className="text-sm font-medium">구성품</p>
            {form.components.map((c, i) => (
              <div key={i} className="grid grid-cols-3 gap-2">
                <input
                  required
                  type="number"
                  placeholder="원료 품목 ID"
                  value={c.component_item_id}
                  onChange={(e) => {
                    const cs = [...form.components];
                    cs[i].component_item_id = e.target.value;
                    setForm({ ...form, components: cs });
                  }}
                  className="border rounded px-2 py-1"
                />
                <input
                  required
                  type="number"
                  placeholder="단위당 수량"
                  value={c.quantity_per}
                  onChange={(e) => {
                    const cs = [...form.components];
                    cs[i].quantity_per = e.target.value;
                    setForm({ ...form, components: cs });
                  }}
                  className="border rounded px-2 py-1"
                />
                <button
                  type="button"
                  onClick={() => {
                    const cs = form.components.filter((_, j) => j !== i);
                    setForm({
                      ...form,
                      components: cs.length ? cs : form.components,
                    });
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
                  components: [
                    ...form.components,
                    { component_item_id: "", quantity_per: "1" },
                  ],
                })
              }
              className="text-sm text-blue-700"
            >
              + 구성품 추가
            </button>
          </div>
          <button className="bg-emerald-700 text-white px-4 py-1 rounded">
            저장
          </button>
        </form>
      )}
      <DataTable<Bom>
        columns={[
          { key: "id", header: "ID" },
          { key: "finished_item_id", header: "완제품" },
          { key: "version", header: "버전" },
          { key: "output_quantity", header: "산출량" },
          {
            key: "components",
            header: "구성품 수",
            render: (r) => r.components.length,
          },
          { key: "is_active", header: "활성", render: (r) => (r.is_active ? "✓" : "✗") },
          { key: "notes", header: "비고" },
        ]}
        rows={rows}
      />
      <Pager page={page} pages={meta.pages} total={meta.total} onChange={setPage} />
    </>
  );
}

function WoTab({
  onError,
  canManage,
}: {
  onError: (s: string) => void;
  canManage: boolean;
}) {
  const [rows, setRows] = useState<WorkOrder[]>([]);
  const [page, setPage] = useState(1);
  const [meta, setMeta] = useState({ total: 0, pages: 1 });
  const [form, setForm] = useState({
    wo_no: "",
    bom_id: "",
    quantity: "1",
    notes: "",
  });

  const load = async () => {
    try {
      const r = await api<Page<WorkOrder>>(
        `/api/manufacturing/work-orders?page=${page}&size=20`
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
      await api("/api/manufacturing/work-orders", {
        method: "POST",
        body: JSON.stringify({
          wo_no: form.wo_no,
          bom_id: Number(form.bom_id),
          quantity: Number(form.quantity),
          notes: form.notes || null,
        }),
      });
      setForm({ wo_no: "", bom_id: "", quantity: "1", notes: "" });
      await load();
    } catch (e) {
      onError(String(e));
    }
  };

  const transition = async (id: number, action: "release" | "complete") => {
    try {
      await api(`/api/manufacturing/work-orders/${id}/${action}`, {
        method: "POST",
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
          className="bg-white p-4 rounded-lg shadow-sm border border-slate-200 grid grid-cols-1 md:grid-cols-5 gap-2 mb-4"
        >
          <input
            required
            placeholder="WO 번호"
            value={form.wo_no}
            onChange={(e) => setForm({ ...form, wo_no: e.target.value })}
            className="border rounded px-2 py-1"
          />
          <input
            required
            type="number"
            placeholder="BOM ID"
            value={form.bom_id}
            onChange={(e) => setForm({ ...form, bom_id: e.target.value })}
            className="border rounded px-2 py-1"
          />
          <input
            required
            type="number"
            placeholder="생산수량"
            value={form.quantity}
            onChange={(e) => setForm({ ...form, quantity: e.target.value })}
            className="border rounded px-2 py-1"
          />
          <input
            placeholder="비고"
            value={form.notes}
            onChange={(e) => setForm({ ...form, notes: e.target.value })}
            className="border rounded px-2 py-1"
          />
          <button className="bg-slate-900 text-white px-3 rounded">
            작업지시 생성
          </button>
        </form>
      )}
      <DataTable<WorkOrder>
        columns={[
          { key: "wo_no", header: "WO" },
          { key: "bom_id", header: "BOM" },
          { key: "quantity", header: "수량" },
          { key: "status", header: "상태" },
          { key: "started_at", header: "시작" },
          { key: "completed_at", header: "완료" },
          {
            key: "_act",
            header: "관리",
            sortable: false,
            render: (r) =>
              canManage ? (
                <div className="flex gap-2">
                  {r.status === "draft" && (
                    <button
                      onClick={() => transition(r.id, "release")}
                      className="text-blue-700 text-xs hover:underline"
                    >
                      착수
                    </button>
                  )}
                  {r.status === "in_progress" && (
                    <button
                      onClick={() => transition(r.id, "complete")}
                      className="text-emerald-700 text-xs hover:underline"
                    >
                      완료
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
