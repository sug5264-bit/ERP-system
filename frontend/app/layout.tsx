import type { Metadata, Viewport } from "next";
import "./globals.css";
import ErrorBoundary from "@/components/ErrorBoundary";
import Toasts from "@/components/Toasts";
import PWARegister from "@/components/PWARegister";
import { CurrencyProvider } from "@/lib/currency";
import { I18nProvider } from "@/lib/i18n";
import { TenantProvider } from "@/lib/tenant";
import { ThemeProvider } from "@/lib/theme";
import { WSProvider } from "@/lib/ws";

export const metadata: Metadata = {
  title: "WellGreen ERP",
  description: "WellGreen 종합 ERP — 음료/주류/유통/물류 관리",
  manifest: "/manifest.webmanifest",
  appleWebApp: {
    capable: true,
    title: "WellGreen ERP",
    statusBarStyle: "default",
  },
  icons: {
    icon: [{ url: "/icon-192.svg", type: "image/svg+xml" }],
    apple: [{ url: "/icon-192.svg" }],
  },
};

export const viewport: Viewport = {
  themeColor: "#15803d",
  width: "device-width",
  initialScale: 1,
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="ko">
      <body>
        <ErrorBoundary>
          <ThemeProvider>
            <I18nProvider>
              <TenantProvider>
                <CurrencyProvider>
                  <WSProvider>
                    {children}
                    <Toasts />
                    <PWARegister />
                  </WSProvider>
                </CurrencyProvider>
              </TenantProvider>
            </I18nProvider>
          </ThemeProvider>
        </ErrorBoundary>
      </body>
    </html>
  );
}
