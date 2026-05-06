// Module registry - add a new entry here when introducing a new module on the frontend.
export type ModuleDef = {
  key: string;
  label: string;
  href: string;
};

export const MODULES: ModuleDef[] = [
  { key: "hr", label: "HR / 인사", href: "/hr" },
  { key: "finance", label: "재무 / 회계", href: "/finance" },
  { key: "inventory", label: "재고 / 물류", href: "/inventory" },
  { key: "sales", label: "영업 / CRM", href: "/sales" },
];
