"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { login } from "@/lib/api";
import { useT } from "@/lib/i18n";

export default function LoginPage() {
  const router = useRouter();
  const { t, lang, setLang } = useT();
  const [email, setEmail] = useState("admin@example.com");
  const [password, setPassword] = useState("admin1234");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

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
        <p className="text-xs text-slate-500">admin@example.com / admin1234</p>
      </form>
    </div>
  );
}
