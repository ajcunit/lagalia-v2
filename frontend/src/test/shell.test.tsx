import { describe, expect, it } from "vitest";

import { passwordChecklist, passwordSatisfies } from "../auth/passwordChecklist";
import {
  ADMIN_TILES,
  canSeeAdminHub,
  MAIN_NAV,
  visibleItems,
} from "../components/navigation";

describe("navegació per permisos", () => {
  it("un employee sense flags veu operativa i eines però no el hub", () => {
    const actions = ["contracts:read", "tools:use", "me:update"];
    const labels = visibleItems(MAIN_NAV, actions).map((i) => i.labelKey);
    expect(labels).toContain("nav.dashboard");
    expect(labels).toContain("nav.contracts");
    expect(labels).toContain("nav.superSearch");
    expect(labels).not.toContain("nav.riskAudit");
    expect(canSeeAdminHub(actions)).toBe(false);
  });

  it("un admin veu el hub amb totes les targetes", () => {
    const adminActions = ADMIN_TILES.map((tile) => tile.action);
    expect(canSeeAdminHub(adminActions)).toBe(true);
    expect(visibleItems(ADMIN_TILES, adminActions)).toHaveLength(ADMIN_TILES.length);
  });

  it("sense cap acció només queda el tauler i cap hub", () => {
    expect(visibleItems(MAIN_NAV, []).map((i) => i.labelKey)).toEqual(["nav.dashboard"]);
    expect(canSeeAdminHub([])).toBe(false);
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
