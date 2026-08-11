import "@testing-library/jest-dom/vitest";

import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

// Sense "globals", Testing Library no es neteja sola entre tests.
afterEach(cleanup);
