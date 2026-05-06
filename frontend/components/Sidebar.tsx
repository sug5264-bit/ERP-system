"use client";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { MODULES } from "@/lib/modules";
import { clearToken } from "@/lib/api";

export default function Sidebar() {
  const pathname = usePathname();
  const router = useRouter();

  const handleLogout = () => {
    clearToken();
    router.push("/login");
  };

  return (
    <aside className="w-60 min-h-screen bg-slate-900 text-slate-100 flex flex-col">
      <div className="px-4 py-5 text-xl font-semibold border-b border-slate-700">
        ERP System
      </div>
      <nav className="flex-1 py-4">
        <Link
          href="/"
          className={`block px-4 py-2 hover:bg-slate-800 ${
            pathname === "/" ? "bg-slate-800" : ""
          }`}
        >
          Dashboard
        </Link>
        {MODULES.map((m) => (
          <Link
            key={m.key}
            href={m.href}
            className={`block px-4 py-2 hover:bg-slate-800 ${
              pathname.startsWith(m.href) ? "bg-slate-800" : ""
            }`}
          >
            {m.label}
          </Link>
        ))}
      </nav>
      <button
        onClick={handleLogout}
        className="m-3 px-3 py-2 bg-slate-700 hover:bg-slate-600 rounded text-sm"
      >
        Logout
      </button>
    </aside>
  );
}
