/**
 * 한국 사업자등록번호 클라이언트 측 체크섬 검증.
 * 백엔드와 동일 알고리즘 — 사용자가 잘못 입력하면 즉시 빨간 글씨로 안내.
 */
const WEIGHTS = [1, 3, 7, 1, 3, 7, 1, 3, 5];

export function normalizeBizNo(v: string): string {
  return (v || "").replace(/[^0-9]/g, "");
}

export function formatBizNo(v: string): string {
  const d = normalizeBizNo(v);
  if (d.length !== 10) return v;
  return `${d.slice(0, 3)}-${d.slice(3, 5)}-${d.slice(5)}`;
}

export function isValidBizNo(v: string): boolean {
  const d = normalizeBizNo(v);
  if (d.length !== 10) return false;
  if (d.slice(0, 3) === "000") return false;
  let total = 0;
  for (let i = 0; i < 9; i++) total += parseInt(d[i], 10) * WEIGHTS[i];
  total += Math.floor((parseInt(d[8], 10) * 5) / 10);
  const check = (10 - (total % 10)) % 10;
  return check === parseInt(d[9], 10);
}
