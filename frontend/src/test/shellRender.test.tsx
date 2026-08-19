import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

vi.mock("../auth/AuthProvider", () => ({
  useAuth: () => ({
    user: { name: "Esteve Tintó", role: "admin", email: "e@cunit.cat" },
    permissions: {
      actions: [
        "contracts:read",
        "tools:use",
        "users:read",
        "departments:write",
        "config:write",
        "audit_log:read",
        "sync:read",
        "webhooks:manage",
        "service_accounts:manage",
        "duplicates:manage",
      ],
    },
    logout: vi.fn(),
  }),
}));

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import { Shell } from "../components/Shell";
import { ViewProvider } from "../view/ViewProvider";

describe("Shell", () => {
  it("mostra l'entrada de Configuració per a un admin", () => {
    render(
      <QueryClientProvider client={new QueryClient()}>
        <MemoryRouter>
          <ViewProvider>
            <Shell />
          </ViewProvider>
        </MemoryRouter>
      </QueryClientProvider>,
    );
    expect(screen.getByRole("link", { name: /Configuració/i })).toBeTruthy();
    expect(screen.getByRole("link", { name: /Contractació/i })).toBeTruthy();
  });
});
