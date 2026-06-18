"use client";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { ADMIN_MODULES, MODULES } from "@/lib/modules";
import { clearToken } from "@/lib/api";
import { hasRole, useMe } from "@/lib/auth";
import { useT } from "@/lib/i18n";
import BrandMark from "./BrandMark";

export default function Sidebar() {
  const pathname = usePathname();
  const router = useRouter();
  const me = useMe();
  const { t, lang, setLang } = useT();

  const handleLogout = () => {
    clearToken();
    router.push("/login");
  };

  const navItemClass = (active: boolean) =>
    `block px-4 py-2 transition-colors border-l-2 ${
      active
        ? "bg-brown-800 border-brand-500 text-white"
        : "border-transparent text-brown-50 hover:bg-brown-800/60 hover:border-brand-500/60"
    }`;

  return (
    <aside className="w-60 min-h-screen bg-slate-900 text-brown-50 flex flex-col font-brand">
      <div className="px-4 py-5 border-b border-brown-800 flex justify-between items-center">
        <BrandMark variant="mono" color="#FFFFFF" size={20} />
        <button
          onClick={() => setLang(lang === "ko" ? "en" : "ko")}
          className="text-xs px-2 py-0.5 bg-brown-800 hover:bg-brand-600 text-brand-100 rounded transition-colors"
        >
          {t("lang.toggle")}
        </button>
      </div>
      {me && (
        <div className="px-4 py-3 text-xs border-b border-brown-800">
          <div className="text-brown-100 font-medium">{me.full_name}</div>
          <div className="text-brown-200/70">{me.email}</div>
          <span className="inline-block mt-1 px-2 py-0.5 rounded bg-brand-600 text-white uppercase tracking-wide font-medium">
            {me.role}
          </span>
        </div>
      )}
      <nav className="flex-1 py-4 overflow-y-auto">
        <Link href="/" className={navItemClass(pathname === "/")}>
          {t("nav.dashboard")}
        </Link>
        {MODULES.map((m) => (
          <Link key={m.key} href={m.href} className={navItemClass(pathname.startsWith(m.href))}>
            {t(m.labelKey as any)}
          </Link>
        ))}
        {ADMIN_MODULES.filter((m) => hasRole(me, m.minRole ?? "viewer")).length > 0 && (
          <div className="px-4 py-2 mt-2 text-xs uppercase tracking-wider text-gold-300/80">
            Admin
          </div>
        )}
        {ADMIN_MODULES.filter((m) => hasRole(me, m.minRole ?? "viewer")).map((m) => (
          <Link key={m.key} href={m.href} className={navItemClass(pathname.startsWith(m.href))}>
            {t(m.labelKey as any)}
          </Link>
        ))}
      </nav>
      <button
        onClick={handleLogout}
        className="m-3 px-3 py-2 bg-brown-800 hover:bg-brand-700 rounded text-sm font-medium transition-colors"
      >
        {t("auth.logout")}
      </button>
    </aside>
  );
}
