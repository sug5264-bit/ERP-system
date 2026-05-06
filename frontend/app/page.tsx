import AppShell from "@/components/AppShell";
import { MODULES } from "@/lib/modules";
import Link from "next/link";

export default function DashboardPage() {
  return (
    <AppShell>
      <h1 className="text-2xl font-semibold mb-6">대시보드</h1>
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        {MODULES.map((m) => (
          <Link
            key={m.key}
            href={m.href}
            className="bg-white p-5 rounded-lg shadow-sm border border-slate-200 hover:border-slate-400"
          >
            <div className="text-sm text-slate-500">{m.key.toUpperCase()}</div>
            <div className="text-lg font-medium mt-1">{m.label}</div>
          </Link>
        ))}
      </div>
    </AppShell>
  );
}
