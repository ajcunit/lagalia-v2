import type { LucideIcon } from "lucide-react";
import {
  Activity,
  ArrowLeftRight,
  GitBranch,
  BarChart3,
  Bot,
  Building2,
  CalendarCheck,
  ClipboardList,
  Copy,
  FileText,
  Globe,
  KeyRound,
  Layers,
  LayoutDashboard,
  MessagesSquare,
  Network,
  Receipt,
  RefreshCw,
  Search,
  Settings,
  ShieldAlert,
  ShieldCheck,
  SlidersHorizontal,
  Star,
  Users,
  Webhook,
} from "lucide-react";

import type { TranslationKey } from "../i18n/ca";

export interface NavItem {
  to: string;
  labelKey: TranslationKey;
  icon: LucideIcon;
  /** Acció de la matriu A2 necessària; sense acció = visible per a tothom. */
  action?: string;
  /** Mòdul activable que la governa (specs/module-flags.md). */
  module?: string;
}

/** Navegació principal plana (B-015 fase 1): icona + espai per respirar. */
export const MAIN_NAV: NavItem[] = [
  { to: "/", labelKey: "nav.dashboard", icon: LayoutDashboard },
  { to: "/contracts", labelKey: "nav.contracts", icon: FileText, action: "contracts:read" },
  {
    to: "/minor-contracts",
    labelKey: "nav.minorContracts",
    icon: Receipt,
    action: "minor_contracts:read",
    module: "minor_contracts",
  },
  { to: "/contractors", labelKey: "nav.contractors", icon: Building2, action: "contracts:read", module: "contractors" },
  { to: "/tasks", labelKey: "nav.tasks", icon: CalendarCheck, action: "tasks:read", module: "tasks" },
  { to: "/favorites", labelKey: "nav.favorites", icon: Star, action: "tools:use", module: "favorites" },
  { to: "/cpv", labelKey: "nav.cpv", icon: Search, action: "tools:use", module: "cpv" },
  { to: "/search", labelKey: "nav.superSearch", icon: Globe, action: "tools:use", module: "super_search" },
  { to: "/generator", labelKey: "nav.docgen", icon: Layers, action: "tools:use", module: "docgen" },
  { to: "/analyst", labelKey: "nav.analyst", icon: BarChart3, action: "audit:run", module: "analyst" },
  { to: "/chat", labelKey: "nav.chat", icon: MessagesSquare, action: "audit:run", module: "chat" },
  { to: "/audit", labelKey: "nav.riskAudit", icon: ShieldAlert, action: "audit:run", module: "risk_audit" },
  { to: "/plan", labelKey: "nav.plan", icon: ClipboardList, action: "plan:read", module: "plan" },
];

/** Entrada única de configuració: hub amb totes les pantalles d'administració. */
export const ADMIN_NAV_ITEM: NavItem = {
  to: "/admin",
  labelKey: "nav.config",
  icon: Settings,
};

export interface AdminTile {
  to: string;
  labelKey: TranslationKey;
  descriptionKey: TranslationKey;
  icon: LucideIcon;
  action: string;
  module?: string;
}

/** Targetes del hub de configuració (/admin). */
export const ADMIN_TILES: AdminTile[] = [
  {
    to: "/admin/system",
    labelKey: "nav.systemStatus",
    descriptionKey: "adminHub.systemStatus",
    icon: Activity,
    action: "system:read",
  },
  {
    to: "/admin/users",
    labelKey: "nav.users",
    descriptionKey: "adminHub.users",
    icon: Users,
    action: "users:read",
  },
  {
    to: "/admin/departments",
    labelKey: "nav.departments",
    descriptionKey: "adminHub.departments",
    icon: Network,
    action: "departments:write",
  },
  {
    to: "/contractors/duplicates",
    labelKey: "nav.duplicates",
    descriptionKey: "adminHub.duplicates",
    icon: Copy,
    action: "duplicates:manage",
    module: "contractors",
  },
  {
    to: "/admin/sync",
    labelKey: "nav.sync",
    descriptionKey: "adminHub.sync",
    icon: RefreshCw,
    action: "sync:read",
  },
  {
    to: "/admin/field-mappings",
    labelKey: "nav.fieldMappings",
    descriptionKey: "adminHub.fieldMappings",
    icon: ArrowLeftRight,
    action: "config:write",
  },
  {
    to: "/admin/bpm",
    labelKey: "nav.bpm",
    descriptionKey: "adminHub.bpm",
    icon: GitBranch,
    action: "bpm:manage",
    module: "bpm",
  },
  {
    to: "/admin/webhooks",
    labelKey: "nav.webhooks",
    descriptionKey: "adminHub.webhooks",
    icon: Webhook,
    action: "webhooks:manage",
    module: "webhooks",
  },
  {
    to: "/admin/service-accounts",
    labelKey: "nav.serviceAccounts",
    descriptionKey: "adminHub.serviceAccounts",
    icon: KeyRound,
    action: "service_accounts:manage",
  },
  {
    to: "/admin/ai",
    labelKey: "nav.ai",
    descriptionKey: "adminHub.ai",
    icon: Bot,
    action: "config:write",
  },
  {
    to: "/admin/config",
    labelKey: "adminHub.settingsTitle",
    descriptionKey: "adminHub.settings",
    icon: SlidersHorizontal,
    action: "config:write",
  },
  {
    to: "/admin/audit-log",
    labelKey: "nav.securityAudit",
    descriptionKey: "adminHub.securityAudit",
    icon: ShieldCheck,
    action: "audit_log:read",
  },
];

/** Filtra per accions de GET /me/permissions i per mòduls desactivats. */
export function visibleItems<T extends { action?: string; module?: string }>(
  items: T[],
  actions: string[],
  disabledModules: string[] = [],
): T[] {
  return items.filter(
    (item) =>
      (item.action === undefined || actions.includes(item.action)) &&
      (item.module === undefined || !disabledModules.includes(item.module)),
  );
}

/** El hub de configuració es mostra si l'usuari pot veure alguna targeta. */
export function canSeeAdminHub(actions: string[], disabledModules: string[] = []): boolean {
  return visibleItems(ADMIN_TILES, actions, disabledModules).length > 0;
}
