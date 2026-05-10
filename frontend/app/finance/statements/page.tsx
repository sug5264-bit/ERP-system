"use client";
import { useState } from "react";
import AppShell from "@/components/AppShell";
import { api } from "@/lib/api";

type BS = {
  as_of: string;
  assets: { items: { code: string; name: string; balance: number }[]; total: number };
  liabilities: { items: any[]; total: number };
  equity: { items: any[]; total: number };
  total_liab_eq: number;
  balanced: boolean;
};

type CF = {
  operating: number;
  investing: number;
  financing: number;
  net_change: number;
};

type VAT = {
  sales: { supply_amount: number; vat_amount: number; invoice_count: number };
  purchase: { supply_amount: number; vat_amount: number; invoice_count: number };
  payable_or_refund: number;
  is_refund: boolean;
};

export default function StatementsPage() {
  const [tab, setTab] = useState<"bs" | "cf" | "vat">("bs");
  const [error, setError] = useState("");
  const [bs, setBs] = useState<BS | null>(null);
  const [cf, setCf] = useState<CF | null>(null);
  const [vat, setVat] = useState<VAT | null>(null);
  const [bsDate, setBsDate] = useState("");
  const [range, setRange] = useState({ start: "", end: "" });

  const runBs = async () => {
    setError("");
    try {
      const q = bsDate ? `?as_of=${bsDate}` : "";
      setBs(await api(`/api/finance/balance-sheet${q}`));
    } catch (e) {
      setError(String(e));
    }
  };
  const runCf = async () => {
    setError("");
    if (!range.start || !range.end) {
      setError("기간을 선택하세요");
      return;
    }
    try {
      setCf(
        await api(
          `/api/finance/cash-flow?start=${range.start}&end=${range.end}`
        )
      );
    } catch (e) {
      setError(String(e));
    }
  };
  const runVat = async () => {
    setError("");
    if (!range.start || !range.end) {
      setError("기간을 선택하세요");
      return;
    }
    try {
      setVat(
        await api(
          `/api/finance/vat-return?start=${range.start}&end=${range.end}`
        )
      );
    } catch (e) {
      setError(String(e));
    }
  };

  return (
    <AppShell>
      <div className="flex justify-between items-center mb-4">
        <h1 className="text-2xl font-semibold">재무제표 / 부가세</h1>
        <div className="flex gap-1">
          {(["bs", "cf", "vat"] as const).map((t) => (
            <button
              key={t}
              onClick={() => setTab(t)}
              className={`px-3 py-1 text-sm rounded ${
                tab === t
                  ? "bg-slate-900 text-white"
                  : "bg-slate-100 hover:bg-slate-200"
              }`}
            >
              {t === "bs" ? "재무상태표" : t === "cf" ? "현금흐름표" : "부가세 신고"}
            </button>
          ))}
        </div>
      </div>
      {error && <p className="text-red-600 text-sm mb-3">{error}</p>}

      {tab === "bs" && (
        <>
          <div className="bg-white p-4 rounded-lg border border-slate-200 mb-4 flex gap-2">
            <input
              type="date"
              value={bsDate}
              onChange={(e) => setBsDate(e.target.value)}
              className="border rounded px-2 py-1"
            />
            <button
              onClick={runBs}
              className="bg-emerald-700 text-white px-3 py-1 rounded text-sm"
            >
              조회
            </button>
          </div>
          {bs && (
            <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
              <BSColumn title="자산" data={bs.assets} color="text-blue-700" />
              <BSColumn title="부채" data={bs.liabilities} color="text-red-600" />
              <BSColumn title="자본" data={bs.equity} color="text-emerald-700" />
              <div className="md:col-span-3 text-sm">
                {bs.balanced ? (
                  <span className="text-emerald-700">
                    ✓ 자산 총액과 부채+자본 총액이 일치
                  </span>
                ) : (
                  <span className="text-red-600">
                    ✗ 불일치: {bs.assets.total} vs {bs.total_liab_eq}
                  </span>
                )}
              </div>
            </div>
          )}
        </>
      )}

      {tab === "cf" && (
        <>
          <div className="bg-white p-4 rounded-lg border border-slate-200 mb-4 flex gap-2 flex-wrap">
            <input
              type="date"
              value={range.start}
              onChange={(e) => setRange({ ...range, start: e.target.value })}
              className="border rounded px-2 py-1"
            />
            <span className="self-center">~</span>
            <input
              type="date"
              value={range.end}
              onChange={(e) => setRange({ ...range, end: e.target.value })}
              className="border rounded px-2 py-1"
            />
            <button
              onClick={runCf}
              className="bg-emerald-700 text-white px-3 py-1 rounded text-sm"
            >
              조회
            </button>
          </div>
          {cf && (
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-center">
              <Stat label="영업활동" value={cf.operating} color="text-blue-700" />
              <Stat label="투자활동" value={cf.investing} color="text-amber-700" />
              <Stat label="재무활동" value={cf.financing} color="text-purple-700" />
              <Stat
                label="현금 순증감"
                value={cf.net_change}
                color={cf.net_change >= 0 ? "text-emerald-700" : "text-red-600"}
              />
            </div>
          )}
        </>
      )}

      {tab === "vat" && (
        <>
          <div className="bg-white p-4 rounded-lg border border-slate-200 mb-4 flex gap-2 flex-wrap">
            <input
              type="date"
              value={range.start}
              onChange={(e) => setRange({ ...range, start: e.target.value })}
              className="border rounded px-2 py-1"
            />
            <span className="self-center">~</span>
            <input
              type="date"
              value={range.end}
              onChange={(e) => setRange({ ...range, end: e.target.value })}
              className="border rounded px-2 py-1"
            />
            <button
              onClick={runVat}
              className="bg-emerald-700 text-white px-3 py-1 rounded text-sm"
            >
              부가세 신고서 생성
            </button>
          </div>
          {vat && (
            <div className="bg-white p-4 rounded-lg border border-slate-200">
              <table className="w-full text-sm">
                <thead className="bg-slate-100">
                  <tr>
                    <th className="px-2 py-2 text-left">구분</th>
                    <th className="px-2 py-2 text-right">건수</th>
                    <th className="px-2 py-2 text-right">공급가액</th>
                    <th className="px-2 py-2 text-right">세액</th>
                  </tr>
                </thead>
                <tbody>
                  <tr className="border-t">
                    <td className="px-2 py-2">매출 (output)</td>
                    <td className="px-2 py-2 text-right">
                      {vat.sales.invoice_count}
                    </td>
                    <td className="px-2 py-2 text-right">
                      {vat.sales.supply_amount.toLocaleString()}
                    </td>
                    <td className="px-2 py-2 text-right text-emerald-700">
                      {vat.sales.vat_amount.toLocaleString()}
                    </td>
                  </tr>
                  <tr className="border-t">
                    <td className="px-2 py-2">매입 (input)</td>
                    <td className="px-2 py-2 text-right">
                      {vat.purchase.invoice_count}
                    </td>
                    <td className="px-2 py-2 text-right">
                      {vat.purchase.supply_amount.toLocaleString()}
                    </td>
                    <td className="px-2 py-2 text-right text-red-600">
                      {vat.purchase.vat_amount.toLocaleString()}
                    </td>
                  </tr>
                  <tr className="border-t bg-slate-50 font-semibold">
                    <td className="px-2 py-2" colSpan={3}>
                      {vat.is_refund ? "환급세액" : "납부세액"}
                    </td>
                    <td className="px-2 py-2 text-right text-lg">
                      {Math.abs(vat.payable_or_refund).toLocaleString()}
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
    </AppShell>
  );
}

function BSColumn({
  title,
  data,
  color,
}: {
  title: string;
  data: { items: { code: string; name: string; balance: number }[]; total: number };
  color: string;
}) {
  return (
    <div className="bg-white border border-slate-200 rounded-lg p-3">
      <h2 className="text-base font-medium mb-2">{title}</h2>
      <ul className="text-sm space-y-1">
        {data.items.map((it) => (
          <li key={it.code} className="flex justify-between">
            <span className="text-slate-600">
              {it.code} {it.name}
            </span>
            <span>{it.balance.toLocaleString()}</span>
          </li>
        ))}
      </ul>
      <div className={`mt-2 pt-2 border-t flex justify-between font-semibold ${color}`}>
        <span>합계</span>
        <span>{data.total.toLocaleString()}</span>
      </div>
    </div>
  );
}

function Stat({
  label,
  value,
  color,
}: {
  label: string;
  value: number;
  color?: string;
}) {
  return (
    <div className="bg-white border border-slate-200 rounded-lg p-4">
      <div className="text-xs text-slate-500">{label}</div>
      <div className={`text-lg font-semibold ${color ?? ""}`}>
        {value.toLocaleString()}
      </div>
    </div>
  );
}
