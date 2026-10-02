import { build } from "esbuild";
import { fileURLToPath } from "node:url";

// Leaf sources live outside .dev/frontend/, so explicitly resolve its dependencies.
await build({
  absWorkingDir: fileURLToPath(new URL(".", import.meta.url)),
  entryPoints: ["../../src/scitex_clew/_django/static/clew_app/ts/clew-init.ts"],
  outdir: "../../src/scitex_clew/_django/static/clew_app/js",
  nodePaths: [fileURLToPath(new URL("node_modules", import.meta.url))],
  bundle: true,
  splitting: true,
  format: "esm",
  minify: true,
  target: "es2020",
});
