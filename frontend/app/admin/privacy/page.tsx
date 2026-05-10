"use client";
import { useEffect, useState } from "react";
import AppShell from "@/components/AppShell";
import DataTable from "@/components/DataTable";
import { api } from "@/lib/api";
import { hasRole, useMe } from "@/lib/auth";

type DSR = {
  id: number;
  type: "access" | "erasure" | "portability" | "correction";
  subject_email: string;
  subject_name: string | null;
  description: string | null;
  status: "pending" | "in_progress" | "completed" | "rejected";
  received_at: string;
  due_at: string | null;
  completed_at: string | null;
  response_notes: string | null;
};

export default function PrivacyPage() {
  const me = useMe();
  const isAdmin = hasRole(me, "admin");
  const [rows, setRows] = useState<DSR[]>([]);
  const [error, setError] = useState("");
  const [bundle, setBundle] = useState<any>(null);
  const [bundleEmail, setBundleEmail] = useState("");
  const [form, setForm] = useState({
    type: "access",
    subject_email: "",
    subject_name: "",
    description: "",
  });

  const load = async () => {
    try {
      setRows(await api<DSR[]>("/api/privacy/requests"));
    } catch (e) {
      setError(String(e));
    }
  };
  useEffect(() => {
    load();
  }, []);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    try {
      await api("/api/privacy/requests", {
        method: "POST",
        body: JSON.stringify({
          type: form.type,
          subject_email: form.subject_email,
          subject_name: form.subject_name || null,
          description: form.description || null,
        }),
      });
      setForm({ type: "access", subject_email: "", subject_name: "", description: "" });
      await load();
    } catch (e) {
      setError(String(e));
    }
  };

  const complete = async (id: number) => {
    const note = prompt("처리 메모 (선택)") || "";
    try {
      await api(
        `/api/privacy/requests/${id}/complete?response_notes=${encodeURIComponent(note)}`,
        { method: "POST" }
      );
      await load();
    } catch (e) {
      setError(String(e));
    }
  };

  const reject = async (id: number) => {
    const reason = prompt("반려 사유");
    if (!reason) return;
    try {
      await api(
        `/api/privacy/requests/${id}/reject?reason=${encodeURIComponent(reason)}`,
        { method: "POST" }
      );
      await load();
    } catch (e) {
      setError(String(e));
    }
  };

  const fetchBundle = async () => {
    setError("");
    if (!bundleEmail) return;
    try {
      setBundle(
        await api(`/api/privacy/access-bundle?email=${encodeURIComponent(bundleEmail)}`)
      );
    } catch (e) {
      setError(String(e));
    }
  };

  const eraseUser = async () => {
    if (!bundleEmail) return;
    if (!confirm(`${bundleEmail} 사용자/직원의 PII를 익명화합니다. 진행할까요?`)) return;
    try {
      await api(`/api/privacy/erase-user?email=${encodeURIComponent(bundleEmail)}`, {
        method: "POST",
      });
      await fetchBundle();
    } catch (e) {
      setError(String(e));
    }
  };

  return (
    <AppShell>
      <h1 className="text-2xl font-semibold mb-4">개인정보 / GDPR · PIPA</h1>
      {error && <p className="text-red-600 text-sm mb-3">{error}</p>}

      <form
        onSubmit={submit}
        className="bg-white p-4 rounded-lg border border-slate-200 grid grid-cols-1 md:grid-cols-5 gap-2 mb-4"
      >
        <select
          value={form.type}
          onChange={(e) => setForm({ ...form, type: e.target.value })}
          className="border rounded px-2 py-1"
        >
          <option value="access">열람 요청</option>
          <option value="erasure">삭제 요청</option>
          <option value="portability">이동 요청</option>
          <option value="correction">정정 요청</option>
        </select>
        <input
          required
          type="email"
          placeholder="대상 이메일"
          value={form.subject_email}
          onChange={(e) => setForm({ ...form, subject_email: e.target.value })}
          className="border rounded px-2 py-1"
        />
        <input
          placeholder="대상 이름"
          value={form.subject_name}
          onChange={(e) => setForm({ ...form, subject_name: e.target.value })}
          className="border rounded px-2 py-1"
        />
        <input
          placeholder="요청 내용"
          value={form.description}
          onChange={(e) => setForm({ ...form, description: e.target.value })}
          className="border rounded px-2 py-1 col-span-1 md:col-span-2"
        />
        <button className="bg-slate-900 text-white rounded">+ DSR 접수</button>
      </form>

      <DataTable<DSR>
        columns={[
          { key: "id", header: "ID" },
          { key: "type", header: "유형" },
          { key: "subject_email", header: "대상" },
          { key: "received_at", header: "접수" },
          { key: "due_at", header: "기한 (PIPA 10일)" },
          {
            key: "status",
            header: "상태",
            render: (r) => (
              <span
                className={
                  r.status === "completed"
                    ? "text-emerald-700 font-medium"
                    : r.status === "rejected"
                    ? "text-red-600 font-medium"
                    : ""
                }
              >
                {r.status}
              </span>
            ),
          },
          { key: "response_notes", header: "처리메모" },
          {
            key: "_act",
            header: "관리",
            sortable: false,
            render: (r) =>
              isAdmin && r.status === "pending" ? (
                <div className="flex gap-2">
                  <button
                    onClick={() => complete(r.id)}
                    className="text-emerald-700 text-xs hover:underline"
                  >
                    완료
                  </button>
                  <button
                    onClick={() => reject(r.id)}
                    className="text-red-600 text-xs hover:underline"
                  >
                    반려
                  </button>
                </div>
              ) : null,
          },
        ]}
        rows={rows}
      />

      {/* Access bundle / erasure (admin) */}
      {isAdmin && (
        <div className="mt-6 bg-white p-4 rounded-lg border border-slate-200">
          <h2 className="text-lg font-medium mb-2">정보주체 PII 조회 / 삭제</h2>
          <div className="flex gap-2 mb-3 flex-wrap">
            <input
              type="email"
              placeholder="이메일"
              value={bundleEmail}
              onChange={(e) => setBundleEmail(e.target.value)}
              className="border rounded px-2 py-1 flex-1 min-w-[200px]"
            />
            <button
              onClick={fetchBundle}
              className="bg-blue-700 text-white px-3 py-1 rounded text-sm"
            >
              데이터 조회
            </button>
            <button
              onClick={eraseUser}
              className="bg-red-600 text-white px-3 py-1 rounded text-sm"
            >
              익명화 처리
            </button>
          </div>
          {bundle && (
            <pre className="bg-slate-50 p-3 rounded text-xs overflow-auto">
              {JSON.stringify(bundle, null, 2)}
            </pre>
          )}
        </div>
      )}
    </AppShell>
  );
}
