import type { LucideIcon } from "lucide-react";
import {
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
  },
  { to: "/contractors", labelKey: "nav.contractors", icon: Building2, action: "contracts:read" },
  { to: "/tasks", labelKey: "nav.tasks", icon: CalendarCheck, action: "tasks:read" },
  { to: "/favorites", labelKey: "nav.favorites", icon: Star, action: "tools:use" },
  { to: "/cpv", labelKey: "nav.cpv", icon: Search, action: "tools:use" },
  { to: "/search", labelKey: "nav.superSearch", icon: Globe, action: "tools:use" },
  { to: "/generator", labelKey: "nav.docgen", icon: Layers, action: "tools:use" },
  { to: "/analyst", labelKey: "nav.analyst", icon: BarChart3, action: "audit:run" },
  { to: "/audit", labelKey: "nav.riskAudit", icon: ShieldAlert, action: "audit:run" },
  { to: "/plan", labelKey: "nav.plan", icon: ClipboardList, action: "plan:read" },
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
}

/** Targetes del hub de configuració (/admin). */
export const ADMIN_TILES: AdminTile[] = [
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
  },
  {
    to: "/admin/sync",
    labelKey: "nav.sync",
    descriptionKey: "adminHub.sync",
    icon: RefreshCw,
    action: "sync:read",
  },
  {
    to: "/admin/webhooks",
    labelKey: "nav.webhooks",
    descriptionKey: "adminHub.webhooks",
    icon: Webhook,
    action: "webhooks:manage",
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

/** Filtra elements segons les accions de GET /me/permissions. */
export function visibleItems<T extends { action?: string }>(items: T[], actions: string[]): T[] {
  return items.filter((item) => item.action === undefined || actions.includes(item.action));
}

/** El hub de configuració es mostra si l'usuari pot veure alguna targeta. */
export function canSeeAdminHub(actions: string[]): boolean {
  return visibleItems(ADMIN_TILES, actions).length > 0;
}
