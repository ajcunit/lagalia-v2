import createClient from "openapi-fetch";

import type { paths } from "./generated/schema";

/**
 * Client HTTP tipat, generat del contracte (openapi.yaml).
 * El servidor de l'openapi és /api/v1; en dev, Vite fa proxy de /api.
 */
export const api = createClient<paths>({ baseUrl: "/api/v1" });
