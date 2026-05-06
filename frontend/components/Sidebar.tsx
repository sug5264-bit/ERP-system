"use client";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { ADMIN_MODULES, MODULES } from "@/lib/modules";
import { clearToken } from "@/lib/api";
import { hasRole, useMe } from "@/lib/auth";
import { useT } from "@/lib/i18n";

export default function Sidebar() {
  const pathname = usePathname();
  const router = useRouter();
  const me = useMe();
  const { t, lang, setLang } = useT();

  const handleLogout = () => {
    clearToken();
    router.push("/login");
  };

  return (
    <aside className="w-60 min-h-screen bg-slate-900 text-slate-100 flex flex-col">
      <div className="px-4 py-5 border-b border-brand-800 flex justify-between items-center">
        <div className="flex items-center gap-2">
          <span className="w-8 h-8 rounded-full bg-brand-500 flex items-center justify-center text-lg">🌱</span>
          <span className="text-lg font-semibold tracking-tight">{t("app.title")}</span>
        </div>
        <button
          onClick={() => setLang(lang === "ko" ? "en" : "ko")}
          className="text-xs px-2 py-0.5 bg-brand-800 hover:bg-brand-700 rounded"
        >
          {t("lang.toggle")}
        </button>
      </div>
      {me && (
        <div className="px-4 py-3 text-xs border-b border-slate-700">
          <div className="text-slate-300">{me.full_name}</div>
          <div className="text-slate-500">{me.email}</div>
          <span className="inline-block mt-1 px-2 py-0.5 rounded bg-slate-700 text-slate-100 uppercase">
            {me.role}
          </span>
        </div>
      )}
      <nav className="flex-1 py-4">
        <Link
          href="/"
          className={`block px-4 py-2 hover:bg-slate-800 ${
            pathname === "/" ? "bg-slate-800" : ""
          }`}
        >
          {t("nav.dashboard")}
        </Link>
        {MODULES.map((m) => (
          <Link
            key={m.key}
            href={m.href}
            className={`block px-4 py-2 hover:bg-slate-800 ${
              pathname.startsWith(m.href) ? "bg-slate-800" : ""
            }`}
          >
            {t(m.labelKey as any)}
          </Link>
        ))}
        {ADMIN_MODULES.filter((m) => hasRole(me, m.minRole ?? "viewer")).length > 0 && (
          <div className="px-4 py-2 mt-2 text-xs uppercase text-slate-500">Admin</div>
        )}
        {ADMIN_MODULES.filter((m) => hasRole(me, m.minRole ?? "viewer")).map((m) => (
          <Link
            key={m.key}
            href={m.href}
            className={`block px-4 py-2 hover:bg-slate-800 ${
              pathname.startsWith(m.href) ? "bg-slate-800" : ""
            }`}
          >
            {t(m.labelKey as any)}
          </Link>
        ))}
      </nav>
      <button
        onClick={handleLogout}
        className="m-3 px-3 py-2 bg-slate-700 hover:bg-slate-600 rounded text-sm"
      >
        {t("auth.logout")}
      </button>
    </aside>
  );
}
