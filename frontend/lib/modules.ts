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
  { key: "payroll", labelKey: "nav.payroll", href: "/hr/payroll" },
  { key: "attendance", labelKey: "nav.attendance", href: "/hr/attendance" },
  { key: "finance", labelKey: "nav.finance", href: "/finance" },
  { key: "periods", labelKey: "nav.periods", href: "/finance/periods", minRole: "manager" },
  { key: "statements", labelKey: "nav.statements", href: "/finance/statements", minRole: "manager" },
  { key: "inventory", labelKey: "nav.inventory", href: "/inventory" },
  { key: "manufacturing", labelKey: "nav.manufacturing", href: "/manufacturing" },
  { key: "sales", labelKey: "nav.sales", href: "/sales" },
  { key: "billing", labelKey: "nav.billing", href: "/billing" },
  { key: "approvals", labelKey: "nav.approvals", href: "/approvals" },
  { key: "suppliers", labelKey: "nav.suppliers", href: "/suppliers" },
  { key: "matching", labelKey: "nav.matching", href: "/suppliers/matching" },
  { key: "rfq", labelKey: "nav.rfq", href: "/suppliers/rfq" },
  { key: "crm", labelKey: "nav.crm", href: "/crm" },
  { key: "assets", labelKey: "nav.assets", href: "/assets" },
  { key: "projects", labelKey: "nav.projects", href: "/projects" },
  { key: "reorder", labelKey: "nav.reorder", href: "/inventory/reorder" },
  { key: "wms", labelKey: "nav.wms", href: "/wms" },
  { key: "dashboards", labelKey: "nav.dashboards", href: "/dashboards" },
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
  {
    key: "admin-keys",
    labelKey: "nav.admin.keys",
    href: "/admin/api-keys",
    minRole: "viewer",  // any logged-in user can manage their own keys
  },
  {
    key: "admin-ledger",
    labelKey: "nav.admin.ledger",
    href: "/admin/ledger",
    minRole: "admin",
  },
  {
    key: "admin-ocr",
    labelKey: "nav.admin.ocr",
    href: "/admin/ocr",
    minRole: "staff",
  },
  {
    key: "admin-forecast",
    labelKey: "nav.admin.forecast",
    href: "/admin/forecast",
    minRole: "viewer",
  },
  {
    key: "admin-form-templates",
    labelKey: "nav.admin.formTemplates",
    href: "/admin/form-templates",
    minRole: "admin",
  },
  {
    key: "admin-edi",
    labelKey: "nav.admin.edi",
    href: "/admin/edi",
    minRole: "admin",
  },
  {
    key: "admin-report-builder",
    labelKey: "nav.admin.reportBuilder",
    href: "/admin/reports",
    minRole: "viewer",
  },
  {
    key: "admin-etax",
    labelKey: "nav.admin.etax",
    href: "/admin/etax",
    minRole: "manager",
  },
  {
    key: "admin-fx",
    labelKey: "nav.admin.fx",
    href: "/admin/fx",
    minRole: "viewer",
  },
  {
    key: "admin-privacy",
    labelKey: "nav.admin.privacy",
    href: "/admin/privacy",
    minRole: "manager",
  },
];
