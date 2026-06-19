"use client";
import { useEffect, useState } from "react";
// useEffect는 ImageUpload 컴포넌트에서 사용
import AppShell from "@/components/AppShell";
import { api, uploadFile } from "@/lib/api";
import { formatBizNo, isValidBizNo, normalizeBizNo } from "@/lib/biz-no";

type CompanyProfile = {
  id?: number;
  business_no: string;
  corporate_no?: string | null;
  company_name: string;
  representative: string;
  address: string;
  business_type?: string | null;
  business_item?: string | null;
  phone?: string | null;
  fax?: string | null;
  email?: string | null;
  website?: string | null;
  bank_name?: string | null;
  bank_account?: string | null;
  bank_holder?: string | null;
};

const EMPTY: CompanyProfile = {
  business_no: "",
  company_name: "",
  representative: "",
  address: "",
};

export default function CompanyProfilePage() {
  const [profile, setProfile] = useState<CompanyProfile>(EMPTY);
  const [loaded, setLoaded] = useState(false);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api<CompanyProfile>("/api/company-profile")
      .then((p) => setProfile(p))
      .catch((e) => {
        if ((e as Error & { status?: number }).status !== 404) {
          setError(String(e));
        }
      })
      .finally(() => setLoaded(true));
  }, []);

  const onChange =
    (key: keyof CompanyProfile) =>
    (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) =>
      setProfile({ ...profile, [key]: e.target.value });

  const save = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    setMessage(null);
    setError(null);
    try {
      const saved = await api<CompanyProfile>("/api/company-profile", {
        method: "PUT",
        body: JSON.stringify(profile),
      });
      setProfile(saved);
      setMessage("저장되었습니다.");
    } catch (e) {
      setError(String(e));
    } finally {
      setSaving(false);
    }
  };

  if (!loaded) {
    return (
      <AppShell>
        <div className="p-6">로딩 중...</div>
      </AppShell>
    );
  }

  return (
    <AppShell>
      <div className="p-6 max-w-3xl">
        <h1 className="text-2xl font-bold mb-2">회사 정보</h1>
        <p className="text-sm text-gray-600 mb-6">
          거래명세표, 세금계산서, 발주서 등 모든 출력 문서에 자사 정보로
          사용됩니다.
        </p>

        {error && (
          <div className="mb-4 p-3 rounded bg-red-50 border border-red-200 text-red-700 text-sm">
            {error}
          </div>
        )}
        {message && (
          <div className="mb-4 p-3 rounded bg-green-50 border border-green-200 text-green-700 text-sm">
            {message}
          </div>
        )}

        <form onSubmit={save} className="space-y-4">
          <Section title="사업자등록증 항목">
            <BizNoField
              value={profile.business_no}
              onChange={(v) => setProfile({ ...profile, business_no: v })}
            />
            <Field
              label="법인등록번호"
              value={profile.corporate_no || ""}
              onChange={onChange("corporate_no")}
            />
            <Field
              label="상호 *"
              value={profile.company_name}
              onChange={onChange("company_name")}
              required
            />
            <Field
              label="대표자 *"
              value={profile.representative}
              onChange={onChange("representative")}
              required
            />
            <Field
              label="사업장 주소 *"
              value={profile.address}
              onChange={onChange("address")}
              required
            />
            <Field
              label="업태"
              placeholder="예: 도소매업, 제조업"
              value={profile.business_type || ""}
              onChange={onChange("business_type")}
            />
            <Field
              label="종목"
              placeholder="예: 식품, 가공식품"
              value={profile.business_item || ""}
              onChange={onChange("business_item")}
            />
          </Section>

          <Section title="연락처">
            <Field
              label="전화"
              value={profile.phone || ""}
              onChange={onChange("phone")}
            />
            <Field
              label="팩스"
              value={profile.fax || ""}
              onChange={onChange("fax")}
            />
            <Field
              label="이메일"
              type="email"
              value={profile.email || ""}
              onChange={onChange("email")}
            />
            <Field
              label="홈페이지"
              value={profile.website || ""}
              onChange={onChange("website")}
            />
          </Section>

          <Section title="입금 계좌 (세금계산서/거래명세표에 표기)">
            <Field
              label="은행명"
              value={profile.bank_name || ""}
              onChange={onChange("bank_name")}
            />
            <Field
              label="계좌번호"
              value={profile.bank_account || ""}
              onChange={onChange("bank_account")}
            />
            <Field
              label="예금주"
              value={profile.bank_holder || ""}
              onChange={onChange("bank_holder")}
            />
          </Section>

          <Section title="로고 / 직인 (PDF 양식에 자동 합성)">
            <ImageUpload
              label="로고 (헤더 좌상단에 표시)"
              endpoint="/api/company-profile/upload-logo"
              previewUrl="/api/company-profile/logo"
              recommendedSpec="권장: 정사각형 또는 가로형 · 600×600px 이상 · PNG(투명배경 권장) 또는 JPG · 2MB 이하"
              onDone={() => setMessage("로고 업로드 완료 — 다음 PDF 출력부터 자동 반영")}
              onError={(e) => setError(e)}
            />
            <ImageUpload
              label="직인 (공급자 박스 옆에 표시)"
              endpoint="/api/company-profile/upload-stamp"
              previewUrl="/api/company-profile/stamp"
              recommendedSpec="권장: 정사각형 · 400×400px 이상 · PNG(투명배경) · 빨간색 인감 스캔본 권장 · 2MB 이하"
              onDone={() => setMessage("직인 업로드 완료 — 다음 PDF 출력부터 자동 반영")}
              onError={(e) => setError(e)}
            />
          </Section>

          <div className="pt-4">
            <button
              type="submit"
              disabled={saving}
              className="px-6 py-2 rounded bg-brand-600 text-white hover:bg-brand-700 disabled:opacity-50"
            >
              {saving ? "저장 중..." : "저장"}
            </button>
          </div>
        </form>
      </div>
    </AppShell>
  );
}

