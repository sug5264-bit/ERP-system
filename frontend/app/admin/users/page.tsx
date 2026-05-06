"use client";
import { useEffect, useState } from "react";
import AppShell from "@/components/AppShell";
import DataTable from "@/components/DataTable";
import { api } from "@/lib/api";
import { Role } from "@/lib/auth";
import { useT } from "@/lib/i18n";

type User = {
  id: number;
  email: string;
  full_name: string;
  role: Role;
};

const ROLES: Role[] = ["admin", "manager", "staff", "viewer"];

export default function UsersAdminPage() {
  const { t } = useT();
  const [users, setUsers] = useState<User[]>([]);
  const [form, setForm] = useState({
    email: "",
    full_name: "",
    password: "",
    role: "staff" as Role,
  });
  const [error, setError] = useState("");

  const load = async () => setUsers(await api<User[]>("/api/auth/users"));

  useEffect(() => {
    load().catch((e) => setError(String(e)));
  }, []);

  const create = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    try {
      await api("/api/auth/users", {
        method: "POST",
        body: JSON.stringify(form),
      });
      setForm({ email: "", full_name: "", password: "", role: "staff" });
      await load();
    } catch (e) {
      setError(String(e));
    }
  };

  const updateRole = async (id: number, role: Role) => {
    try {
      await api(`/api/auth/users/${id}`, {
        method: "PATCH",
        body: JSON.stringify({ role }),
      });
      await load();
    } catch (e) {
      setError(String(e));
    }
  };

  const remove = async (id: number) => {
    if (!confirm("Delete this user?")) return;
    try {
      await api(`/api/auth/users/${id}`, { method: "DELETE" });
      await load();
    } catch (e) {
      setError(String(e));
    }
  };

  return (
    <AppShell>
      <h1 className="text-2xl font-semibold mb-4">{t("nav.admin.users")}</h1>

      <form
        onSubmit={create}
        className="bg-white p-4 rounded-lg shadow-sm border border-slate-200 grid grid-cols-1 md:grid-cols-5 gap-3 mb-6"
      >
        <input
          required
          type="email"
          placeholder={t("auth.email")}
          value={form.email}
          onChange={(e) => setForm({ ...form, email: e.target.value })}
          className="border rounded px-2 py-1"
        />
        <input
          required
          placeholder="Name"
          value={form.full_name}
          onChange={(e) => setForm({ ...form, full_name: e.target.value })}
          className="border rounded px-2 py-1"
        />
        <input
          required
          type="password"
          placeholder={t("auth.password")}
          value={form.password}
          onChange={(e) => setForm({ ...form, password: e.target.value })}
          className="border rounded px-2 py-1"
        />
        <select
          value={form.role}
          onChange={(e) => setForm({ ...form, role: e.target.value as Role })}
          className="border rounded px-2 py-1"
        >
          {ROLES.map((r) => (
            <option key={r} value={r}>
              {r}
            </option>
          ))}
        </select>
        <button className="bg-slate-900 text-white px-3 rounded">{t("common.add")}</button>
      </form>

      {error && <p className="text-red-600 text-sm mb-3">{error}</p>}

      <DataTable<User>
        columns={[
          { key: "id", header: "ID" },
          { key: "email", header: t("auth.email") },
          { key: "full_name", header: "Name" },
          {
            key: "role",
            header: t("auth.role"),
            render: (u) => (
              <select
                value={u.role}
                onChange={(e) => updateRole(u.id, e.target.value as Role)}
                className="border rounded px-2 py-1 text-sm"
              >
                {ROLES.map((r) => (
                  <option key={r} value={r}>
                    {r}
                  </option>
                ))}
              </select>
            ),
          },
          {
            key: "actions",
            header: t("common.actions"),
            render: (u) => (
              <button
                onClick={() => remove(u.id)}
                className="text-red-600 text-xs hover:underline"
              >
                {t("common.delete")}
              </button>
            ),
          },
        ]}
        rows={users}
      />
    </AppShell>
  );
}
