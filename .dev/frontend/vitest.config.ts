import { defineConfig } from "vitest/config";
import { fileURLToPath } from "node:url";
import { createRequire } from "node:module";

const root = fileURLToPath(new URL("../..", import.meta.url));
const require = createRequire(import.meta.url);

export default defineConfig({
  root,
  cacheDir: fileURLToPath(new URL("node_modules/.vite", import.meta.url)),
  server: { fs: { allow: [root] } },
  resolve: { alias: { mermaid: require.resolve("mermaid") } },
  test: { environment: "jsdom", include: ["tests/scitex_clew/_django/**/*.test.ts"] },
});
