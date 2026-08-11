import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import axe from "axe-core";
import type { ReactNode } from "react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";

import { AuthProvider } from "../../auth/AuthProvider";
import { Login } from "../../routes/Login";
import { NotFound } from "../../routes/NotFound";
import { Setup } from "../../routes/Setup";

function Providers({ children }: { children: ReactNode }) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return (
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <AuthProvider>{children}</AuthProvider>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

async function expectNoViolations(container: HTMLElement): Promise<void> {
  const results = await axe.run(container, {
    // El contrast es valida als tokens (spec); jsdom no calcula estils reals.
    rules: { "color-contrast": { enabled: false } },
  });
  expect(results.violations).toEqual([]);
}

describe("a11y (axe)", () => {
  it("NotFound sense violacions", async () => {
    const { container } = render(
      <MemoryRouter>
        <NotFound />
      </MemoryRouter>,
    );
    await expectNoViolations(container);
  });

  it("Login sense violacions", async () => {
    const { container } = render(
      <Providers>
        <Login />
      </Providers>,
    );
    await expectNoViolations(container);
  });

  it("Setup (pas de compte d'administració) sense violacions", async () => {
    const { container, getByText } = render(
      <Providers>
        <Setup />
      </Providers>,
    );
    getByText("Comença").click();
    await expectNoViolations(container);
  });
});
