import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import axe from "axe-core";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";

import { Home } from "../../routes/Home";
import { NotFound } from "../../routes/NotFound";

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

  it("Home sense violacions", async () => {
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    const { container } = render(
      <QueryClientProvider client={queryClient}>
        <Home />
      </QueryClientProvider>,
    );
    await expectNoViolations(container);
  });
});
