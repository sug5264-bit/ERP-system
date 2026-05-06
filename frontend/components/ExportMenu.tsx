"use client";
import { downloadFile } from "@/lib/api";

export default function ExportMenu({
  endpoint,
  filename,
}: {
  endpoint: string;
  filename: string;
}) {
  const onExport = (format: "csv" | "xlsx" | "pdf") => {
    const sep = endpoint.includes("?") ? "&" : "?";
    const ext = format === "xlsx" ? "xlsx" : format;
    downloadFile(`${endpoint}${sep}format=${format}`, `${filename}.${ext}`).catch((e) =>
      alert(`Export failed: ${e}`)
    );
  };

  return (
    <div className="inline-flex rounded border border-slate-300 overflow-hidden text-sm">
      <button onClick={() => onExport("csv")} className="px-3 py-1 hover:bg-slate-100">
        CSV
      </button>
      <button
        onClick={() => onExport("xlsx")}
        className="px-3 py-1 hover:bg-slate-100 border-l border-slate-300"
      >
        Excel
      </button>
      <button
        onClick={() => onExport("pdf")}
        className="px-3 py-1 hover:bg-slate-100 border-l border-slate-300"
      >
        PDF
      </button>
    </div>
  );
}
