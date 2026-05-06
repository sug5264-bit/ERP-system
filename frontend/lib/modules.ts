// Module registry. Add a new entry when introducing a new module.
import type { Role } from "./auth";

export type ModuleDef = {
  key: string;
  labelKey: string; // i18n key
  href: string;
  minRole?: Role; // optional: hide nav entry if user lacks role
};

export const MODULES: ModuleDef[] = [
  { key: "hr", labelKey: "nav.hr", href: "/hr" },
  { key: "finance", labelKey: "nav.finance", href: "/finance" },
  { key: "inventory", labelKey: "nav.inventory", href: "/inventory" },
  { key: "sales", labelKey: "nav.sales", href: "/sales" },
  { key: "approvals", labelKey: "nav.approvals", href: "/approvals" },
  { key: "reports", labelKey: "nav.reports", href: "/reports" },
];

export const ADMIN_MODULES: ModuleDef[] = [
  { key: "admin-users", labelKey: "nav.admin.users", href: "/admin/users", minRole: "admin" },
  { key: "admin-audit", labelKey: "nav.admin.audit", href: "/admin/audit", minRole: "admin" },
  {
    key: "admin-fields",
    labelKey: "nav.admin.fields",
    href: "/admin/custom-fields",
    minRole: "admin",
  },
  {
    key: "admin-data",
    labelKey: "nav.admin.data",
    href: "/admin/data",
    minRole: "admin",
  },
];
