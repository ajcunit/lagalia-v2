import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    // 127.0.0.1 explícit: a Windows, «localhost» pot resoldre's a ::1 i
    // Vite queda escoltant només IPv6 mentre el navegador ataca IPv4.
    host: "127.0.0.1",
    port: 5173,
    strictPort: true,
    proxy: {
      // En desenvolupament, l'API viu a un altre port; mai URLs incrustades.
      "/api": {
        target: process.env.VITE_API_PROXY_TARGET ?? "http://127.0.0.1:8000",
        changeOrigin: true,
      },
    },
  },
  test: {
    environment: "jsdom",
    setupFiles: ["src/test/setup.ts"],
    globals: false,
  },
});
