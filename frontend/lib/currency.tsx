"use client";
import { createContext, useContext, useEffect, useState, ReactNode } from "react";
import { api } from "./api";

export type Currency = {
  id: number;
  code: string;
  name: string;
  symbol: string;
  is_base: boolean;
};

const Ctx = createContext<{
  base: Currency | null;
  current: Currency | null;
  list: Currency[];
  setCurrent: (c: Currency) => void;
  format: (amount: number) => string;
  rate: number; // current/base
}>({
  base: null,
  current: null,
  list: [],
  setCurrent: () => {},
  format: (n) => n.toLocaleString(),
  rate: 1,
});

export function CurrencyProvider({ children }: { children: ReactNode }) {
  const [list, setList] = useState<Currency[]>([]);
  const [base, setBase] = useState<Currency | null>(null);
  const [current, setCurrentState] = useState<Currency | null>(null);
  const [rate, setRate] = useState(1);

  useEffect(() => {
    api<Currency[]>("/api/currencies")
      .then((cs) => {
        setList(cs);
        const b = cs.find((c) => c.is_base) || cs[0] || null;
        setBase(b);
        const savedCode = typeof window !== "undefined" && localStorage.getItem("erp_currency");
        const initial = cs.find((c) => c.code === savedCode) || b;
        if (initial) setCurrentState(initial);
      })
      .catch(() => {});
  }, []);

  useEffect(() => {
    if (!base || !current) return;
    if (current.id === base.id) {
      setRate(1);
      return;
    }
    api<{ converted: string; rate_used: string }>(
      `/api/currencies/convert?amount=1&from=${base.code}&to=${current.code}`
    )
      .then((r) => setRate(Number(r.converted)))
      .catch(() => setRate(1));
  }, [base?.id, current?.id]);

  const setCurrent = (c: Currency) => {
    setCurrentState(c);
    localStorage.setItem("erp_currency", c.code);
  };

  const format = (amount: number) => {
    const v = (amount || 0) * rate;
    const s = current?.symbol || "";
    return `${s}${v.toLocaleString(undefined, { maximumFractionDigits: 2 })} ${current?.code ?? ""}`.trim();
  };

  return (
    <Ctx.Provider value={{ base, current, list, setCurrent, format, rate }}>
      {children}
    </Ctx.Provider>
  );
}

export function useCurrency() {
  return useContext(Ctx);
}
