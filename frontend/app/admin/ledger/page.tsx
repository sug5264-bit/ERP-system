"use client";
import { useEffect, useState } from "react";
import AppShell from "@/components/AppShell";
import DataTable from "@/components/DataTable";
import { api } from "@/lib/api";

type Entry = {
  id: number;
  seq: number;
  event_type: string;
  resource_type: string | null;
  resource_id: number | null;
  payload: any;
  prev_hash: string;
  this_hash: string;
  actor_id: number | null;
  created_at: string;
};

type Verify = {
  valid: boolean;
  entries?: number;
  tip_hash?: string;
  broken_at_seq?: number;
};

export default function LedgerPage() {
  const [entries, setEntries] = useState<Entry[]>([]);
  const [verify, setVerify] = useState<Verify | null>(null);
  const [error, setError] = useState("");

  const load = async () => {
    try {
      setEntries(await api<Entry[]>("/api/ledger?limit=200"));
      setVerify(await api<Verify>("/api/ledger/verify"));
    } catch (e) {
      setError(String(e));
    }
  };

  useEffect(() => {
    load();
  }, []);

  return (
    <AppShell>
      <div className="flex justify-between items-center mb-4">
        <h1 className="text-2xl font-semibold">공급망 레저</h1>
        {verify && (
          <span
            className={`px-3 py-1 text-sm rounded ${
              verify.valid
                ? "bg-brand-100 text-brand-800 dark:bg-brand-900 dark:text-brand-100"
                : "bg-red-100 text-red-700"
            }`}
          >
            {verify.valid
              ? `✓ 체인 검증 OK (${verify.entries}건)`
              : `✗ 체인 손상 @ seq ${verify.broken_at_seq}`}
          </span>
        )}
      </div>
      {verify?.valid && verify.tip_hash && (
        <p className="text-xs text-slate-500 mb-3">
          Tip hash: <code className="break-all">{verify.tip_hash}</code>
        </p>
      )}
      {error && <p className="text-red-600 text-sm mb-3">{error}</p>}

      <DataTable<Entry>
        columns={[
          { key: "seq", header: "Seq" },
          {
            key: "created_at",
            header: "시간",
            render: (e) => new Date(e.created_at).toLocaleString(),
          },
          { key: "event_type", header: "이벤트" },
          {
            key: "resource",
            header: "대상",
            render: (e) =>
              e.resource_type ? `${e.resource_type}#${e.resource_id}` : "-",
          },
          {
            key: "payload",
            header: "Payload",
            render: (e) => (
              <code className="text-xs text-slate-600 truncate block max-w-xs" title={JSON.stringify(e.payload)}>
                {JSON.stringify(e.payload).slice(0, 80)}
              </code>
            ),
          },
          {
            key: "this_hash",
            header: "Hash",
            render: (e) => <code className="text-xs">{e.this_hash.slice(0, 12)}…</code>,
          },
        ]}
        rows={entries}
      />
    </AppShell>
  );
}
