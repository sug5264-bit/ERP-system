"use client";

export default function Pager({
  page,
  pages,
  total,
  onChange,
}: {
  page: number;
  pages: number;
  total: number;
  onChange: (p: number) => void;
}) {
  if (pages <= 1) {
    return total > 0 ? (
      <p className="text-xs text-slate-500 mt-2">총 {total}건</p>
    ) : null;
  }
  const prev = Math.max(1, page - 1);
  const next = Math.min(pages, page + 1);
  return (
    <div className="flex items-center justify-between mt-3 text-sm">
      <span className="text-slate-500">
        {(page - 1) * 20 + 1}-{Math.min(page * 20, total)} / 총 {total}건
      </span>
      <div className="flex gap-1">
        <button
          onClick={() => onChange(prev)}
          disabled={page === 1}
          className="px-3 py-1 border rounded disabled:opacity-40"
        >
          이전
        </button>
        <span className="px-3 py-1">
          {page} / {pages}
        </span>
        <button
          onClick={() => onChange(next)}
          disabled={page === pages}
          className="px-3 py-1 border rounded disabled:opacity-40"
        >
          다음
        </button>
      </div>
    </div>
  );
}
