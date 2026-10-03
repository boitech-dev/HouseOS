import { realpathSync } from "node:fs";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import french from "./src/locale_fr";

export default defineConfig({
  plugins: [
    react(),
    {
      // Every interface text (English, with the French as a hint) for the server, which has
      // Nox's AI translate them when the house adds a language (backend/houseos/languages.py).
      name: "ui-strings",
      generateBundle() {
        this.emitFile({
          type: "asset",
          fileName: "ui-strings.json",
          source: JSON.stringify(french),
        });
      },
    },
  ],
  // The local dev run (`tools/local.py run`, port 8990); HOUSEOS_API points elsewhere on purpose,
  // e.g. an isolated test app. Never a house people live in.
  // /themes: the themes' pictures and installed themes' stylesheets, served by the house.
  // fs.allow: the themes' own fonts (../themes) and node_modules where it really lives (a link).
  server: {
    port: 5176,
    fs: { allow: ["..", realpathSync("node_modules")] },
    proxy: Object.fromEntries(
      ["/api", "/themes"].map((path) => [path, process.env.HOUSEOS_API ?? "http://127.0.0.1:8990"]),
    ),
  },
  build: {
    // iPhones and iPads that stopped at iOS 15 still open the app (Vite's default is Safari 16).
    target: ["es2020", "safari15"],
    // Fonts stay files: the app's CSP (font-src 'self') refuses the data: URLs Vite inlines small ones as.
    assetsInlineLimit: (file: string) => (file.endsWith(".woff2") ? false : undefined),
    outDir: "dist",
    emptyOutDir: true,
  },
});
