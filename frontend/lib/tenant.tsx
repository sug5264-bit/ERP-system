"use client";
import { createContext, useContext, useEffect, useState, ReactNode } from "react";
import { api } from "./api";

export type Tenant = {
  id: number;
  code: string;
  name: string;
  description: string | null;
};

const Ctx = createContext<{
  list: Tenant[];
  current: Tenant | null;
  setCurrent: (t: Tenant | null) => void;
}>({
  list: [],
  current: null,
  setCurrent: () => {},
});

export function TenantProvider({ children }: { children: ReactNode }) {
  const [list, setList] = useState<Tenant[]>([]);
  const [current, setCurrentState] = useState<Tenant | null>(null);

  useEffect(() => {
    api<Tenant[]>("/api/tenants/me")
      .then((ts) => {
        setList(ts);
        const saved = typeof window !== "undefined" && localStorage.getItem("erp_tenant_id");
        const initial = ts.find((t) => String(t.id) === saved) || ts[0] || null;
        setCurrentState(initial);
      })
      .catch(() => {});
  }, []);

  const setCurrent = (t: Tenant | null) => {
    setCurrentState(t);
    if (t) localStorage.setItem("erp_tenant_id", String(t.id));
    else localStorage.removeItem("erp_tenant_id");
  };

  return <Ctx.Provider value={{ list, current, setCurrent }}>{children}</Ctx.Provider>;
}

export function useTenant() {
  return useContext(Ctx);
}
