/** Catàleg català. La UI només fa servir claus; mai strings incrustats. */
export const ca = {
  "app.name": "LAGALia",
  "app.tagline": "Gestió de contractació pública de l'Ajuntament de Cunit",
  "app.skipToContent": "Vés al contingut",
  "home.apiStatus": "Estat de l'API",
  "home.apiVersion": "Versió {version}",
  "home.apiOnline": "Operativa",
  "home.apiOffline": "No disponible",
  "home.apiChecking": "Comprovant…",
  "home.setupStatus": "Estat del sistema",
  "home.needsSetup": "Pendent d'inicialitzar",
  "home.ready": "Inicialitzat",
  "home.phase": "Fase 0 — esquelet",
  "notFound.title": "Pàgina no trobada",
  "notFound.description": "L'adreça que has escrit no correspon a cap pantalla.",
  "notFound.backHome": "Torna a l'inici",
  "theme.toggle": "Canvia el tema",
  "theme.light": "Tema clar",
  "theme.dark": "Tema fosc",
} as const;

export type TranslationKey = keyof typeof ca;
