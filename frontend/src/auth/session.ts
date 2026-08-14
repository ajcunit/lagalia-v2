/**
 * Gestió de sessió (spec login-shell.md):
 * - refresh token persistit a localStorage; token d'accés NOMÉS en memòria.
 * - restauració en carregar (refresh amb rotació).
 * - middleware: adjunta Authorization i, en 401 d'una petició GET,
 *   refresca una vegada i reintenta.
 */

import createClient from "openapi-fetch";

import { api } from "../api/client";
import type { paths } from "../api/generated/schema";

const REFRESH_KEY = "lagalia.refreshToken";

let accessToken: string | null = null;
let expiredCallback: (() => void) | null = null;

// Client sense middleware per a /auth/refresh (evita recursió).
const bareClient = createClient<paths>({ baseUrl: "/api/v1" });

interface TokenPair {
  access_token: string;
  refresh_token: string;
}

export function getAccessToken(): string | null {
  return accessToken;
}

export function setSession(pair: TokenPair): void {
  accessToken = pair.access_token;
  localStorage.setItem(REFRESH_KEY, pair.refresh_token);
}

export function clearSession(): void {
  accessToken = null;
  localStorage.removeItem(REFRESH_KEY);
}

export function hasAccessToken(): boolean {
  return accessToken !== null;
}

export function onSessionExpired(callback: () => void): void {
  expiredCallback = callback;
}

let inflightRestore: Promise<boolean> | null = null;

/** Restaura (o rota) la sessió amb el refresh token persistit.
 *
 * Single-flight: dues crides simultànies (StrictMode, dos 401 alhora)
 * comparteixen la mateixa rotació — si no, la segona reutilitzaria el
 * token acabat de rotar i la detecció de robatori revocaria la família.
 */
export function restoreSession(): Promise<boolean> {
  inflightRestore ??= doRestore().finally(() => {
    inflightRestore = null;
  });
  return inflightRestore;
}

async function doRestore(): Promise<boolean> {
  const refreshToken = localStorage.getItem(REFRESH_KEY);
  if (!refreshToken) return false;
  const { data, error } = await bareClient.POST("/auth/refresh", {
    body: { refresh_token: refreshToken },
  });
  if (error !== undefined || data === undefined) {
    clearSession();
    return false;
  }
  setSession(data);
  return true;
}

api.use({
  onRequest({ request }) {
    if (accessToken !== null && !request.headers.has("Authorization")) {
      request.headers.set("Authorization", `Bearer ${accessToken}`);
    }
    return request;
  },
  async onResponse({ request, response }) {
    const isAuthEndpoint = new URL(request.url).pathname.includes("/auth/");
    if (response.status !== 401 || isAuthEndpoint) return response;

    if (await restoreSession()) {
      // Només reintentem peticions sense cos (el body ja s'ha consumit).
      if (request.method === "GET" || request.method === "HEAD") {
        const retry = new Request(request.url, {
          method: request.method,
          headers: new Headers(request.headers),
        });
        retry.headers.set("Authorization", `Bearer ${accessToken}`);
        return fetch(retry);
      }
      return response;
    }
    expiredCallback?.();
    return response;
  },
});
