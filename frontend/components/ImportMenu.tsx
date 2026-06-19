"use client";
import { useState } from "react";
import { downloadFile, uploadFile } from "@/lib/api";

type ImportResult = {
  created: number;
  updated: number;
  skipped: number;
  errors: { row: number; reason: string }[];
  total_rows: number;
};

/**
 * 공용 일괄 업로드 / 양식 다운로드 버튼 그룹.
 *
 * - importEndpoint: POST 대상 (multipart). upsert=true 자동 부착.
 * - templateEndpoint: 양식 GET URL (format=xlsx 자동 부착).
 * - 결과를 한국어로 alert 노출. 오류 행이 있으면 상위 10건까지 표시.
 */
export default function ImportMenu({
  importEndpoint,
  templateEndpoint,
  templateFilename,
  onComplete,
  onError,
}: {
  importEndpoint: string;
  templateEndpoint: string;
  templateFilename: string;
  onComplete?: () => void;
  onError?: (s: string) => void;
}) {
  const [busy, setBusy] = useState(false);

  const pick = () => {
    const input = document.createElement("input");
    input.type = "file";
    input.accept = ".xlsx,.csv,.xls";
    input.onchange = async () => {
      const f = input.files?.[0];
      if (!f) return;
      setBusy(true);
      try {
        const sep = importEndpoint.includes("?") ? "&" : "?";
        const res = await uploadFile<ImportResult>(
          `${importEndpoint}${sep}upsert=true`,
          f
        );
        // 결과 alert + 에러 50건까지 표시 (이상은 "외 N건")
        const errCount = res.errors.length;
        let errMsg = "";
        if (errCount > 0) {
          const shown = res.errors.slice(0, 50);
          const overflow = errCount - shown.length;
          errMsg =
            `\n\n실패 ${errCount}건:\n` +
            shown.map((e) => `  ${e.row}행: ${e.reason}`).join("\n");
          if (overflow > 0) errMsg += `\n  ...외 ${overflow}건`;
        }
        alert(
          `[완료]\n신규 ${res.created} · 갱신 ${res.updated} · 건너뜀 ${res.skipped} (총 ${res.total_rows}행)${errMsg}`
        );
        onComplete?.();
      } catch (e) {
        if (onError) onError(String(e));
        else alert(`업로드 실패: ${e}`);
      } finally {
        setBusy(false);
      }
    };
    input.click();
  };

  const downloadTemplate = () => {
    const sep = templateEndpoint.includes("?") ? "&" : "?";
    downloadFile(`${templateEndpoint}${sep}format=xlsx`, templateFilename).catch(
      (e) => (onError ? onError(String(e)) : alert(`다운로드 실패: ${e}`))
    );
  };

  return (
    <div className="inline-flex rounded border border-emerald-300 overflow-hidden text-sm bg-emerald-50">
      <button
        onClick={pick}
        disabled={busy}
        className="px-3 py-1 hover:bg-emerald-100 disabled:opacity-50"
        title="Excel(.xlsx) 또는 CSV 업로드"
      >
        {busy ? "업로드 중..." : "↑ 업로드"}
      </button>
      <button
        onClick={downloadTemplate}
        className="px-3 py-1 hover:bg-emerald-100 border-l border-emerald-300"
        title="업로드 양식 다운로드"
      >
        양식
      </button>
    </div>
  );
}
