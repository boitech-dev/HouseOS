// Runs every tests/*.cjs browser check sequentially against the isolated test app.
// Usage: npm run test:browser [-- name-filter...]
import { mkdirSync, readdirSync } from "node:fs";
import { spawnSync } from "node:child_process";

const filters = process.argv.slice(2);
const files = readdirSync("tests")
  .filter((f) => f.endsWith(".cjs") && f !== "session.cjs")
  .filter((f) => !filters.length || filters.some((x) => f.includes(x)))
  .sort();
// Screenshots and results of this run (git ignores them; tracked evidence/*.png are history).
mkdirSync("evidence/latest", { recursive: true });
const failed = [];
for (const file of files) {
  const started = Date.now();
  const run = spawnSync("node", ["tests/" + file], { encoding: "utf8", timeout: 300000 });
  const ok = run.status === 0;
  const seconds = ((Date.now() - started) / 1000).toFixed(1);
  console.log(`${ok ? "PASS" : "FAIL"} ${file} (${seconds}s)`);
  if (!ok) {
    failed.push(file);
    console.log(
      ((run.stderr || "") + (run.stdout || "") + (run.error?.message || ""))
        .trim()
        .split("\n")
        .slice(-15)
        .map((l) => "    " + l)
        .join("\n"),
    );
  }
}
console.log(
  `\n${files.length - failed.length}/${files.length} passed` +
    (failed.length ? "; failed: " + failed.join(", ") : ""),
);
process.exit(failed.length ? 1 : 0);
