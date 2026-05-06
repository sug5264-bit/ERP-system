"use client";
import AuthGate from "./AuthGate";
import NotificationsBell from "./NotificationsBell";
import Sidebar from "./Sidebar";

export default function AppShell({ children }: { children: React.ReactNode }) {
  return (
    <AuthGate>
      <div className="flex">
        <Sidebar />
        <main className="flex-1 flex flex-col">
          <header className="bg-white border-b border-slate-200 px-6 py-2 flex justify-end items-center">
            <NotificationsBell />
          </header>
          <div className="flex-1 p-6">{children}</div>
        </main>
      </div>
    </AuthGate>
  );
}
