"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { api } from "@/lib/api";

/**
 * 회사정보가 미설정이면 화면 상단에 상시 안내 배너.
 * 모든 페이지(AppShell)에서 노출되어 신규 도입 시 헤매지 않도록 함.
 *
 * - 404 → 미설정 → 배너 표시
 * - 200 → 정상 → 숨김
 * - 다른 에러 → 조용히 숨김 (네트워크 등)
 */
export default function SetupBanner() {
  const [show, setShow] = useState(false);

  useEffect(() => {
    api("/api/company-profile")
      .then(() => setShow(false))
      .catch((e) => {
        const err = e as Error & { status?: number };
        if (err.status === 404) setShow(true);
      });
  }, []);

  if (!show) return null;

  return (
    <div className="bg-amber-50 border-b border-amber-300 px-6 py-2 flex items-center gap-3 text-sm">
      <span className="font-semibold text-amber-800">⚠ 회사정보 미설정</span>
      <span className="text-amber-700">
        거래명세표·세금계산서 등 PDF 출력에 필요합니다.
      </span>
      <Link
        href="/admin/company"
        className="ml-auto px-3 py-1 rounded bg-amber-600 text-white hover:bg-amber-700"
      >
        지금 등록 →
      </Link>
    </div>
  );
}
