// Copies third-party browser bundles from node_modules into static/vendor so
// they are served by Django (no CDN, works offline, pinned by package-lock).
import { copyFileSync, mkdirSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const out = resolve(root, "static/vendor");
mkdirSync(out, { recursive: true });

const files = {
  "htmx.org/dist/htmx.min.js": "htmx.min.js",
  "chart.js/dist/chart.umd.min.js": "chart.umd.min.js",
  // Source map referenced by the bundle; needed by the hashed static manifest.
  "chart.js/dist/chart.umd.min.js.map": "chart.umd.min.js.map",
};

for (const [src, dest] of Object.entries(files)) {
  copyFileSync(resolve(root, "node_modules", src), resolve(out, dest));
  console.log(`vendored ${src} -> static/vendor/${dest}`);
}
