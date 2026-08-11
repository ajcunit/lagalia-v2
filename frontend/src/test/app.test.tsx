import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";

import { ThemeToggle } from "../components/ThemeToggle";
import { t } from "../i18n";
import { NotFound } from "../routes/NotFound";

describe("i18n", () => {
  it("resol claus i paràmetres", () => {
    expect(t("app.name")).toBe("LAGALia");
    expect(t("home.apiVersion", { version: "0.1.0" })).toBe("Versió 0.1.0");
  });
});

describe("NotFound", () => {
  it("mostra la pàgina 404 amb enllaç a l'inici", () => {
    render(
      <MemoryRouter>
        <NotFound />
      </MemoryRouter>,
    );

    expect(screen.getByRole("heading", { name: t("notFound.title") })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: t("notFound.backHome") })).toHaveAttribute(
      "href",
      "/",
    );
  });
});

describe("ThemeToggle", () => {
  it("alterna el tema i el persisteix", async () => {
    document.documentElement.dataset.theme = "light";
    const user = userEvent.setup();
    render(<ThemeToggle />);

    await user.click(screen.getByRole("button", { name: t("theme.toggle") }));

    expect(document.documentElement.dataset.theme).toBe("dark");
    expect(localStorage.getItem("lagalia.theme")).toBe("dark");

    await user.click(screen.getByRole("button", { name: t("theme.toggle") }));
    expect(document.documentElement.dataset.theme).toBe("light");
  });
});
