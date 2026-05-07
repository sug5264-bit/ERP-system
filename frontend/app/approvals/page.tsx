"use client";
import { useEffect, useState } from "react";
import AppShell from "@/components/AppShell";
import { api } from "@/lib/api";
import { useMe } from "@/lib/auth";

type Step = {
  id: number;
  order: number;
  approver_id: number;
  status: "pending" | "approved" | "rejected" | "cancelled";
  comment: string | null;
  decided_at: string | null;
};

type Request = {
  id: number;
  title: string;
  resource_type: string;
  resource_id: number;
  requester_id: number;
  status: "pending" | "approved" | "rejected" | "cancelled";
  current_step: number;
  created_at: string;
  template_id: number | null;
  form_data: Record<string, any> | null;
  steps: Step[];
};

type User = { id: number; email: string; full_name: string };

type FieldType = "text" | "number" | "date" | "select" | "textarea" | "checkbox";
type Field = { key: string; label: string; type: FieldType; required: boolean; options: string[] | null };
type TemplateStep = { order: number; approver_id: number };
type Template = {
  id: number;
  code: string;
  name: string;
  description: string | null;
  schema_: Field[];
  default_steps: TemplateStep[];
  is_active: boolean;
};

const TABS = [
  { key: "inbox", label: "결재할 요청" },
  { key: "mine", label: "내가 올린 요청" },
  { key: "all", label: "전체" },
] as const;

