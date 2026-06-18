"use client";
import { useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { api, login, setToken } from "@/lib/api";
import { useT } from "@/lib/i18n";
import BrandMark from "@/components/BrandMark";

export default function LoginPage() {
  const router = useRouter();
  const params = useSearchParams();
  const { t, lang, setLang } = useT();
  const [email, setEmail] = useState("admin@wellgreen.com");
  const [password, setPassword] = useState("admin1234");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [providers, setProviders] = useState<{ google: boolean }>({ google: false });

  useEffect(() => {
    const tokenFromUrl = params.get("token");
    if (tokenFromUrl) {
      setToken(tokenFromUrl);
      router.replace("/");
      return;
    }
    api<{ google: boolean }>("/api/auth/oauth/providers")
      .then(setProviders)
      .catch(() => {});
  }, [params, router]);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError("");
    try {
      await login(email, password);
      router.push("/");
    } catch {
      setError(lang === "ko" ? "로그인 실패." : "Login failed.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-brand-50 via-white to-gold-50 px-4">
      <form
        onSubmit={submit}
        className="bg-white p-8 rounded-xl shadow-xl w-[26rem] space-y-4 border border-brand-100 ring-1 ring-brand-500/20"
      >
        <div className="flex justify-between items-start">
          <BrandMark size={28} />
          <button
            type="button"
            onClick={() => setLang(lang === "ko" ? "en" : "ko")}
            className="text-xs px-2 py-1 border border-brown-200 text-brown-700 rounded hover:bg-brand-50"
          >
            {t("lang.toggle")}
          </button>
        </div>
        <div className="border-t border-brand-100 pt-3">
          <h1 className="text-lg font-semibold text-brown-700">
            {t("auth.login.title")}
          </h1>
        </div>
        <div>
          <label className="block text-sm text-brown-700 mb-1 font-medium">
            {t("auth.email")}
          </label>
          <input
            type="email"
            className="w-full border border-brown-200 rounded px-3 py-2 focus:outline-none focus:ring-2 focus:ring-brand-500 focus:border-transparent"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
          />
        </div>
        <div>
          <label className="block text-sm text-brown-700 mb-1 font-medium">
            {t("auth.password")}
          </label>
          <input
            type="password"
            className="w-full border border-brown-200 rounded px-3 py-2 focus:outline-none focus:ring-2 focus:ring-brand-500 focus:border-transparent"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
          />
        </div>
        {error && <p className="text-red-600 text-sm">{error}</p>}
        <button
          type="submit"
          disabled={loading}
          className="w-full bg-brand-600 text-white py-2.5 rounded font-medium hover:bg-brand-700 disabled:opacity-50 transition-colors"
        >
          {loading ? "..." : t("auth.login")}
        </button>

        {providers.google && (
          <>
            <div className="flex items-center gap-3 my-4">
              <hr className="flex-1 border-brand-100" />
              <span className="text-xs text-warm-gray">또는</span>
              <hr className="flex-1 border-brand-100" />
            </div>
            <a
              href="/api/auth/oauth/google/start"
              className="block w-full text-center border border-brown-200 py-2 rounded hover:bg-brand-50 text-sm text-brown-700"
            >
              Google로 로그인
            </a>
          </>
        )}

        <p className="text-xs text-warm-gray text-center pt-2">
          admin@wellgreen.com / admin1234
        </p>
      </form>
    </div>
  );
}
