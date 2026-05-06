"use client";
import { useEffect, useState } from "react";
import AppShell from "@/components/AppShell";
import Attachments from "@/components/Attachments";
import DataTable from "@/components/DataTable";
import ExportMenu from "@/components/ExportMenu";
import { api } from "@/lib/api";
import { hasRole, useMe } from "@/lib/auth";

type Employee = {
  id: number;
  employee_no: string;
  full_name: string;
  email: string;
  position: string | null;
  salary: string;
  department: { id: number; name: string } | null;
};

export default function HRPage() {
  const me = useMe();
  const [employees, setEmployees] = useState<Employee[]>([]);
  const [form, setForm] = useState({
    employee_no: "",
    full_name: "",
    email: "",
    position: "",
    salary: "0",
  });
  const [error, setError] = useState("");
  const [attachFor, setAttachFor] = useState<Employee | null>(null);

  const load = async () => {
    setEmployees(await api<Employee[]>("/api/hr/employees"));
  };

  useEffect(() => {
    load().catch((e) => setError(String(e)));
  }, []);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    try {
      await api("/api/hr/employees", {
        method: "POST",
        body: JSON.stringify({ ...form, salary: Number(form.salary) }),
      });
      setForm({ employee_no: "", full_name: "", email: "", position: "", salary: "0" });
      await load();
    } catch (e) {
      setError(String(e));
    }
  };

  return (
    <AppShell>
      <div className="flex justify-between items-center mb-4">
        <h1 className="text-2xl font-semibold">HR / 인사</h1>
        <ExportMenu endpoint="/api/hr/employees/export" filename="employees" />
      </div>

      <form
        onSubmit={submit}
        className="bg-white p-4 rounded-lg shadow-sm border border-slate-200 grid grid-cols-1 md:grid-cols-5 gap-3 mb-6"
      >
        <input
          required
          placeholder="사번"
          value={form.employee_no}
          onChange={(e) => setForm({ ...form, employee_no: e.target.value })}
          className="border rounded px-2 py-1"
        />
        <input
          required
          placeholder="이름"
          value={form.full_name}
          onChange={(e) => setForm({ ...form, full_name: e.target.value })}
          className="border rounded px-2 py-1"
        />
        <input
          required
          type="email"
          placeholder="이메일"
          value={form.email}
          onChange={(e) => setForm({ ...form, email: e.target.value })}
          className="border rounded px-2 py-1"
        />
        <input
          placeholder="직책"
          value={form.position}
          onChange={(e) => setForm({ ...form, position: e.target.value })}
          className="border rounded px-2 py-1"
        />
        <div className="flex gap-2">
          <input
            type="number"
            placeholder="급여"
            value={form.salary}
            onChange={(e) => setForm({ ...form, salary: e.target.value })}
            className="border rounded px-2 py-1 w-full"
          />
          <button className="bg-slate-900 text-white px-3 rounded">추가</button>
        </div>
      </form>

      {error && <p className="text-red-600 text-sm mb-3">{error}</p>}

      <DataTable<Employee>
        columns={[
          { key: "employee_no", header: "사번" },
          { key: "full_name", header: "이름" },
          { key: "email", header: "이메일" },
          { key: "position", header: "직책" },
          {
            key: "department",
            header: "부서",
            render: (r) => r.department?.name ?? "-",
          },
          { key: "salary", header: "급여" },
          {
            key: "files",
            header: "첨부",
            render: (r) => (
              <button
                onClick={() => setAttachFor(r)}
                className="text-blue-700 text-xs hover:underline"
              >
                파일
              </button>
            ),
          },
        ]}
        rows={employees}
      />

      {attachFor && (
        <div className="fixed inset-0 bg-black/30 flex items-center justify-center z-30">
          <div className="bg-white rounded-lg p-6 w-96 space-y-3">
            <div className="flex justify-between items-center">
              <h2 className="text-lg font-medium">{attachFor.full_name} - 첨부파일</h2>
              <button
                onClick={() => setAttachFor(null)}
                className="text-slate-500 hover:text-slate-900"
              >
                ✕
              </button>
            </div>
            <Attachments
              relatedType="employee"
              relatedId={attachFor.id}
              canDelete={hasRole(me, "manager")}
            />
          </div>
        </div>
      )}
    </AppShell>
  );
}
