"use client";
import { useState } from "react";
import { api } from "@/lib/api";
import { hasRole, useMe } from "@/lib/auth";

export type EditField = {
  key: string;
  label: string;
  type?: "text" | "number" | "email";
};

/**
 * Admin-only inline action buttons that show "수정 / 삭제" on each row.
 *
 *   <EditDeleteActions
 *     row={item}
 *     fields={[{key:"name", label:"품목명"}, {key:"unit_price", label:"단가", type:"number"}]}
 *     patchPath={(r) => `/api/inventory/items/${r.id}`}
 *     deletePath={(r) => `/api/inventory/items/${r.id}`}
 *     onChange={load}
 *   />
 *
 * Hidden entirely for non-admin users — backend also rejects them.
 */
export default function EditDeleteActions<T extends { id: number | string }>({
  row,
  fields,
  patchPath,
  deletePath,
  onChange,
  confirmText,
}: {
  row: T;
  fields: EditField[];
  patchPath: (r: T) => string;
  deletePath: (r: T) => string;
  onChange: () => void | Promise<void>;
  confirmText?: string;
}) {
  const me = useMe();
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState<Record<string, any>>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  if (!hasRole(me, "admin")) return null;

  const startEdit = () => {
    const initial: Record<string, any> = {};
    fields.forEach((f) => {
      initial[f.key] = (row as any)[f.key] ?? "";
    });
    setDraft(initial);
    setError("");
    setEditing(true);
  };

  const submit = async () => {
    setBusy(true);
    setError("");
    try {
      const body: Record<string, any> = {};
      for (const f of fields) {
        const v = draft[f.key];
        if (v === "" || v === null || v === undefined) continue;
        body[f.key] = f.type === "number" ? Number(v) : v;
      }
      await api(patchPath(row), {
        method: "PATCH",
        body: JSON.stringify(body),
      });
      setEditing(false);
      await onChange();
    } catch (e: any) {
      setError(String(e?.message ?? e));
    } finally {
      setBusy(false);
    }
  };

  const remove = async () => {
    if (!confirm(confirmText ?? "정말 삭제하시겠습니까? 되돌릴 수 없습니다.")) return;
    setBusy(true);
    setError("");
    try {
      await api(deletePath(row), { method: "DELETE" });
      await onChange();
    } catch (e: any) {
      // surface backend cascade-violations to the user
      alert(`삭제 실패: ${e?.message ?? e}`);
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <div className="flex gap-2">
        <button
          onClick={startEdit}
          className="text-blue-700 text-xs hover:underline"
        >
          수정
        </button>
        <button
          onClick={remove}
          disabled={busy}
          className="text-red-600 text-xs hover:underline disabled:opacity-50"
        >
          삭제
        </button>
      </div>

      {editing && (
        <div className="fixed inset-0 bg-black/30 flex items-center justify-center z-30">
          <div className="bg-white dark:bg-slate-900 rounded-lg p-6 w-96 space-y-3 max-h-[80vh] overflow-y-auto">
            <div className="flex justify-between items-center">
              <h2 className="text-lg font-medium">수정</h2>
              <button
                onClick={() => setEditing(false)}
                className="text-slate-500 hover:text-slate-900"
              >
                ✕
              </button>
            </div>
            {fields.map((f) => (
              <div key={f.key}>
                <label className="block text-xs text-slate-600 mb-1">
                  {f.label}
                </label>
                <input
                  type={f.type ?? "text"}
                  value={draft[f.key] ?? ""}
                  onChange={(e) =>
                    setDraft({ ...draft, [f.key]: e.target.value })
                  }
                  className="border rounded px-2 py-1 w-full text-sm"
                />
              </div>
            ))}
            {error && <p className="text-red-600 text-xs">{error}</p>}
            <div className="flex justify-end gap-2 pt-2">
              <button
                onClick={() => setEditing(false)}
                className="px-3 py-1 border rounded text-sm"
              >
                취소
              </button>
              <button
                onClick={submit}
                disabled={busy}
                className="px-3 py-1 bg-brand-700 text-white rounded text-sm disabled:opacity-50"
              >
                {busy ? "저장 중..." : "저장"}
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
