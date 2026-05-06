"use client";
import { useEffect, useState } from "react";
import AppShell from "@/components/AppShell";
import DataTable from "@/components/DataTable";
import { api } from "@/lib/api";

type FieldType = "text" | "number" | "date" | "select" | "textarea" | "checkbox";
type Field = { key: string; label: string; type: FieldType; required: boolean; options: string[] | null };
type Step = { order: number; approver_id: number };
type Template = {
  id: number;
  code: string;
  name: string;
  description: string | null;
  schema_: Field[];
  default_steps: Step[];
  is_active: boolean;
};
type User = { id: number; full_name: string; email: string };

const TYPES: FieldType[] = ["text", "number", "date", "select", "textarea", "checkbox"];

export default function FormTemplatesPage() {
  const [templates, setTemplates] = useState<Template[]>([]);
  const [users, setUsers] = useState<User[]>([]);
  const [error, setError] = useState("");
  const [editing, setEditing] = useState<Partial<Template> | null>(null);

  const load = () =>
    api<Template[]>("/api/approvals/templates?active_only=false")
      .then(setTemplates)
      .catch((e) => setError(String(e)));

  useEffect(() => {
    load();
    api<User[]>("/api/auth/users")
      .then(setUsers)
      .catch(() => {});
  }, []);

  const startNew = () =>
    setEditing({
      code: "",
      name: "",
      description: "",
      schema_: [],
      default_steps: [],
      is_active: true,
    });

  const save = async () => {
    if (!editing) return;
    setError("");
    const payload = {
      code: editing.code,
      name: editing.name,
      description: editing.description,
      schema: editing.schema_ ?? [],
      default_steps: editing.default_steps ?? [],
      is_active: editing.is_active ?? true,
    };
    try {
      if (editing.id) {
        await api(`/api/approvals/templates/${editing.id}`, {
          method: "PUT",
          body: JSON.stringify(payload),
        });
      } else {
        await api("/api/approvals/templates", {
          method: "POST",
          body: JSON.stringify(payload),
        });
      }
      setEditing(null);
      await load();
    } catch (e) {
      setError(String(e));
    }
  };

  const remove = async (id: number) => {
    if (!confirm("삭제하시겠습니까?")) return;
    await api(`/api/approvals/templates/${id}`, { method: "DELETE" });
    await load();
  };

  const updateField = (idx: number, patch: Partial<Field>) => {
    if (!editing?.schema_) return;
    const next = [...editing.schema_];
    next[idx] = { ...next[idx], ...patch };
    setEditing({ ...editing, schema_: next });
  };

  return (
    <AppShell>
      <div className="flex justify-between items-center mb-4">
        <h1 className="text-2xl font-semibold">결재 양식 템플릿</h1>
        <button
          onClick={startNew}
          className="px-4 py-2 bg-brand-700 text-white rounded text-sm"
        >
          + 새 양식
        </button>
      </div>

      {error && <p className="text-red-600 text-sm mb-3">{error}</p>}

      <DataTable<Template>
        columns={[
          { key: "code", header: "코드" },
          { key: "name", header: "이름" },
          {
            key: "schema_",
            header: "필드 수",
            render: (t) => t.schema_.length,
          },
          {
            key: "default_steps",
            header: "결재선",
            render: (t) => t.default_steps.length,
          },
          {
            key: "is_active",
            header: "상태",
            render: (t) =>
              t.is_active ? (
                <span className="text-brand-700 text-xs">활성</span>
              ) : (
                <span className="text-slate-400 text-xs">비활성</span>
              ),
          },
          {
            key: "actions",
            header: "",
            render: (t) => (
              <div className="flex gap-3">
                <button
                  onClick={() => setEditing(t)}
                  className="text-blue-700 text-xs hover:underline"
                >
                  편집
                </button>
                <button
                  onClick={() => remove(t.id)}
                  className="text-red-600 text-xs hover:underline"
                >
                  삭제
                </button>
              </div>
            ),
          },
        ]}
        rows={templates}
      />

      {editing && (
        <div className="fixed inset-0 bg-black/30 flex items-center justify-center z-30">
          <div className="bg-white rounded-lg p-6 w-[40rem] max-h-[85vh] overflow-y-auto space-y-3">
            <div className="flex justify-between items-center">
              <h2 className="text-lg font-medium">
                {editing.id ? "양식 편집" : "새 양식"}
              </h2>
              <button
                onClick={() => setEditing(null)}
                className="text-slate-500"
              >
                ✕
              </button>
            </div>

            <div className="grid grid-cols-2 gap-2">
              <input
                placeholder="코드 (EXPENSE, LEAVE, ...)"
                value={editing.code ?? ""}
                onChange={(e) => setEditing({ ...editing, code: e.target.value })}
                className="border rounded px-2 py-1 text-sm"
                disabled={!!editing.id}
              />
              <input
                placeholder="이름"
                value={editing.name ?? ""}
                onChange={(e) => setEditing({ ...editing, name: e.target.value })}
                className="border rounded px-2 py-1 text-sm"
              />
            </div>
            <input
              placeholder="설명"
              value={editing.description ?? ""}
              onChange={(e) =>
                setEditing({ ...editing, description: e.target.value })
              }
              className="border rounded px-2 py-1 text-sm w-full"
            />

            <div className="border-t pt-3">
              <div className="flex justify-between items-center mb-2">
                <h3 className="font-medium text-sm">필드</h3>
                <button
                  onClick={() =>
                    setEditing({
                      ...editing,
                      schema_: [
                        ...(editing.schema_ ?? []),
                        { key: "", label: "", type: "text", required: false, options: null },
                      ],
                    })
                  }
                  className="text-xs px-2 py-1 border rounded"
                >
                  + 필드
                </button>
              </div>
              <div className="space-y-2">
                {(editing.schema_ ?? []).map((f, idx) => (
                  <div key={idx} className="grid grid-cols-12 gap-2 items-center">
                    <input
                      placeholder="key"
                      value={f.key}
                      onChange={(e) => updateField(idx, { key: e.target.value })}
                      className="border rounded px-2 py-1 text-sm col-span-3"
                    />
                    <input
                      placeholder="라벨"
                      value={f.label}
                      onChange={(e) => updateField(idx, { label: e.target.value })}
                      className="border rounded px-2 py-1 text-sm col-span-3"
                    />
                    <select
                      value={f.type}
                      onChange={(e) =>
                        updateField(idx, { type: e.target.value as FieldType })
                      }
                      className="border rounded px-2 py-1 text-sm col-span-2"
                    >
                      {TYPES.map((t) => (
                        <option key={t} value={t}>
                          {t}
                        </option>
                      ))}
                    </select>
                    <input
                      placeholder={f.type === "select" ? "옵션,콤마,구분" : "—"}
                      disabled={f.type !== "select"}
                      value={f.options?.join(",") ?? ""}
                      onChange={(e) =>
                        updateField(idx, {
                          options: e.target.value
                            ? e.target.value.split(",").map((x) => x.trim())
                            : null,
                        })
                      }
                      className="border rounded px-2 py-1 text-sm col-span-3 disabled:bg-slate-100"
                    />
                    <label className="flex items-center gap-1 col-span-1 text-xs">
                      <input
                        type="checkbox"
                        checked={f.required}
                        onChange={(e) => updateField(idx, { required: e.target.checked })}
                      />
                      필수
                    </label>
                  </div>
                ))}
              </div>
            </div>

            <div className="border-t pt-3">
              <div className="flex justify-between items-center mb-2">
                <h3 className="font-medium text-sm">기본 결재선</h3>
                <button
                  onClick={() =>
                    setEditing({
                      ...editing,
                      default_steps: [
                        ...(editing.default_steps ?? []),
                        { order: (editing.default_steps?.length ?? 0) + 1, approver_id: 0 },
                      ],
                    })
                  }
                  className="text-xs px-2 py-1 border rounded"
                >
                  + 단계
                </button>
              </div>
              {(editing.default_steps ?? []).map((s, idx) => (
                <div key={idx} className="flex gap-2 mb-1 text-sm">
                  <span className="w-12">단계 {s.order}</span>
                  <select
                    value={s.approver_id}
                    onChange={(e) => {
                      const next = [...(editing.default_steps ?? [])];
                      next[idx] = { ...next[idx], approver_id: Number(e.target.value) };
                      setEditing({ ...editing, default_steps: next });
                    }}
                    className="border rounded px-2 py-1 flex-1"
                  >
                    <option value={0}>결재자 선택</option>
                    {users.map((u) => (
                      <option key={u.id} value={u.id}>
                        {u.full_name} ({u.email})
                      </option>
                    ))}
                  </select>
                </div>
              ))}
            </div>

            <div className="flex justify-end gap-2 pt-2">
              <button
                onClick={() => setEditing(null)}
                className="px-3 py-1 border rounded text-sm"
              >
                취소
              </button>
              <button
                onClick={save}
                className="px-3 py-1 bg-brand-700 text-white rounded text-sm"
              >
                저장
              </button>
            </div>
          </div>
        </div>
      )}
    </AppShell>
  );
}