export default function ApprovalsPage() {
  const me = useMe();
  const [tab, setTab] = useState<(typeof TABS)[number]["key"]>("inbox");
  const [requests, setRequests] = useState<Request[]>([]);
  const [users, setUsers] = useState<User[]>([]);
  const [error, setError] = useState("");

  const [form, setForm] = useState({
    title: "",
    resource_type: "sales_order",
    resource_id: "",
    approver_ids: [] as string[],
  });

  const [templates, setTemplates] = useState<Template[]>([]);
  const [templateId, setTemplateId] = useState<string>("");
  const [formValues, setFormValues] = useState<Record<string, any>>({});

  const load = () =>
    api<Request[]>(`/api/approvals?scope=${tab}`)
      .then(setRequests)
      .catch((e) => setError(String(e)));

  useEffect(() => {
    load();
  }, [tab]);

  useEffect(() => {
    api<{ items: User[] }>("/api/auth/users?page=1&size=200")
      .then((r) => setUsers(r.items))
      .catch(() => setUsers([]));
    api<Template[]>("/api/approvals/templates")
      .then(setTemplates)
      .catch(() => setTemplates([]));
  }, []);

  const selectedTemplate = templates.find((t) => String(t.id) === templateId);

  // When a template is picked, prefill the approver chain from default_steps
  useEffect(() => {
    if (!selectedTemplate) return;
    setForm((f) => ({
      ...f,
      title: f.title || selectedTemplate.name,
      approver_ids: selectedTemplate.default_steps
        .sort((a, b) => a.order - b.order)
        .map((s) => String(s.approver_id)),
    }));
    // Clear values when switching templates
    setFormValues({});
  }, [templateId]);

  const userName = (id: number) => users.find((u) => u.id === id)?.full_name ?? `user#${id}`;

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");

    // Validate template required fields
    if (selectedTemplate) {
      for (const f of selectedTemplate.schema_) {
        if (f.required && !formValues[f.key]) {
          setError(`필수 항목: ${f.label}`);
          return;
        }
      }
    }

    try {
      await api("/api/approvals", {
        method: "POST",
        body: JSON.stringify({
          title: form.title,
          resource_type: form.resource_type,
          resource_id: Number(form.resource_id) || 0,
          template_id: selectedTemplate ? selectedTemplate.id : null,
          form_data: selectedTemplate ? formValues : null,
          steps: form.approver_ids
            .filter(Boolean)
            .map((id, idx) => ({ order: idx + 1, approver_id: Number(id) })),
        }),
      });
      setForm({ title: "", resource_type: "sales_order", resource_id: "", approver_ids: [] });
      setTemplateId("");
      setFormValues({});
      await load();
    } catch (e) {
      setError(String(e));
    }
  };

  const decide = async (id: number, action: "approve" | "reject") => {
    const comment = prompt(action === "approve" ? "승인 메모 (선택)" : "반려 사유");
    if (action === "reject" && !comment) return;
    try {
      await api(`/api/approvals/${id}/${action}`, {
        method: "POST",
        body: JSON.stringify({ comment: comment || null }),
      });
      await load();
    } catch (e) {
      setError(String(e));
    }
  };

  const cancel = async (id: number) => {
    if (!confirm("이 결재 요청을 취소하시겠습니까?")) return;
    try {
      await api(`/api/approvals/${id}/cancel`, { method: "POST" });
      await load();
    } catch (e) {
      setError(String(e));
    }
  };

  const statusColor = (s: string) =>
    s === "approved"
      ? "bg-green-100 text-green-700 dark:bg-green-900 dark:text-green-200"
      : s === "rejected"
      ? "bg-red-100 text-red-700 dark:bg-red-900 dark:text-red-200"
      : s === "cancelled"
      ? "bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300"
      : "bg-amber-100 text-amber-700 dark:bg-amber-900 dark:text-amber-200";

  return (
    <AppShell>
      <h1 className="text-2xl font-semibold mb-4">결재 워크플로</h1>

      <form
        onSubmit={submit}
        className="bg-white p-4 rounded-lg shadow-sm border border-slate-200 mb-6 space-y-3"
      >
        <h2 className="text-lg font-medium">새 결재 요청</h2>

        <div>
          <label className="text-sm text-slate-600 block mb-1">양식 (선택)</label>
          <select
            value={templateId}
            onChange={(e) => setTemplateId(e.target.value)}
            className="border rounded px-2 py-1 w-full"
          >
            <option value="">양식 없이 자유 결재</option>
            {templates.map((t) => (
              <option key={t.id} value={t.id}>
                {t.name} ({t.code})
              </option>
            ))}
          </select>
          {selectedTemplate?.description && (
            <p className="text-xs text-slate-500 mt-1">{selectedTemplate.description}</p>
          )}
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
          <input
            required
            placeholder="제목"
            value={form.title}
            onChange={(e) => setForm({ ...form, title: e.target.value })}
            className="border rounded px-2 py-1"
          />
          <select
            value={form.resource_type}
            onChange={(e) => setForm({ ...form, resource_type: e.target.value })}
            className="border rounded px-2 py-1"
          >
            <option value="sales_order">sales_order</option>
            <option value="journal_entry">journal_entry</option>
            <option value="employee">employee</option>
            <option value="expense">expense</option>
            <option value="other">other</option>
          </select>
          <input
            type="number"
            placeholder="리소스 ID (양식만 쓰면 0)"
            value={form.resource_id}
            onChange={(e) => setForm({ ...form, resource_id: e.target.value })}
            className="border rounded px-2 py-1"
          />
        </div>

        {selectedTemplate && selectedTemplate.schema_.length > 0 && (
          <div className="border-t pt-3 space-y-2">
            <div className="text-sm font-medium">{selectedTemplate.name} 입력</div>
            {selectedTemplate.schema_.map((field) => (
              <div key={field.key} className="grid grid-cols-12 items-center gap-2">
                <label className="col-span-3 text-sm">
                  {field.label}
                  {field.required && <span className="text-red-600 ml-1">*</span>}
                </label>
                <div className="col-span-9">
                  {field.type === "textarea" ? (
                    <textarea
                      value={formValues[field.key] ?? ""}
                      onChange={(e) =>
                        setFormValues({ ...formValues, [field.key]: e.target.value })
                      }
                      className="border rounded px-2 py-1 w-full"
                      rows={3}
                    />
                  ) : field.type === "select" ? (
                    <select
                      value={formValues[field.key] ?? ""}
                      onChange={(e) =>
                        setFormValues({ ...formValues, [field.key]: e.target.value })
                      }
                      className="border rounded px-2 py-1 w-full"
                    >
                      <option value="">선택</option>
                      {(field.options ?? []).map((o) => (
                        <option key={o} value={o}>
                          {o}
                        </option>
                      ))}
                    </select>
                  ) : field.type === "checkbox" ? (
                    <input
                      type="checkbox"
                      checked={!!formValues[field.key]}
                      onChange={(e) =>
                        setFormValues({ ...formValues, [field.key]: e.target.checked })
                      }
                    />
                  ) : (
                    <input
                      type={field.type === "number" ? "number" : field.type === "date" ? "date" : "text"}
                      value={formValues[field.key] ?? ""}
                      onChange={(e) =>
                        setFormValues({
                          ...formValues,
                          [field.key]:
                            field.type === "number" ? Number(e.target.value) : e.target.value,
                        })
                      }
                      className="border rounded px-2 py-1 w-full"
                    />
                  )}
                </div>
              </div>
            ))}
          </div>
        )}

        <div className="space-y-2">
          <div className="text-sm text-slate-600">결재자 (순서대로)</div>
          {form.approver_ids.map((id, idx) => (
            <div key={idx} className="flex gap-2">
              <span className="text-sm self-center w-12">단계 {idx + 1}</span>
              <select
                value={id}
                onChange={(e) =>
                  setForm({
                    ...form,
                    approver_ids: form.approver_ids.map((v, i) => (i === idx ? e.target.value : v)),
                  })
                }
                className="border rounded px-2 py-1 flex-1"
              >
                <option value="">결재자 선택</option>
                {users.map((u) => (
                  <option key={u.id} value={u.id}>
                    {u.full_name} ({u.email})
                  </option>
                ))}
              </select>
              <button
                type="button"
                onClick={() =>
                  setForm({
                    ...form,
                    approver_ids: form.approver_ids.filter((_, i) => i !== idx),
                  })
                }
                className="text-red-600 text-xs"
              >
                삭제
              </button>
            </div>
          ))}
          <button
            type="button"
            onClick={() => setForm({ ...form, approver_ids: [...form.approver_ids, ""] })}
            className="px-3 py-1 border rounded text-sm"
          >
            + 결재자 추가
          </button>
        </div>
        <button
          type="submit"
          disabled={form.approver_ids.filter(Boolean).length === 0}
          className="bg-slate-900 text-white px-4 py-1 rounded disabled:opacity-50"
        >
          요청 제출
        </button>
      </form>

      {error && <p className="text-red-600 text-sm mb-3">{error}</p>}

      <div className="flex gap-2 mb-4 border-b border-slate-200">
        {TABS.map((t) => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            className={`px-4 py-2 text-sm ${
              tab === t.key
                ? "border-b-2 border-slate-900 dark:border-slate-100 font-medium"
                : "text-slate-500"
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      <div className="space-y-3">
        {requests.length === 0 && (
          <p className="text-sm text-slate-500">결재 요청이 없습니다.</p>
        )}
        {requests.map((r) => {
          const myStep = r.steps.find(
            (s) => s.order === r.current_step && s.status === "pending"
          );
          const canDecide = myStep && me && myStep.approver_id === me.id;
          const canCancel = me && r.requester_id === me.id && r.status === "pending";
          return (
            <div
              key={r.id}
              className="bg-white p-4 rounded-lg shadow-sm border border-slate-200"
            >
              <div className="flex justify-between items-start">
                <div>
                  <div className="font-medium">{r.title}</div>
                  <div className="text-xs text-slate-500">
                    {r.resource_type}#{r.resource_id} · 요청자: {userName(r.requester_id)} ·{" "}
                    {new Date(r.created_at).toLocaleString()}
                  </div>
                </div>
                <span className={`px-2 py-0.5 rounded text-xs uppercase ${statusColor(r.status)}`}>
                  {r.status}
                </span>
              </div>

              {r.form_data && (
                <dl className="mt-3 grid grid-cols-1 md:grid-cols-2 gap-x-4 gap-y-1 text-sm bg-slate-50 dark:bg-slate-800 rounded p-2">
                  {Object.entries(r.form_data).map(([k, v]) => (
                    <div key={k} className="flex gap-2">
                      <dt className="text-slate-500 capitalize min-w-[6rem]">{k}</dt>
                      <dd className="font-medium">{String(v)}</dd>
                    </div>
                  ))}
                </dl>
              )}

              <ol className="mt-3 space-y-1">
                {r.steps.map((s) => (
                  <li key={s.id} className="flex items-center gap-2 text-sm">
                    <span className="w-6 text-slate-500">{s.order}.</span>
                    <span className="flex-1">{userName(s.approver_id)}</span>
                    <span className={`px-2 py-0.5 rounded text-xs uppercase ${statusColor(s.status)}`}>
                      {s.status}
                    </span>
                    {s.comment && (
                      <span className="text-xs text-slate-500 italic">"{s.comment}"</span>
                    )}
                  </li>
                ))}
              </ol>
              {(canDecide || canCancel) && (
                <div className="mt-3 flex gap-2">
                  {canDecide && (
                    <>
                      <button
                        onClick={() => decide(r.id, "approve")}
                        className="px-3 py-1 bg-green-600 text-white rounded text-sm"
                      >
                        승인
                      </button>
                      <button
                        onClick={() => decide(r.id, "reject")}
                        className="px-3 py-1 bg-red-600 text-white rounded text-sm"
                      >
                        반려
                      </button>
                    </>
                  )}
                  {canCancel && (
                    <button
                      onClick={() => cancel(r.id)}
                      className="px-3 py-1 border rounded text-sm"
                    >
                      취소
                    </button>
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </AppShell>
  );
}
