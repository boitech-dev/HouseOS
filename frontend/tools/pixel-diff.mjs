// Compare two folders of screenshots (same names): the share of pixels that changed, per image.
//   node tools/pixel-diff.mjs <before> <after> [--max 0.5] [--diffs <folder>]
// Exits 1 when any image changed more than --max percent (a size change counts as 100 %).
import { createRequire } from "node:module";
import { mkdirSync, readdirSync, readFileSync, statSync, writeFileSync } from "node:fs";
import { join } from "node:path";
const { PNG } = createRequire(import.meta.url)("pngjs");
const [before, after] = process.argv.slice(2);
const opt = (name, fallback) => {
  const i = process.argv.indexOf("--" + name);
  return i > 0 ? process.argv[i + 1] : fallback;
};
const max = Number(opt("max", "0.5"));
const diffs = opt("diffs", "");
const files = (dir) =>
  readdirSync(dir, { recursive: true }).filter(
    (f) => f.endsWith(".png") && statSync(join(dir, f)).isFile(),
  );
let worst = 0;
const rows = [];
for (const name of files(before).sort()) {
  let a, b;
  try {
    [a, b] = [before, after].map((dir) => PNG.sync.read(readFileSync(join(dir, name))));
  } catch {
    rows.push([name, 100, "missing"]);
    worst = 100;
    continue;
  }
  if (a.width !== b.width || a.height !== b.height) {
    rows.push([name, 100, `size ${a.width}×${a.height} → ${b.width}×${b.height}`]);
    worst = 100;
    continue;
  }
  const mark = new PNG({ width: a.width, height: a.height });
  let changed = 0;
  for (let i = 0; i < a.data.length; i += 4) {
    const moved = [0, 1, 2].some((c) => Math.abs(a.data[i + c] - b.data[i + c]) > 8);
    if (moved) changed++;
    mark.data.set(
      moved ? [255, 0, 160, 255] : [a.data[i] / 3, a.data[i + 1] / 3, a.data[i + 2] / 3, 255],
      i,
    );
  }
  const share = (100 * changed) / (a.width * a.height);
  worst = Math.max(worst, share);
  rows.push([name, share, ""]);
  if (diffs && share > 0) {
    mkdirSync(join(diffs, name, ".."), { recursive: true });
    writeFileSync(join(diffs, name), PNG.sync.write(mark));
  }
}
for (const [name, share, note] of rows.sort((x, y) => y[1] - x[1]))
  console.log(
    `${share > max ? "✗" : "✓"} ${share.toFixed(2).padStart(6)} %  ${name}${note ? "  " + note : ""}`,
  );
console.log(`worst ${worst.toFixed(2)} % (allowed ${max} %)`);
process.exit(worst > max ? 1 : 0);
