"use client";
import { useEffect, useState } from "react";
import AppShell from "@/components/AppShell";
import DataTable from "@/components/DataTable";
import { api } from "@/lib/api";

type Account = { id: number; code: string; name: string; type: string };
type JournalEntry = {
  id: number;
  entry_date: string;
  description: string;
  reference: string | null;
  lines: { id: number; account_id: number; debit: string; credit: string }[];
};

export default function FinancePage() {
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [entries, setEntries] = useState<JournalEntry[]>([]);
  const [error, setError] = useState("");

  const load = async () => {
    const [a, e] = await Promise.all([
      api<Account[]>("/api/finance/accounts"),
      api<JournalEntry[]>("/api/finance/journal-entries"),
    ]);
    setAccounts(a);
    setEntries(e);
  };

  useEffect(() => {
    load().catch((e) => setError(String(e)));
  }, []);

  return (
    <AppShell>
      <h1 className="text-2xl font-semibold mb-4">재무 / 회계</h1>
      {error && <p className="text-red-600 text-sm mb-3">{error}</p>}

      <h2 className="text-lg font-medium mb-2">계정과목</h2>
      <div className="mb-6">
        <DataTable<Account>
          columns={[
            { key: "code", header: "코드" },
            { key: "name", header: "계정명" },
            { key: "type", header: "유형" },
          ]}
          rows={accounts}
        />
      </div>

      <h2 className="text-lg font-medium mb-2">분개 전표</h2>
      <DataTable<JournalEntry>
        columns={[
          { key: "entry_date", header: "일자" },
          { key: "description", header: "내용" },
          { key: "reference", header: "참조" },
          {
            key: "total",
            header: "차변 합계",
            render: (r) =>
              r.lines.reduce((s, l) => s + Number(l.debit), 0).toLocaleString(),
          },
        ]}
        rows={entries}
        empty="아직 전표가 없습니다"
      />
    </AppShell>
  );
}
