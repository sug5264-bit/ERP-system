import type { Metadata } from "next";
import "./globals.css";
import Toasts from "@/components/Toasts";
import { CurrencyProvider } from "@/lib/currency";
import { I18nProvider } from "@/lib/i18n";
import { ThemeProvider } from "@/lib/theme";
import { WSProvider } from "@/lib/ws";

export const metadata: Metadata = {
  title: "ERP System",
  description: "Internal ERP PoC",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="ko">
      <body>
        <ThemeProvider>
          <I18nProvider>
            <CurrencyProvider>
              <WSProvider>
                {children}
                <Toasts />
              </WSProvider>
            </CurrencyProvider>
          </I18nProvider>
        </ThemeProvider>
      </body>
    </html>
  );
}