function Section({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <div className="border rounded-lg p-4 bg-white">
      <h2 className="font-semibold text-gray-800 mb-3">{title}</h2>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">{children}</div>
    </div>
  );
}

function Field({
  label,
  type = "text",
  ...props
}: React.InputHTMLAttributes<HTMLInputElement> & { label: string }) {
  return (
    <label className="block text-sm">
      <span className="text-gray-700">{label}</span>
      <input
        type={type}
        {...props}
        className="mt-1 block w-full rounded border-gray-300 shadow-sm focus:border-brand-500 focus:ring-brand-500 px-3 py-2 border"
      />
    </label>
  );
}

function BizNoField({
  value,
  onChange,
}: {
  value: string;
  onChange: (v: string) => void;
}) {
  const normalized = normalizeBizNo(value);
  // 검증은 10자리 전부 입력했을 때만. 입력 중에는 중립.
  const filled = normalized.length === 10;
  const valid = filled && isValidBizNo(value);
  const status =
    !filled ? "neutral" : valid ? "ok" : "bad";

  return (
    <label className="block text-sm">
      <span className="text-gray-700">사업자등록번호 *</span>
      <input
        type="text"
        required
        placeholder="123-45-67890"
        value={value}
        onChange={(e) => {
          // 10자리 다 들어왔으면 자동 하이픈
          const d = normalizeBizNo(e.target.value);
          onChange(d.length === 10 ? formatBizNo(d) : e.target.value);
        }}
        onBlur={() => {
          if (filled && valid) onChange(formatBizNo(value));
        }}
        className={`mt-1 block w-full rounded shadow-sm px-3 py-2 border ${
          status === "bad"
            ? "border-red-400 focus:border-red-500 focus:ring-red-500"
            : status === "ok"
            ? "border-emerald-400 focus:border-emerald-500 focus:ring-emerald-500"
            : "border-gray-300 focus:border-brand-500 focus:ring-brand-500"
        }`}
      />
      {status === "bad" && (
        <div className="text-xs text-red-600 mt-1">
          체크섬 오류 — 입력 번호를 확인하세요
        </div>
      )}
      {status === "ok" && (
        <div className="text-xs text-emerald-700 mt-1">✓ 유효</div>
      )}
    </label>
  );
}

