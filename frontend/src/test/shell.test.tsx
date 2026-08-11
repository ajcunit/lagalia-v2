import { describe, expect, it } from "vitest";

import { passwordChecklist, passwordSatisfies } from "../auth/passwordChecklist";
import { NAV_ZONES, visibleZones } from "../components/navigation";

describe("visibleZones", () => {
  it("un employee sense flags només veu tauler i superbuscador", () => {
    const zones = visibleZones(NAV_ZONES, ["contracts:read", "tools:use", "me:update"]);

    const labels = zones.flatMap((z) => z.items.map((i) => i.labelKey));
    expect(labels).toContain("nav.dashboard");
    expect(labels).toContain("nav.contracts");
    expect(labels).toContain("nav.superSearch");
    expect(labels).not.toContain("nav.users");
    expect(labels).not.toContain("nav.securityAudit");
    // La zona d'administració desapareix sencera.
    expect(zones.map((z) => z.labelKey)).not.toContain("nav.zone.administration");
  });

  it("un admin ho veu tot", () => {
    const adminActions = [
      "contracts:read",
      "tools:use",
      "users:read",
      "departments:write",
      "config:write",
      "audit_log:read",
    ];

    const zones = visibleZones(NAV_ZONES, adminActions);

    const labels = zones.flatMap((z) => z.items.map((i) => i.labelKey));
    expect(labels).toContain("nav.users");
    expect(labels).toContain("nav.securityAudit");
  });

  it("sense cap acció només queden les entrades sense requisit", () => {
    const zones = visibleZones(NAV_ZONES, []);

    const labels = zones.flatMap((z) => z.items.map((i) => i.labelKey));
    expect(labels).toEqual(["nav.dashboard"]);
  });
});

describe("passwordChecklist", () => {
  it("marca cada requisit per separat", () => {
    const short = passwordChecklist("aB1");
    expect(short.find((i) => i.labelKey === "setup.password.length")?.ok).toBe(false);
    expect(short.find((i) => i.labelKey === "setup.password.upper")?.ok).toBe(true);
    expect(short.find((i) => i.labelKey === "setup.password.digit")?.ok).toBe(true);
  });

  it("passwordSatisfies coincideix amb la política", () => {
    expect(passwordSatisfies("Contrasenya-Robusta-42")).toBe(true);
    expect(passwordSatisfies("totminuscules123")).toBe(false);
    expect(passwordSatisfies("Curta1")).toBe(false);
  });
});
