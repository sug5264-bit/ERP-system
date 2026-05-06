"use client";
import { useRef, useState } from "react";
import AppShell from "@/components/AppShell";
import { uploadFile } from "@/lib/api";

type Result = {
  text: string;
  lines: { name: string; quantity: number; unit_price: number }[];
  created: { sku: string; name: string }[];
};

export default function OCRPage() {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState<Result | null>(null);
  const [autoCreate, setAutoCreate] = useState(false);
  const ref = useRef<HTMLInputElement>(null);

  const onFile = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setBusy(true);
    setError("");
    setResult(null);
    try {
      const r = await uploadFile<Result>(
        `/api/ocr/receipt?create_items=${autoCreate}`,
        file
      );
      setResult(r);
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
      if (ref.current) ref.current.value = "";
    }
  };

  return (
    <AppShell>
      <h1 className="text-2xl font-semibold mb-4">영수증 OCR</h1>

      <div className="bg-white p-4 rounded-lg border border-slate-200 space-y-3 mb-6">
        <p className="text-sm text-slate-600">
          영수증/송장 이미지를 업로드하면 텍스트를 인식하고{" "}
          <code>품목 / 수량 / 단가</code> 행으로 자동 파싱합니다.
        </p>
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={autoCreate}
            onChange={(e) => setAutoCreate(e.target.checked)}
          />
          파싱된 품목을 재고에 자동 등록 (manager 이상)
        </label>
        <input
          ref={ref}
          type="file"
          accept="image/*"
          onChange={onFile}
          disabled={busy}
          className="block text-sm"
        />
        {busy && <p className="text-xs text-slate-500">처리 중...</p>}
      </div>

      {error && <p className="text-red-600 text-sm mb-3">{error}</p>}

      {result && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div className="bg-white p-4 rounded-lg border border-slate-200">
            <h2 className="font-medium mb-2">파싱 결과 ({result.lines.length}행)</h2>
            <table className="w-full text-sm">
              <thead className="bg-slate-100">
                <tr>
                  <th className="text-left px-2 py-1">품목</th>
                  <th className="text-right px-2 py-1">수량</th>
                  <th className="text-right px-2 py-1">단가</th>
                </tr>
              </thead>
              <tbody>
                {result.lines.map((l, i) => (
                  <tr key={i} className="border-t">
                    <td className="px-2 py-1">{l.name}</td>
                    <td className="px-2 py-1 text-right">{l.quantity}</td>
                    <td className="px-2 py-1 text-right">
                      {l.unit_price.toLocaleString()}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {result.created.length > 0 && (
              <p className="mt-3 text-sm text-brand-700">
                ✓ 신규 품목 {result.created.length}건 등록됨
              </p>
            )}
          </div>

          <div className="bg-white p-4 rounded-lg border border-slate-200">
            <h2 className="font-medium mb-2">원본 텍스트</h2>
            <pre className="text-xs whitespace-pre-wrap text-slate-600">
              {result.text}
            </pre>
          </div>
        </div>
      )}
    </AppShell>
  );
}
