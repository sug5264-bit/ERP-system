"use client";
import { createContext, useContext, useEffect, useState, ReactNode } from "react";

export type Lang = "ko" | "en";

const messages = {
  ko: {
    "app.title": "ERP 시스템",
    "nav.dashboard": "대시보드",
    "nav.hr": "HR / 인사",
    "nav.finance": "재무 / 회계",
    "nav.inventory": "재고 / 물류",
    "nav.sales": "영업 / CRM",
    "nav.approvals": "결재",
    "nav.admin.users": "사용자 관리",
    "nav.admin.audit": "감사 로그",
    "common.add": "추가",
    "common.delete": "삭제",
    "common.save": "저장",
    "common.cancel": "취소",
    "common.search": "검색",
    "common.loading": "불러오는 중...",
    "common.empty": "데이터가 없습니다",
    "common.actions": "작업",
    "auth.email": "이메일",
    "auth.password": "비밀번호",
    "auth.login": "로그인",
    "auth.login.title": "ERP 로그인",
    "auth.logout": "로그아웃",
    "auth.role": "역할",
    "dashboard.summary": "요약",
    "dashboard.employees": "직원",
    "dashboard.items": "품목",
    "dashboard.lowStock": "재고 부족",
    "dashboard.orders": "주문",
    "dashboard.openOrders": "미확정 주문",
    "dashboard.totalSales": "총 매출",
    "dashboard.salesByMonth": "월별 매출",
    "dashboard.employeesByDept": "부서별 직원",
    "dashboard.topItems": "재고 가치 Top",
    "lang.toggle": "EN",
  },
  en: {
    "app.title": "ERP System",
    "nav.dashboard": "Dashboard",
    "nav.hr": "HR",
    "nav.finance": "Finance",
    "nav.inventory": "Inventory",
    "nav.sales": "Sales / CRM",
    "nav.approvals": "Approvals",
    "nav.admin.users": "User Management",
    "nav.admin.audit": "Audit Log",
    "common.add": "Add",
    "common.delete": "Delete",
    "common.save": "Save",
    "common.cancel": "Cancel",
    "common.search": "Search",
    "common.loading": "Loading...",
    "common.empty": "No data",
    "common.actions": "Actions",
    "auth.email": "Email",
    "auth.password": "Password",
    "auth.login": "Sign in",
    "auth.login.title": "ERP Login",
    "auth.logout": "Logout",
    "auth.role": "Role",
    "dashboard.summary": "Summary",
    "dashboard.employees": "Employees",
    "dashboard.items": "Items",
    "dashboard.lowStock": "Low Stock",
    "dashboard.orders": "Orders",
    "dashboard.openOrders": "Open Orders",
    "dashboard.totalSales": "Total Sales",
    "dashboard.salesByMonth": "Sales by Month",
    "dashboard.employeesByDept": "Employees by Department",
    "dashboard.topItems": "Top Items by Stock Value",
    "lang.toggle": "한",
  },
} as const;

type Key = keyof typeof messages.ko;

const I18nContext = createContext<{
  lang: Lang;
  setLang: (l: Lang) => void;
  t: (key: Key) => string;
}>({ lang: "ko", setLang: () => {}, t: (k) => k });

export function I18nProvider({ children }: { children: ReactNode }) {
  const [lang, setLangState] = useState<Lang>("ko");

  useEffect(() => {
    const saved = (typeof window !== "undefined" && localStorage.getItem("erp_lang")) as Lang | null;
    if (saved === "ko" || saved === "en") setLangState(saved);
  }, []);

  const setLang = (l: Lang) => {
    setLangState(l);
    localStorage.setItem("erp_lang", l);
  };

  const t = (key: Key): string => messages[lang][key] ?? messages.ko[key] ?? key;

  return <I18nContext.Provider value={{ lang, setLang, t }}>{children}</I18nContext.Provider>;
}

export function useT() {
  return useContext(I18nContext);
}
