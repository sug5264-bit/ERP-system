"use client";
import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";

type SearchHit = {
  module: string;
  type: string;
  id: number;
  title: string;
  subtitle: string;
  href: string;
};

export default function SearchBar() {
  const router = useRouter();
  const [q, setQ] = useState("");
  const [open, setOpen] = useState(false);
  const [hits, setHits] = useState<SearchHit[]>([]);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!q.trim()) {
      setHits([]);
      return;
    }
    const id = setTimeout(() => {
      api<{ results: SearchHit[] }>(`/api/search?q=${encodeURIComponent(q)}`)
        .then((r) => setHits(r.results))
        .catch(() => setHits([]));
    }, 200);
    return () => clearTimeout(id);
  }, [q]);

  useEffect(() => {
    const close = (e: MouseEvent) => {
      if (!ref.current?.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, []);

  return (
    <div ref={ref} className="relative w-72">
      <input
        type="search"
        value={q}
        placeholder="검색 (직원, 고객, 품목, 주문...)"
        onFocus={() => setOpen(true)}
        onChange={(e) => {
          setQ(e.target.value);
          setOpen(true);
        }}
        className="w-full border border-slate-300 rounded px-3 py-1 text-sm bg-white"
      />
      {open && q && (
        <div className="absolute left-0 right-0 mt-1 bg-white border border-slate-200 rounded-lg shadow-lg z-30 max-h-96 overflow-y-auto">
          {hits.length === 0 ? (
            <div className="p-3 text-sm text-slate-500">결과 없음</div>
          ) : (
            <ul>
              {hits.map((h) => (
                <li key={`${h.module}-${h.type}-${h.id}`}>
                  <button
                    onClick={() => {
                      setOpen(false);
                      setQ("");
                      router.push(h.href);
                    }}
                    className="w-full text-left px-3 py-2 hover:bg-slate-50 border-b last:border-b-0"
                  >
                    <div className="flex items-center justify-between">
                      <span className="text-sm font-medium">{h.title}</span>
                      <span className="text-xs text-slate-500 uppercase">{h.type}</span>
                    </div>
                    {h.subtitle && (
                      <div className="text-xs text-slate-500 truncate">{h.subtitle}</div>
                    )}
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}
