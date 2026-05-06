"use client";
import { useEffect, useState } from "react";
import AppShell from "@/components/AppShell";
import DataTable from "@/components/DataTable";
import { api } from "@/lib/api";

type ApiKey = {
  id: number;
  name: string;
  prefix: string;
  revoked: boolean;
  rate_per_minute: number;
  last_used_at: string | null;
  created_at: string;
};

export default function ApiKeysPage() {
  const [keys, setKeys] = useState<ApiKey[]>([]);
  const [name, setName] = useState("");
  const [rate, setRate] = useState(60);
  const [error, setError] = useState("");
  const [created, setCreated] = useState<string | null>(null);

  const load = () =>
    api<ApiKey[]>("/api/auth/api-keys")
      .then(setKeys)
      .catch((e) => setError(String(e)));

  useEffect(() => {
    load();
  }, []);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setCreated(null);
    try {
      const res = await api<{ key: string }>(
        `/api/auth/api-keys?name=${encodeURIComponent(name)}&rate_per_minute=${rate}`,
        { method: "POST" }
      );
      setCreated(res.key);
      setName("");
      await load();
    } catch (e) {
      setError(String(e));
    }
  };

  const revoke = async (id: number) => {
    if (!confirm("이 키를 폐기하시겠습니까?")) return;
    await api(`/api/auth/api-keys/${id}`, { method: "DELETE" });
    await load();
  };

  return (
    <AppShell>
      <h1 className="text-2xl font-semibold mb-4">API 키</h1>

      <form
        onSubmit={submit}
        className="bg-white p-4 rounded-lg shadow-sm border border-slate-200 grid grid-cols-1 md:grid-cols-3 gap-3 mb-6"
      >
        <input
          required
          placeholder="이름 (예: mobile-app)"
          value={name}
          onChange={(e) => setName(e.target.value)}
          className="border rounded px-2 py-1"
        />
        <input
          type="number"
          min={1}
          value={rate}
          onChange={(e) => setRate(Number(e.target.value))}
          className="border rounded px-2 py-1"
          placeholder="분당 요청 한도"
        />
        <button className="bg-slate-900 text-white px-3 rounded">키 발급</button>
      </form>

      {error && <p className="text-red-600 text-sm mb-3">{error}</p>}
      {created && (
        <div className="mb-4 p-3 bg-amber-50 border border-amber-200 rounded text-sm">
          <p className="font-medium text-amber-900">새 키 (한 번만 표시됩니다)</p>
          <code className="block mt-1 break-all">{created}</code>
        </div>
      )}

      <DataTable<ApiKey>
        columns={[
          { key: "name", header: "이름" },
          {
            key: "prefix",
            header: "Prefix",
            render: (k) => <code className="text-xs">{k.prefix}…</code>,
          },
          { key: "rate_per_minute", header: "한도/분" },
          {
            key: "last_used_at",
            header: "마지막 사용",
            render: (k) =>
              k.last_used_at ? new Date(k.last_used_at).toLocaleString() : "-",
          },
          {
            key: "revoked",
            header: "상태",
            render: (k) =>
              k.revoked ? (
                <span className="text-red-600 text-xs">폐기됨</span>
              ) : (
                <span className="text-brand-700 text-xs">활성</span>
              ),
          },
          {
            key: "actions",
            header: "",
            render: (k) =>
              !k.revoked && (
                <button
                  onClick={() => revoke(k.id)}
                  className="text-red-600 text-xs hover:underline"
                >
                  폐기
                </button>
              ),
          },
        ]}
        rows={keys}
      />

      <div className="mt-8 bg-white p-4 rounded-lg border border-slate-200 text-sm space-y-2">
        <h2 className="font-medium">사용법</h2>
        <p>
          <code>X-API-Key: &lt;key&gt;</code> 헤더로 모든 API 호출에 사용 가능 (Bearer JWT
          대신).
        </p>
        <pre className="bg-slate-100 dark:bg-slate-800 p-2 rounded text-xs overflow-x-auto">
{`curl -H "X-API-Key: wg_..." https://erp.wellgreen.com/api/inventory/items`}
        </pre>
      </div>
    </AppShell>
  );
}
