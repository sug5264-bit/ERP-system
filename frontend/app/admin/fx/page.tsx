"use client";
import { useEffect, useState } from "react";
import AppShell from "@/components/AppShell";
import DataTable from "@/components/DataTable";
import { api } from "@/lib/api";
import { hasRole, useMe } from "@/lib/auth";

type Rate = {
  id: number;
  date: string;
  from_ccy: string;
  to_ccy: string;
  rate: string;
};

export default function FxPage() {
  const me = useMe();
  const isAdmin = hasRole(me, "admin");
  const [rows, setRows] = useState<Rate[]>([]);
  const [filter, setFilter] = useState({ from: "", to: "" });
  const [error, setError] = useState("");
  const [conv, setConv] = useState<any>(null);
  const [convForm, setConvForm] = useState({
    amount: "100",
    from_ccy: "USD",
    to_ccy: "KRW",
    as_of: "",
  });
  const [form, setForm] = useState({
    date: "",
    from_ccy: "USD",
    to_ccy: "KRW",
    rate: "",
  });

  const load = async () => {
    try {
      const params = new URLSearchParams();
      if (filter.from) params.set("from_ccy", filter.from);
      if (filter.to) params.set("to_ccy", filter.to);
      const q = params.toString() ? `?${params}` : "";
      setRows(await api<Rate[]>(`/api/fx/rates${q}`));
    } catch (e) {
      setError(String(e));
    }
  };
  useEffect(() => {
    load();
  }, [filter]);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    try {
      await api("/api/fx/rates", {
        method: "POST",
        body: JSON.stringify({
          date: form.date,
          from_ccy: form.from_ccy,
          to_ccy: form.to_ccy,
          rate: Number(form.rate),
        }),
      });
      setForm({ ...form, rate: "" });
      await load();
    } catch (e) {
      setError(String(e));
    }
  };

  const convertNow = async () => {
    setError("");
    try {
      const params = new URLSearchParams({
        amount: convForm.amount,
        from_ccy: convForm.from_ccy,
        to_ccy: convForm.to_ccy,
      });
      if (convForm.as_of) params.set("as_of", convForm.as_of);
      setConv(await api(`/api/fx/convert?${params}`));
    } catch (e) {
      setError(String(e));
    }
  };

  return (
    <AppShell>
      <h1 className="text-2xl font-semibold mb-4">환율 / FX</h1>
      {error && <p className="text-red-600 text-sm mb-3">{error}</p>}

      {/* Convert */}
      <div className="bg-white p-4 rounded-lg border border-slate-200 mb-4">
        <h2 className="text-base font-medium mb-2">환산 계산기</h2>
        <div className="grid grid-cols-1 md:grid-cols-5 gap-2">
          <input
            type="number"
            placeholder="금액"
            value={convForm.amount}
            onChange={(e) => setConvForm({ ...convForm, amount: e.target.value })}
            className="border rounded px-2 py-1"
          />
          <input
            placeholder="From (USD)"
            value={convForm.from_ccy}
            onChange={(e) =>
              setConvForm({ ...convForm, from_ccy: e.target.value.toUpperCase() })
            }
            className="border rounded px-2 py-1"
          />
          <input
            placeholder="To (KRW)"
            value={convForm.to_ccy}
            onChange={(e) =>
              setConvForm({ ...convForm, to_ccy: e.target.value.toUpperCase() })
            }
            className="border rounded px-2 py-1"
          />
          <input
            type="date"
            value={convForm.as_of}
            onChange={(e) => setConvForm({ ...convForm, as_of: e.target.value })}
            className="border rounded px-2 py-1"
          />
          <button
            onClick={convertNow}
            className="bg-emerald-700 text-white rounded text-sm"
          >
            환산
          </button>
        </div>
        {conv && (
          <p className="mt-2 text-sm">
            {conv.amount.toLocaleString()} {conv.from_ccy} ={" "}
            <span className="font-semibold">
              {conv.result.toLocaleString()} {conv.to_ccy}
            </span>{" "}
            <span className="text-slate-500">
              (rate {conv.rate} · {conv.as_of})
            </span>
          </p>
        )}
      </div>

      {/* Add rate (admin) */}
      {isAdmin && (
        <form
          onSubmit={submit}
          className="bg-white p-4 rounded-lg border border-slate-200 grid grid-cols-1 md:grid-cols-5 gap-2 mb-4"
        >
          <input
            required
            type="date"
            value={form.date}
            onChange={(e) => setForm({ ...form, date: e.target.value })}
            className="border rounded px-2 py-1"
          />
          <input
            required
            placeholder="From"
            value={form.from_ccy}
            onChange={(e) =>
              setForm({ ...form, from_ccy: e.target.value.toUpperCase() })
            }
            className="border rounded px-2 py-1"
          />
          <input
            required
            placeholder="To"
            value={form.to_ccy}
            onChange={(e) =>
              setForm({ ...form, to_ccy: e.target.value.toUpperCase() })
            }
            className="border rounded px-2 py-1"
          />
          <input
            required
            type="number"
            step="0.0001"
            placeholder="환율"
            value={form.rate}
            onChange={(e) => setForm({ ...form, rate: e.target.value })}
            className="border rounded px-2 py-1"
          />
          <button className="bg-slate-900 text-white rounded">+ 환율 등록</button>
        </form>
      )}

      <div className="flex gap-2 mb-2">
        <input
          placeholder="From 필터"
          value={filter.from}
          onChange={(e) => setFilter({ ...filter, from: e.target.value.toUpperCase() })}
          className="border rounded px-2 py-1"
        />
        <input
          placeholder="To 필터"
          value={filter.to}
          onChange={(e) => setFilter({ ...filter, to: e.target.value.toUpperCase() })}
          className="border rounded px-2 py-1"
        />
      </div>

      <DataTable<Rate>
        columns={[
          { key: "date", header: "일자" },
          { key: "from_ccy", header: "From" },
          { key: "to_ccy", header: "To" },
          {
            key: "rate",
            header: "Rate",
            render: (r) => Number(r.rate).toLocaleString(),
          },
        ]}
        rows={rows}
      />
    </AppShell>
  );
}
