import { describe, expect, it } from "vitest";

import { formatCurrency, formatDate, formatDuration } from "../lib/format";

describe("formats ca-ES centralitzats", () => {
  it("formatCurrency", () => {
    const normalize = (value: string) => value.replace(/[  ]/g, " ");
    expect(normalize(formatCurrency("1234567.5"))).toBe("1.234.567,50 €");
    expect(normalize(formatCurrency(1000))).toBe("1.000,00 €");
    expect(formatCurrency(null)).toBe("—");
    expect(formatCurrency("no-numero")).toBe("—");
  });

  it("formatDate", () => {
    expect(formatDate("2026-01-15")).toMatch(/15/);
    expect(formatDate("2026-01-15")).toMatch(/2026/);
    expect(formatDate(null)).toBe("—");
    expect(formatDate("data-dolenta")).toBe("—");
  });

  it("formatDuration", () => {
    expect(formatDuration(12)).toBe("1 any");
    expect(formatDuration(27)).toBe("2 anys i 3 mesos");
    expect(formatDuration(1)).toBe("1 mes");
    expect(formatDuration(null)).toBe("—");
    expect(formatDuration(0)).toBe("—");
  });
});
