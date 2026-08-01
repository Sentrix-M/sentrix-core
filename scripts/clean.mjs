#!/usr/bin/env node
/**
 * Sentrix monorepo — cross-platform clean script.
 *
 * Removes build artifacts and caches produced by the toolchain:
 *   - node_modules/                 (dependencies)
 *   - node_modules inside apps      (nested workspace deps)
 *   - node_modules inside packages  (nested workspace deps)
 *   - .turbo/                       (Turbo cache)
 *   - .next/                        (Next.js build output)
 *   - dist/ build/ out/             (generic build outputs)
 *   - *.tsbuildinfo                 (TypeScript incremental build cache)
 *
 * Cross-platform note: uses only Node.js APIs (no rm -rf) so it works on
 * Windows (cmd/PowerShell), Linux, and macOS.
 */
import { existsSync, readdirSync, rmSync } from "node:fs";
import { join, resolve } from "node:path";

const root = resolve(import.meta.dirname, "..");

/** Recursively collect directories to remove relative to root. */
function collectTargets() {
  const targets = ["node_modules", ".turbo", "dist", "build", "out", ".next"];
  const found = [];
  const scanned = new Set();

  function scan(dir) {
    if (scanned.has(dir)) return;
    scanned.add(dir);

    let entries = [];
    try {
      entries = readdirSync(dir, { withFileTypes: true });
    } catch {
      return;
    }

    for (const entry of entries) {
      const full = join(dir, entry.name);
      if (targets.includes(entry.name)) {
        found.push(full);
        continue;
      }
      if (entry.isDirectory() && !entry.name.startsWith(".")) {
        scan(full);
      }
    }
  }

  scan(root);

  // Remove all *.tsbuildinfo files as well.
  return { found, tsbuildinfo: [] };
}

function collectTsBuildInfo() {
  const files = [];
  const scanned = new Set();

  function scan(dir) {
    if (scanned.has(dir)) return;
    scanned.add(dir);

    let entries = [];
    try {
      entries = readdirSync(dir, { withFileTypes: true });
    } catch {
      return;
    }

    for (const entry of entries) {
      const full = join(dir, entry.name);
      if (entry.isDirectory() && !entry.name.startsWith(".")) {
        scan(full);
      } else if (entry.name.endsWith(".tsbuildinfo")) {
        files.push(full);
      }
    }
  }

  scan(root);
  return files;
}

const { found } = collectTargets();
const tsbuildinfo = collectTsBuildInfo();

let removed = 0;
for (const target of [...found, ...tsbuildinfo]) {
  if (existsSync(target)) {
    rmSync(target, { recursive: true, force: true });
    const relative = target.replace(`${root}\\`, "").replace(`${root}/`, "");
    console.log(`removed  ${relative}`);
    removed += 1;
  }
}

console.log(`\nClean complete: removed ${removed} artifact(s).`);
