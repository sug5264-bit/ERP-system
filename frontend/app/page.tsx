"use client";
import { useEffect, useState } from "react";
import AppShell from "@/components/AppShell";
import { BarChart, PieChart } from "@/components/charts";
import { api } from "@/lib/api";
import { useT } from "@/lib/i18n";

type Summary = {
  employees: number;
  items: number;
  low_stock: number;
  orders: number;
  open_orders: number;
  total_sales: number;
};

type SalesPoint = { month: string; total: number };
type DeptCount = { department: string; count: number };
type TopItem = { sku: string; name: string; value: number };

export default function DashboardPage() {
  const { t } = useT();
  const [summary, setSummary] = useState<Summary | null>(null);
  const [sales, setSales] = useState<SalesPoint[]>([]);
  const [depts, setDepts] = useState<DeptCount[]>([]);
  const [topItems, setTopItems] = useState<TopItem[]>([]);

  useEffect(() => {
    Promise.all([
      api<Summary>("/api/reports/summary"),
      api<SalesPoint[]>("/api/reports/sales-by-month"),
      api<DeptCount[]>("/api/reports/employees-by-department"),
      api<TopItem[]>("/api/reports/top-items"),
    ])
      .then(([s, sa, d, ti]) => {
        setSummary(s);
        setSales(sa);
        setDepts(d);
        setTopItems(ti);
      })
      .catch(console.error);
  }, []);

  return (
    <AppShell>
      <h1 className="text-2xl font-semibold mb-6">{t("nav.dashboard")}</h1>

      {summary && (
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3 mb-8">
          <Stat label={t("dashboard.employees")} value={summary.employees} />
          <Stat label={t("dashboard.items")} value={summary.items} />
          <Stat
            label={t("dashboard.lowStock")}
            value={summary.low_stock}
            highlight={summary.low_stock > 0}
          />
          <Stat label={t("dashboard.orders")} value={summary.orders} />
          <Stat label={t("dashboard.openOrders")} value={summary.open_orders} />
          <Stat
            label={t("dashboard.totalSales")}
            value={summary.total_sales.toLocaleString()}
          />
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <Card title={t("dashboard.salesByMonth")}>
          <BarChart data={sales.map((s) => ({ label: s.month.slice(2), value: s.total }))} />
        </Card>
        <Card title={t("dashboard.employeesByDept")}>
          <PieChart data={depts.map((d) => ({ label: d.department, value: d.count }))} />
        </Card>
        <Card title={t("dashboard.topItems")}>
          <BarChart
            data={topItems.map((i) => ({ label: i.sku, value: i.value }))}
            format={(v) => v.toLocaleString()}
          />
        </Card>
      </div>
    </AppShell>
  );
}

function Stat({
  label,
  value,
  highlight,
}: {
  label: string;
  value: number | string;
  highlight?: boolean;
}) {
  return (
    <div
      className={`bg-white p-4 rounded-lg shadow-sm border ${
        highlight ? "border-red-300" : "border-slate-200"
      }`}
    >
      <div className="text-xs text-slate-500">{label}</div>
      <div className={`text-2xl font-semibold mt-1 ${highlight ? "text-red-600" : ""}`}>
        {value}
      </div>
    </div>
  );
}

function Card({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="bg-white p-5 rounded-lg shadow-sm border border-slate-200">
      <h2 className="text-lg font-medium mb-3">{title}</h2>
      {children}
    </div>
  );
}
