import type { TranslationKey } from "../i18n/ca";

export interface NavItem {
  to: string;
  labelKey: TranslationKey;
  /** Acció de la matriu A2 necessària; sense acció = visible per a tothom. */
  action?: string;
}

export interface NavZone {
  labelKey: TranslationKey;
  items: NavItem[];
}

/** Zones de docs/10-ui.md §3. Les rutes de fases futures existeixen com a
 * pantalles «en construcció» perquè la navegació ja sigui la definitiva. */
export const NAV_ZONES: NavZone[] = [
  {
    labelKey: "nav.zone.operations",
    items: [
      { to: "/", labelKey: "nav.dashboard" },
      { to: "/contracts", labelKey: "nav.contracts", action: "contracts:read" },
      { to: "/minor-contracts", labelKey: "nav.minorContracts", action: "minor_contracts:read" },
      { to: "/contractors", labelKey: "nav.contractors", action: "contracts:read" },
      { to: "/tasks", labelKey: "nav.tasks", action: "tasks:read" },
    ],
  },
  {
    labelKey: "nav.zone.intelligence",
    items: [{ to: "/search", labelKey: "nav.superSearch", action: "tools:use" }],
  },
  {
    labelKey: "nav.zone.administration",
    items: [
      { to: "/contractors/duplicates", labelKey: "nav.duplicates", action: "duplicates:manage" },
      { to: "/admin/users", labelKey: "nav.users", action: "users:read" },
      { to: "/admin/departments", labelKey: "nav.departments", action: "departments:write" },
      { to: "/admin/webhooks", labelKey: "nav.webhooks", action: "webhooks:manage" },
      { to: "/admin/config", labelKey: "nav.config", action: "config:write" },
      { to: "/admin/audit-log", labelKey: "nav.securityAudit", action: "audit_log:read" },
    ],
  },
];

/** Filtra la navegació amb les accions de GET /me/permissions. */
export function visibleZones(zones: NavZone[], actions: string[]): NavZone[] {
  return zones
    .map((zone) => ({
      ...zone,
      items: zone.items.filter(
        (item) => item.action === undefined || actions.includes(item.action),
      ),
    }))
    .filter((zone) => zone.items.length > 0);
}
