// Copies static assets (index.html, CSS, manifest, service worker, worklet, icons) into dist/.
import { cpSync, mkdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
mkdirSync(join(root, "dist"), { recursive: true });
cpSync(join(root, "public"), join(root, "dist"), { recursive: true });
console.log("copied public/ -> dist/");
