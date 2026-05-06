"use client";
import AuthGate from "./AuthGate";
import CurrencyPicker from "./CurrencyPicker";
import NotificationsBell from "./NotificationsBell";
import SearchBar from "./SearchBar";
import Sidebar from "./Sidebar";
import { useTheme } from "@/lib/theme";

export default function AppShell({ children }: { children: React.ReactNode }) {
  const { theme, toggle } = useTheme();
  return (
    <AuthGate>
      <div className="flex">
        <Sidebar />
        <main className="flex-1 flex flex-col">
          <header className="bg-white dark:bg-slate-900 border-b border-slate-200 dark:border-slate-700 px-6 py-2 flex items-center gap-3">
            <SearchBar />
            <div className="flex-1" />
            <CurrencyPicker />
            <button
              onClick={toggle}
              className="px-2 py-1 rounded hover:bg-slate-100 dark:hover:bg-slate-800 text-sm"
              title="Toggle theme"
            >
              {theme === "dark" ? "☀️" : "🌙"}
            </button>
            <NotificationsBell />
          </header>
          <div className="flex-1 p-6">{children}</div>
        </main>
      </div>
    </AuthGate>
  );
}
