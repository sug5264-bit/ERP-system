"use client";
import { useEffect, useState } from "react";
import AppShell from "@/components/AppShell";
import DataTable from "@/components/DataTable";
import { api } from "@/lib/api";

type Account = { id: number; code: string; name: string; type: string };
type Line = { id: number; account_id: number; debit: string; credit: string; memo: string | null };
type JournalEntry = {
  id: number;
  entry_date: string;
  description: string;
  reference: string | null;
  lines: Line[];
};

type LineDraft = { account_id: string; debit: string; credit: string; memo: string };

const emptyLine: LineDraft = { account_id: "", debit: "0", credit: "0", memo: "" };

export default function FinancePage() {
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [entries, setEntries] = useState<JournalEntry[]>([]);
  const [error, setError] = useState("");

  const [description, setDescription] = useState("");
  const [reference, setReference] = useState("");
  const [lines, setLines] = useState<LineDraft[]>([{ ...emptyLine }, { ...emptyLine }]);

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

  const totalDebit = lines.reduce((s, l) => s + Number(l.debit || 0), 0);
  const totalCredit = lines.reduce((s, l) => s + Number(l.credit || 0), 0);
  const balanced = totalDebit === totalCredit && totalDebit > 0;

  const updateLine = (idx: number, patch: Partial<LineDraft>) =>
    setLines((prev) => prev.map((l, i) => (i === idx ? { ...l, ...patch } : l)));

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    if (!balanced) {
      setError("차변 합계와 대변 합계가 일치해야 합니다.");
      return;
    }
    try {
      await api("/api/finance/journal-entries", {
        method: "POST",
        body: JSON.stringify({
          description,
          reference: reference || null,
          lines: lines
            .filter((l) => l.account_id)
            .map((l) => ({
              account_id: Number(l.account_id),
              debit: Number(l.debit || 0),
              credit: Number(l.credit || 0),
              memo: l.memo || null,
            })),
        }),
      });
      setDescription("");
      setReference("");
      setLines([{ ...emptyLine }, { ...emptyLine }]);
      await load();
    } catch (e) {
      setError(String(e));
    }
  };

  return (
    <AppShell>
      <h1 className="text-2xl font-semibold mb-4">재무 / 회계</h1>
      {error && <p className="text-red-600 text-sm mb-3">{error}</p>}

      <h2 className="text-lg font-medium mb-2">전표 입력</h2>
      <form
        onSubmit={submit}
        className="bg-white p-4 rounded-lg shadow-sm border border-slate-200 mb-6 space-y-3"
      >
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          <input
            required
            placeholder="내용 (예: 12월 사무실 임대료 지급)"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            className="border rounded px-2 py-1"
          />
          <input
            placeholder="참조번호 (선택)"
            value={reference}
            onChange={(e) => setReference(e.target.value)}
            className="border rounded px-2 py-1"
          />
        </div>

        <table className="w-full text-sm">
          <thead className="bg-slate-100">
            <tr>
              <th className="text-left px-2 py-1">계정과목</th>
              <th className="text-right px-2 py-1">차변</th>
              <th className="text-right px-2 py-1">대변</th>
              <th className="text-left px-2 py-1">적요</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {lines.map((line, idx) => (
              <tr key={idx}>
                <td className="px-2 py-1">
                  <select
                    value={line.account_id}
                    onChange={(e) => updateLine(idx, { account_id: e.target.value })}
                    className="border rounded px-2 py-1 w-full"
                  >
                    <option value="">선택</option>
                    {accounts.map((a) => (
                      <option key={a.id} value={a.id}>
                        {a.code} - {a.name}
                      </option>
                    ))}
                  </select>
                </td>
                <td className="px-2 py-1">
                  <input
                    type="number"
                    value={line.debit}
                    onChange={(e) => updateLine(idx, { debit: e.target.value })}
                    className="border rounded px-2 py-1 w-full text-right"
                  />
                </td>
                <td className="px-2 py-1">
                  <input
                    type="number"
                    value={line.credit}
                    onChange={(e) => updateLine(idx, { credit: e.target.value })}
                    className="border rounded px-2 py-1 w-full text-right"
                  />
                </td>
                <td className="px-2 py-1">
                  <input
                    value={line.memo}
                    onChange={(e) => updateLine(idx, { memo: e.target.value })}
                    className="border rounded px-2 py-1 w-full"
                  />
                </td>
                <td className="px-2 py-1">
                  {lines.length > 2 && (
                    <button
                      type="button"
                      onClick={() => setLines(lines.filter((_, i) => i !== idx))}
                      className="text-red-600 text-xs"
                    >
                      삭제
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
          <tfoot>
            <tr className="font-medium border-t">
              <td className="px-2 py-1 text-right">합계</td>
              <td className="px-2 py-1 text-right">{totalDebit.toLocaleString()}</td>
              <td className="px-2 py-1 text-right">{totalCredit.toLocaleString()}</td>
              <td colSpan={2}>
                {!balanced && totalDebit + totalCredit > 0 && (
                  <span className="text-red-600 text-xs ml-2">차/대변 불일치</span>
                )}
              </td>
            </tr>
          </tfoot>
        </table>

        <div className="flex gap-2">
          <button
            type="button"
            onClick={() => setLines([...lines, { ...emptyLine }])}
            className="px-3 py-1 border rounded text-sm"
          >
            + 라인 추가
          </button>
          <button
            type="submit"
            disabled={!balanced}
            className="px-4 py-1 bg-slate-900 text-white rounded disabled:opacity-50"
          >
            전표 저장
          </button>
        </div>
      </form>

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

      <h2 className="text-lg font-medium mb-2">분개 전표 ({entries.length})</h2>
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
