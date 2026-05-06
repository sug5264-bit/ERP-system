"use client";
import { useRef, useState } from "react";
import AppShell from "@/components/AppShell";
import { downloadFile, uploadFile } from "@/lib/api";

export default function DataAdminPage() {
  const [error, setError] = useState("");
  const [info, setInfo] = useState("");
  const [importEntity, setImportEntity] = useState<"items" | "customers" | "employees">("items");
  const [truncate, setTruncate] = useState(false);
  const importRef = useRef<HTMLInputElement>(null);
  const restoreRef = useRef<HTMLInputElement>(null);

  const onBackup = async () => {
    setError("");
    try {
      await downloadFile("/api/admin/backup", `wellgreen-backup-${new Date().toISOString().slice(0, 10)}.json`);
      setInfo("백업 다운로드 완료");
    } catch (e) {
      setError(String(e));
    }
  };

  const onRestore = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    if (!confirm(`${file.name} 으로 복원합니다. ${truncate ? "기존 데이터를 삭제합니다." : ""} 계속할까요?`)) return;
    setError("");
    setInfo("");
    try {
      const result = await uploadFile(
        `/api/admin/restore?truncate_first=${truncate}`,
        file
      );
      setInfo(JSON.stringify(result));
    } catch (e) {
      setError(String(e));
    } finally {
      if (restoreRef.current) restoreRef.current.value = "";
    }
  };

  const onImport = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setError("");
    setInfo("");
    try {
      const result = await uploadFile(`/api/admin/import?entity=${importEntity}`, file);
      setInfo(`임포트 완료: ${JSON.stringify(result)}`);
    } catch (e) {
      setError(String(e));
    } finally {
      if (importRef.current) importRef.current.value = "";
    }
  };

  return (
    <AppShell>
      <h1 className="text-2xl font-semibold mb-4">백업 & 임포트</h1>

      {error && <p className="text-red-600 text-sm mb-3">{error}</p>}
      {info && <p className="text-brand-700 text-sm mb-3">{info}</p>}

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <Card title="전체 백업">
          <p className="text-sm text-slate-600 mb-3">
            모든 테이블을 JSON으로 내려받습니다.
          </p>
          <button
            onClick={onBackup}
            className="px-4 py-2 bg-brand-700 text-white rounded text-sm"
          >
            백업 다운로드
          </button>
        </Card>

        <Card title="복원">
          <p className="text-sm text-slate-600 mb-3">
            JSON 백업 파일을 업로드하여 복원합니다.
          </p>
          <label className="flex items-center gap-2 text-sm mb-3">
            <input
              type="checkbox"
              checked={truncate}
              onChange={(e) => setTruncate(e.target.checked)}
            />
            기존 데이터 삭제 후 복원
          </label>
          <input
            ref={restoreRef}
            type="file"
            accept=".json"
            onChange={onRestore}
            className="block text-sm"
          />
        </Card>

        <Card title="Excel 임포트">
          <p className="text-sm text-slate-600 mb-3">
            첫 행이 헤더인 .xlsx 파일을 업로드합니다.
          </p>
          <select
            value={importEntity}
            onChange={(e) => setImportEntity(e.target.value as any)}
            className="border rounded px-2 py-1 text-sm mb-3 w-full"
          >
            <option value="items">품목 (items)</option>
            <option value="customers">고객 (customers)</option>
            <option value="employees">직원 (employees)</option>
          </select>
          <input
            ref={importRef}
            type="file"
            accept=".xlsx"
            onChange={onImport}
            className="block text-sm"
          />
        </Card>
      </div>

      <div className="mt-8 bg-white p-4 rounded-lg border border-slate-200">
        <h2 className="text-lg font-medium mb-2">엑셀 헤더 가이드</h2>
        <ul className="text-sm text-slate-600 space-y-1 list-disc pl-5">
          <li>
            <code>items</code>: <code>sku, name, unit, unit_price, stock_qty</code>
            (또는 한글: SKU, 품목명, 단위, 단가, 재고)
          </li>
          <li>
            <code>customers</code>: <code>name, email, phone, company</code> (한글:
            이름, 회사)
          </li>
          <li>
            <code>employees</code>:{" "}
            <code>employee_no, full_name, email, position, salary</code>
          </li>
        </ul>
      </div>
    </AppShell>
  );
}

function Card({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="bg-white p-4 rounded-lg border border-slate-200">
      <h2 className="text-lg font-medium mb-3">{title}</h2>
      {children}
    </div>
  );
}
