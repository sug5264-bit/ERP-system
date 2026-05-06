"use client";
import { useEffect, useState } from "react";
import AppShell from "@/components/AppShell";
import DataTable from "@/components/DataTable";
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

export default function AuditLogPage() {
  const { t } = useT();
  const [logs, setLogs] = useState<Log[]>([]);
  const [error, setError] = useState("");

  useEffect(() => {
    api<Log[]>("/api/audit/logs?limit=200")
      .then(setLogs)
      .catch((e) => setError(String(e)));
  }, []);

  return (
    <AppShell>
      <h1 className="text-2xl font-semibold mb-4">{t("nav.admin.audit")}</h1>
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
