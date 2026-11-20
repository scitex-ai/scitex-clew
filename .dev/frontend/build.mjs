import { build } from "esbuild";
import { fileURLToPath } from "node:url";
import { readdir, unlink } from "node:fs/promises";
import { join } from "node:path";

const output = fileURLToPath(new URL("../../src/scitex_clew/_django/static/clew_app/js", import.meta.url));
for (const name of await readdir(output)) {
  if (name.endsWith(".js") || name.endsWith(".js.LEGAL.txt")) await unlink(join(output, name));
}

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
