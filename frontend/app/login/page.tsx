"use client";
import { useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { api, login, setToken } from "@/lib/api";
import { useT } from "@/lib/i18n";

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
    <div className="min-h-screen flex items-center justify-center">
      <form
        onSubmit={submit}
        className="bg-white p-8 rounded-lg shadow-md w-96 space-y-4 border border-slate-200"
      >
        <div className="flex justify-between items-center">
          <h1 className="text-2xl font-semibold">{t("auth.login.title")}</h1>
          <button
            type="button"
            onClick={() => setLang(lang === "ko" ? "en" : "ko")}
            className="text-xs px-2 py-1 border rounded"
          >
            {t("lang.toggle")}
          </button>
        </div>
        <div>
          <label className="block text-sm text-slate-700 mb-1">{t("auth.email")}</label>
          <input
            type="email"
            className="w-full border border-slate-300 rounded px-3 py-2"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
          />
        </div>
        <div>
          <label className="block text-sm text-slate-700 mb-1">{t("auth.password")}</label>
          <input
            type="password"
            className="w-full border border-slate-300 rounded px-3 py-2"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
          />
        </div>
        {error && <p className="text-red-600 text-sm">{error}</p>}
        <button
          type="submit"
          disabled={loading}
          className="w-full bg-slate-900 text-white py-2 rounded hover:bg-slate-800 disabled:opacity-50"
        >
          {loading ? "..." : t("auth.login")}
        </button>

        {providers.google && (
          <>
            <div className="flex items-center gap-3 my-4">
              <hr className="flex-1 border-slate-200" />
              <span className="text-xs text-slate-500">또는</span>
              <hr className="flex-1 border-slate-200" />
            </div>
            <a
              href="/api/auth/oauth/google/start"
              className="block w-full text-center border border-slate-300 py-2 rounded hover:bg-slate-50 text-sm"
            >
              Google로 로그인
            </a>
          </>
        )}

        <p className="text-xs text-slate-500">admin@wellgreen.com / admin1234</p>
      </form>
    </div>
  );
}
