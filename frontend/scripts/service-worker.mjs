import { readFile, writeFile, readdir, stat } from "node:fs/promises";
import { createHash } from "node:crypto";
const dist = new URL("../dist", import.meta.url).pathname;
const assets = (await readdir(dist + "/assets")).sort().join(":");
const sw = await readFile(dist + "/sw.js", "utf8");
const hash = createHash("sha256").update(assets + sw);
// /art keeps stable file names, so its bytes must change the cache version too.
for (const name of (await readdir(dist + "/art", { recursive: true })).sort())
  if (!(await stat(dist + "/art/" + name)).isDirectory())
    hash.update(name).update(await readFile(dist + "/art/" + name));
hash.update(await readFile(dist + "/manifest.webmanifest"));
const version = hash.digest("hex").slice(0, 16);
const chunks = (await readdir(dist + "/assets"))
  .filter((name) => /\.(js|css)$/.test(name))
  .map((name) => "/assets/" + name);
await writeFile(
  dist + "/sw.js",
  sw
    .replace("HOUSEOS_SHELL_VERSION", "houseos-shell-" + version)
    .replace("/* HOUSEOS_CHUNKS */ []", JSON.stringify(chunks)),
);
