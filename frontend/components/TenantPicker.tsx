"use client";
import { useTenant } from "@/lib/tenant";

export default function TenantPicker() {
  const { list, current, setCurrent } = useTenant();
  if (list.length === 0) return null;
  return (
    <select
      value={current?.id ?? ""}
      onChange={(e) => {
        const next = list.find((t) => String(t.id) === e.target.value) || null;
        setCurrent(next);
        // Reload so all queries pick up the new X-Tenant-ID header.
        window.location.reload();
      }}
      className="border border-slate-300 rounded px-2 py-1 text-sm bg-white"
      title="Active tenant"
    >
      {list.map((t) => (
        <option key={t.id} value={t.id}>
          🏢 {t.name}
        </option>
      ))}
    </select>
  );
}
