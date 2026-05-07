"use client";

export default function Loading({ label = "불러오는 중..." }: { label?: string }) {
  return (
    <div className="flex items-center gap-2 text-slate-500 text-sm py-6">
      <span className="inline-block w-3 h-3 rounded-full bg-brand-500 animate-pulse" />
      {label}
    </div>
  );
}
