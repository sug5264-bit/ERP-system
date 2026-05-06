"use client";
import { useEffect, useState } from "react";
import AppShell from "@/components/AppShell";
import DataTable from "@/components/DataTable";
import { api } from "@/lib/api";

type FieldType = "text" | "number" | "date" | "boolean" | "select";
type FieldDef = {
  id: number;
  entity_type: string;
  key: string;
  label: string;
  field_type: FieldType;
  options: string[] | null;
  required: boolean;
};

const ENTITY_TYPES = ["item", "employee", "customer", "order"];
const FIELD_TYPES: FieldType[] = ["text", "number", "date", "boolean", "select"];

export default function CustomFieldsPage() {
  const [defs, setDefs] = useState<FieldDef[]>([]);
  const [error, setError] = useState("");
  const [form, setForm] = useState({
    entity_type: "item",
    key: "",
    label: "",
    field_type: "text" as FieldType,
    options: "",
    required: false,
  });

  const load = () =>
    api<FieldDef[]>("/api/custom-fields/definitions")
      .then(setDefs)
      .catch((e) => setError(String(e)));

  useEffect(() => {
    load();
  }, []);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    try {
      await api("/api/custom-fields/definitions", {
        method: "POST",
        body: JSON.stringify({
          entity_type: form.entity_type,
          key: form.key,
          label: form.label,
          field_type: form.field_type,
          required: form.required,
          options:
            form.field_type === "select"
              ? form.options.split(",").map((s) => s.trim()).filter(Boolean)
              : null,
        }),
      });
      setForm({ ...form, key: "", label: "", options: "" });
      await load();
    } catch (e) {
      setError(String(e));
    }
  };

  const remove = async (id: number) => {
    if (!confirm("이 필드와 모든 값을 삭제합니다. 진행할까요?")) return;
    try {
      await api(`/api/custom-fields/definitions/${id}`, { method: "DELETE" });
      await load();
    } catch (e) {
      setError(String(e));
    }
  };

  return (
    <AppShell>
      <h1 className="text-2xl font-semibold mb-4">커스텀 필드</h1>

      <form
        onSubmit={submit}
        className="bg-white p-4 rounded-lg shadow-sm border border-slate-200 grid grid-cols-1 md:grid-cols-6 gap-3 mb-6"
      >
        <select
          value={form.entity_type}
          onChange={(e) => setForm({ ...form, entity_type: e.target.value })}
          className="border rounded px-2 py-1"
        >
          {ENTITY_TYPES.map((t) => (
            <option key={t} value={t}>
              {t}
            </option>
          ))}
        </select>
        <input
          required
          placeholder="키 (예: origin_country)"
          value={form.key}
          onChange={(e) => setForm({ ...form, key: e.target.value })}
          className="border rounded px-2 py-1"
        />
        <input
          required
          placeholder="라벨 (예: 원산지)"
          value={form.label}
          onChange={(e) => setForm({ ...form, label: e.target.value })}
          className="border rounded px-2 py-1"
        />
        <select
          value={form.field_type}
          onChange={(e) => setForm({ ...form, field_type: e.target.value as FieldType })}
          className="border rounded px-2 py-1"
        >
          {FIELD_TYPES.map((t) => (
            <option key={t} value={t}>
              {t}
            </option>
          ))}
        </select>
        <input
          placeholder={
            form.field_type === "select" ? "선택지 (콤마 구분)" : "—"
          }
          disabled={form.field_type !== "select"}
          value={form.options}
          onChange={(e) => setForm({ ...form, options: e.target.value })}
          className="border rounded px-2 py-1 disabled:bg-slate-100"
        />
        <button className="bg-slate-900 text-white rounded">필드 추가</button>
      </form>

      {error && <p className="text-red-600 text-sm mb-3">{error}</p>}

      <DataTable<FieldDef>
        columns={[
          { key: "entity_type", header: "대상" },
          { key: "key", header: "키" },
          { key: "label", header: "라벨" },
          { key: "field_type", header: "타입" },
          {
            key: "options",
            header: "선택지",
            render: (d) => d.options?.join(", ") ?? "-",
          },
          {
            key: "actions",
            header: "",
            render: (d) => (
              <button
                onClick={() => remove(d.id)}
                className="text-red-600 text-xs hover:underline"
              >
                삭제
              </button>
            ),
          },
        ]}
        rows={defs}
      />
    </AppShell>
  );
}
