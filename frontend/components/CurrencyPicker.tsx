"use client";
import { useCurrency } from "@/lib/currency";

export default function CurrencyPicker() {
  const { list, current, setCurrent } = useCurrency();
  if (list.length === 0) return null;
  return (
    <select
      value={current?.code ?? ""}
      onChange={(e) => {
        const next = list.find((c) => c.code === e.target.value);
        if (next) setCurrent(next);
      }}
      className="border border-slate-300 rounded px-2 py-1 text-sm bg-white"
      title="Display currency"
    >
      {list.map((c) => (
        <option key={c.code} value={c.code}>
          {c.symbol || c.code} {c.code}
          {c.is_base ? " (base)" : ""}
        </option>
      ))}
    </select>
  );
}
