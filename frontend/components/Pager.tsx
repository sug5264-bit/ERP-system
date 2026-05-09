"use client";

export default function Pager({
  page,
  pages,
  total,
  size = 20,
  onChange,
}: {
  page: number;
  pages: number;
  total: number;
  /** Items per page — must match what was sent to the server. */
  size?: number;
  onChange: (p: number) => void;
}) {
  if (pages <= 1) {
    return total > 0 ? (
      <p className="text-xs text-slate-500 mt-2">총 {total}건</p>
    ) : null;
  }
  const prev = Math.max(1, page - 1);
  const next = Math.min(pages, page + 1);
  const from = (page - 1) * size + 1;
  const to = Math.min(page * size, total);
  return (
    <div className="flex items-center justify-between mt-3 text-sm">
      <span className="text-slate-500">
        {from}-{to} / 총 {total}건
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
