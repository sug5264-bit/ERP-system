"use client";
import { createContext, useContext, useEffect, useState, ReactNode } from "react";

export type Lang = "ko" | "en";

const messages = {
  ko: {
    "app.title": "WellGreen ERP",
    "nav.dashboard": "대시보드",
    "nav.hr": "HR / 인사",
    "nav.finance": "재무 / 회계",
    "nav.inventory": "재고 / 물류",
    "nav.sales": "영업 / CRM",
    "nav.approvals": "결재",
    "nav.suppliers": "공급사 / 발주",
    "nav.reports": "예약 보고서",
    "nav.admin.users": "사용자 관리",
    "nav.admin.audit": "감사 로그",
    "nav.admin.fields": "커스텀 필드",
    "nav.admin.data": "백업 & 임포트",
    "nav.admin.keys": "API 키",
    "nav.admin.ledger": "공급망 레저",
    "nav.admin.ocr": "영수증 OCR",
    "nav.admin.forecast": "재고 예측",
    "nav.admin.formTemplates": "결재 양식 템플릿",
    "nav.admin.edi": "EDI / B2B",
    "nav.admin.reportBuilder": "리포트 빌더",
    "nav.payroll": "급여 / 휴가",
    "nav.periods": "회계기간 / 결산",
    "nav.manufacturing": "제조 / BOM",
    "nav.billing": "청구 / 수금",
    "nav.matching": "3-way 매칭",
    "nav.rfq": "RFQ / 공급사 평가",
    "nav.crm": "CRM 파이프라인",
    "nav.assets": "자산 / 감가상각",
    "nav.attendance": "근태 / 출퇴근",
    "nav.ats": "채용 / ATS",
    "nav.kpi": "KPI 라이브러리",
    "nav.projects": "프로젝트 / Job",
    "nav.admin.etax": "전자세금계산서",
    "nav.admin.fx": "환율 / FX",
    "nav.admin.privacy": "개인정보 / DSR",
    "nav.reorder": "재고보충 / ABC",
    "nav.dashboards": "대시보드",
    "nav.statements": "재무제표 / 부가세",
    "nav.wms": "WMS / 출하",
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
    "auth.login.title": "WellGreen ERP 로그인",
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
    "app.title": "WellGreen ERP",
    "nav.dashboard": "Dashboard",
    "nav.hr": "HR",
    "nav.finance": "Finance",
    "nav.inventory": "Inventory",
    "nav.sales": "Sales / CRM",
    "nav.approvals": "Approvals",
    "nav.suppliers": "Suppliers / POs",
    "nav.reports": "Scheduled Reports",
    "nav.admin.users": "User Management",
    "nav.admin.audit": "Audit Log",
    "nav.admin.fields": "Custom Fields",
    "nav.admin.data": "Backup & Import",
    "nav.admin.keys": "API Keys",
    "nav.admin.ledger": "Supply Chain Ledger",
    "nav.admin.ocr": "Receipt OCR",
    "nav.admin.forecast": "Inventory Forecast",
    "nav.admin.formTemplates": "Approval Form Builder",
    "nav.admin.edi": "EDI / B2B",
    "nav.admin.reportBuilder": "Report Builder",
    "nav.payroll": "Payroll / Leave",
    "nav.periods": "Fiscal Periods",
    "nav.manufacturing": "Manufacturing / BOM",
    "nav.billing": "Billing / Payments",
    "nav.matching": "3-way Matching",
    "nav.rfq": "RFQ / Vendor Scorecard",
    "nav.crm": "CRM Pipeline",
    "nav.assets": "Fixed Assets",
    "nav.attendance": "Attendance",
    "nav.ats": "ATS / Recruiting",
    "nav.kpi": "KPI Library",
    "nav.projects": "Projects",
    "nav.admin.etax": "E-Tax Invoices",
    "nav.admin.fx": "FX Rates",
    "nav.admin.privacy": "Privacy / DSR",
    "nav.reorder": "Reorder / ABC",
    "nav.dashboards": "Dashboards",
    "nav.statements": "Statements / VAT",
    "nav.wms": "WMS / Shipping",
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
    "auth.login.title": "WellGreen ERP Login",
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
