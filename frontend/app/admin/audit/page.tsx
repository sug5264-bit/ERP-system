"use client";
import { useEffect, useState } from "react";
import AppShell from "@/components/AppShell";
import DataTable from "@/components/DataTable";
import ExportMenu from "@/components/ExportMenu";
import { api } from "@/lib/api";
import { useT } from "@/lib/i18n";

type Log = {
  id: number;
  user_email: string | null;
  method: string;
  path: string;
  status_code: number;
  ip: string | null;
  payload: string | null;
  created_at: string;
};

const METHODS = ["", "POST", "PATCH", "PUT", "DELETE"];

export default function AuditLogPage() {
  const { t } = useT();
  const [logs, setLogs] = useState<Log[]>([]);
  const [error, setError] = useState("");
  const [filters, setFilters] = useState({
    user_email: "",
    method: "",
    path: "",
    status_code: "",
  });

  const buildQuery = () => {
    const p = new URLSearchParams({ size: "200" });
    if (filters.user_email) p.append("user_email", filters.user_email);
    if (filters.method) p.append("method", filters.method);
    if (filters.path) p.append("path", filters.path);
    if (filters.status_code) p.append("status_code", filters.status_code);
    return p.toString();
  };

  const load = () =>
    api<{ items: Log[] }>(`/api/audit/logs?${buildQuery()}`)
      .then((r) => setLogs(r.items))
      .catch((e) => setError(String(e)));

  useEffect(() => {
    load();
  }, []);

  return (
    <AppShell>
      <div className="flex justify-between items-center mb-4">
        <h1 className="text-2xl font-semibold">{t("nav.admin.audit")}</h1>
        <ExportMenu endpoint="/api/audit/logs/export" filename="audit_logs" />
      </div>

      <form
        onSubmit={(e) => {
          e.preventDefault();
          load();
        }}
        className="bg-white p-3 rounded-lg shadow-sm border border-slate-200 grid grid-cols-2 md:grid-cols-5 gap-2 mb-4"
      >
        <input
          placeholder="user email"
          value={filters.user_email}
          onChange={(e) => setFilters({ ...filters, user_email: e.target.value })}
          className="border rounded px-2 py-1 text-sm"
        />
        <select
          value={filters.method}
          onChange={(e) => setFilters({ ...filters, method: e.target.value })}
          className="border rounded px-2 py-1 text-sm"
        >
          {METHODS.map((m) => (
            <option key={m} value={m}>
              {m || "method"}
            </option>
          ))}
        </select>
        <input
          placeholder="path contains"
          value={filters.path}
          onChange={(e) => setFilters({ ...filters, path: e.target.value })}
          className="border rounded px-2 py-1 text-sm"
        />
        <input
          placeholder="status code"
          value={filters.status_code}
          onChange={(e) => setFilters({ ...filters, status_code: e.target.value })}
          className="border rounded px-2 py-1 text-sm"
        />
        <div className="flex gap-2">
          <button className="px-3 py-1 bg-slate-900 text-white rounded text-sm">검색</button>
          <button
            type="button"
            onClick={() => {
              setFilters({ user_email: "", method: "", path: "", status_code: "" });
              api<{ items: Log[] }>("/api/audit/logs?size=200").then((r) => setLogs(r.items));
            }}
            className="px-3 py-1 border rounded text-sm"
          >
            초기화
          </button>
        </div>
      </form>

      {error && <p className="text-red-600 text-sm mb-3">{error}</p>}

      <DataTable<Log>
        columns={[
          {
            key: "created_at",
            header: "Time",
            render: (l) => new Date(l.created_at).toLocaleString(),
          },
          { key: "user_email", header: "User" },
          {
            key: "method",
            header: "Method",
            render: (l) => (
              <span
                className={`px-2 py-0.5 rounded text-xs font-mono ${
                  l.method === "DELETE"
                    ? "bg-red-100 text-red-700"
                    : l.method === "POST"
                    ? "bg-green-100 text-green-700"
                    : "bg-slate-100 text-slate-700"
                }`}
              >
                {l.method}
              </span>
            ),
          },
          { key: "path", header: "Path" },
          {
            key: "status_code",
            header: "Status",
            render: (l) => (
              <span
                className={
                  l.status_code >= 400 ? "text-red-600 font-medium" : "text-slate-700"
                }
              >
                {l.status_code}
              </span>
            ),
          },
          { key: "ip", header: "IP" },
          {
            key: "payload",
            header: "Payload",
            render: (l) =>
              l.payload ? (
                <code className="text-xs text-slate-600 truncate block max-w-xs" title={l.payload}>
                  {l.payload.slice(0, 80)}
                  {l.payload.length > 80 ? "..." : ""}
                </code>
              ) : (
                "-"
              ),
          },
        ]}
        rows={logs}
        empty={t("common.empty")}
      />
    </AppShell>
  );
}