function ImageUpload({
  label,
  endpoint,
  previewUrl,
  recommendedSpec,
  onDone,
  onError,
}: {
  label: string;
  endpoint: string;
  previewUrl: string;
  recommendedSpec: string;
  onDone: () => void;
  onError: (s: string) => void;
}) {
  const [busy, setBusy] = useState(false);
  // blob: URL — Bearer 토큰을 직접 부착하기 위해 fetch + createObjectURL 사용.
  // <img src="/api/..."> 직접 호출은 헤더가 안 붙어 401 발생.
  const [blobUrl, setBlobUrl] = useState<string | null>(null);

  const loadPreview = async () => {
    try {
      const { getToken } = await import("@/lib/api");
      const token = getToken();
      const tenant =
        typeof window !== "undefined"
          ? localStorage.getItem("erp_tenant_id")
          : null;
      const h: Record<string, string> = {};
      if (token) h["Authorization"] = `Bearer ${token}`;
      if (tenant) h["X-Tenant-ID"] = tenant;
      const res = await fetch(previewUrl, { headers: h });
      if (!res.ok) {
        setBlobUrl(null);
        return;
      }
      const blob = await res.blob();
      // 이전 URL 회수
      setBlobUrl((prev) => {
        if (prev) URL.revokeObjectURL(prev);
        return URL.createObjectURL(blob);
      });
    } catch {
      setBlobUrl(null);
    }
  };

  useEffect(() => {
    loadPreview();
    // cleanup
    return () => {
      if (blobUrl) URL.revokeObjectURL(blobUrl);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const pick = () => {
    const input = document.createElement("input");
    input.type = "file";
    input.accept = "image/png,image/jpeg";
    input.onchange = async () => {
      const f = input.files?.[0];
      if (!f) return;
      // 클라이언트 사전 검증
      if (f.size > 2 * 1024 * 1024) {
        onError("파일이 2MB를 초과합니다.");
        return;
      }
      if (!["image/png", "image/jpeg"].includes(f.type)) {
        onError("PNG 또는 JPG만 업로드 가능합니다.");
        return;
      }
      setBusy(true);
      try {
        await uploadFile(endpoint, f);
        await loadPreview();
        onDone();
      } catch (e) {
        onError(String(e));
      } finally {
        setBusy(false);
      }
    };
    input.click();
  };

  return (
    <div className="block text-sm md:col-span-2">
      <div className="text-gray-700 mb-2 font-medium">{label}</div>
      <div className="text-xs text-gray-500 mb-2">{recommendedSpec}</div>
      <div className="flex gap-3 items-center">
        <div className="w-28 h-28 border rounded bg-gray-50 flex items-center justify-center overflow-hidden">
          {blobUrl ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img
              src={blobUrl}
              alt={label}
              className="max-w-full max-h-full object-contain"
            />
          ) : (
            <span className="text-xs text-gray-400">미설정</span>
          )}
        </div>
        <div className="flex flex-col gap-2">
          <button
            type="button"
            onClick={pick}
            disabled={busy}
            className="px-3 py-1 rounded border border-emerald-300 bg-emerald-50 hover:bg-emerald-100 disabled:opacity-50"
          >
            {busy ? "업로드 중..." : "이미지 선택"}
          </button>
          {blobUrl && (
            <div className="text-xs text-emerald-700">✓ 등록됨</div>
          )}
        </div>
      </div>
    </div>
  );
}
