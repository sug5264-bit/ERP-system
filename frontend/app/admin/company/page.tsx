"use client";
import { useEffect, useState } from "react";
import AppShell from "@/components/AppShell";
import { api, uploadFile } from "@/lib/api";

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
            <Field
              label="사업자등록번호 *"
              placeholder="123-45-67890"
              value={profile.business_no}
              onChange={onChange("business_no")}
              required
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
              label="로고"
              endpoint="/api/company-profile/upload-logo"
              previewUrl="/api/company-profile/logo"
              onDone={() => setMessage("로고 업로드 완료")}
              onError={(e) => setError(e)}
            />
            <ImageUpload
              label="직인"
              endpoint="/api/company-profile/upload-stamp"
              previewUrl="/api/company-profile/stamp"
              onDone={() => setMessage("직인 업로드 완료")}
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

function ImageUpload({
  label,
  endpoint,
  previewUrl,
  onDone,
  onError,
}: {
  label: string;
  endpoint: string;
  previewUrl: string;
  onDone: () => void;
  onError: (s: string) => void;
}) {
  const [previewKey, setPreviewKey] = useState(0);
  const [busy, setBusy] = useState(false);

  const pick = () => {
    const input = document.createElement("input");
    input.type = "file";
    input.accept = "image/png,image/jpeg";
    input.onchange = async () => {
      const f = input.files?.[0];
      if (!f) return;
      setBusy(true);
      try {
        await uploadFile(endpoint, f);
        setPreviewKey((k) => k + 1);
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
    <div className="block text-sm">
      <div className="text-gray-700 mb-2">{label}</div>
      <div className="flex gap-3 items-center">
        <div
          className="w-24 h-24 border rounded bg-gray-50 flex items-center justify-center overflow-hidden"
        >
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            key={previewKey}
            src={`${previewUrl}?v=${previewKey}`}
            alt={label}
            className="max-w-full max-h-full object-contain"
            onError={(e) => {
              (e.currentTarget as HTMLImageElement).style.display = "none";
            }}
          />
        </div>
        <button
          type="button"
          onClick={pick}
          disabled={busy}
          className="px-3 py-1 rounded border border-emerald-300 bg-emerald-50 hover:bg-emerald-100 disabled:opacity-50"
        >
          {busy ? "업로드 중..." : "이미지 선택 (PNG/JPG, 2MB↓)"}
        </button>
      </div>
    </div>
  );
}
