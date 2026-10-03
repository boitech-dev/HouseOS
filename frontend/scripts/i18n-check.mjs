// Fails the build when a literal t("…") string has no French translation.
// Dictionaries are TypeScript modules; Node 22 strips their types on import.
import { readdirSync, readFileSync } from "node:fs";
const load = async (name) => (await import(new URL(`../src/${name}`, import.meta.url))).default;
const dictionary = await load("locale_fr.ts");
const normalize = (text) => text.replace(/\s+/g, " ").trim();
// Names and formats that read the same in French.
const same = [
  "MIDNIGHT HOUSE",
  "YouTube",
  "SoundCloud",
  "4K",
  "1080p",
  "720p",
  "HDR",
  "Chromecast",
  "HouseOS — Claude Code sign in",
];
// t(cond ? "A" : "B"), nested choices included, whatever the condition holds (quotes, calls):
// every literal right after a ? or : (outside strings) is a branch shown to someone.
function choices(source) {
  const found = [];
  for (const m of source.matchAll(/\bt\(/g)) {
    let depth = 1,
      prev = "";
    for (let i = m.index + m[0].length; i < source.length && depth; i++) {
      const c = source[i];
      if (c === '"' || c === "'" || c === "`") {
        let j = i + 1;
        while (j < source.length && source[j] !== c) j += source[j] === "\\" ? 2 : 1;
        if (c === '"' && (prev === "?" || prev === ":")) found.push(source.slice(i + 1, j));
        prev = c;
        i = j;
        continue;
      }
      if (c === "(") depth++;
      else if (c === ")") depth--;
      if (!/\s/.test(c)) prev = c;
    }
  }
  return found;
}
const known = new Set([...Object.keys(dictionary), ...same].map(normalize));
const missing = new Map();
for (const file of readdirSync(new URL("../src", import.meta.url), { recursive: true })) {
  if (!/\.tsx?$/.test(file) || file.includes("generated/")) continue;
  const source = readFileSync(new URL(`../src/${file}`, import.meta.url), "utf8");
  const literals = [
    // (a trailing comma too: prettier adds one after a long literal on its own line)
    ...[...source.matchAll(/\bt\(\s*"((?:[^"\\]|\\.)*)"\s*,?\s*\)/g)].map((m) => m[1]),
    ...choices(source),
  ];
  for (const literal of literals) {
    const text = normalize(JSON.parse(`"${literal}"`));
    if (text && !known.has(text)) missing.set(text, file);
  }
  // Errors reach people too: a thrown or shown failure's own words go through t().
  for (const m of source.matchAll(/\b(?:new Error|setError|setFailure|setProblem)\(\s*"([^"]+)"/g))
    missing.set(`${m[1]} (wrap it in t())`, file);
}
// Themes' own words (themes/*/flavor.json): English and French for every one.
const themes = new URL("../../themes/", import.meta.url);
for (const id of readdirSync(themes).filter((name) => !name.startsWith("_"))) {
  let flavor = {};
  try {
    flavor = JSON.parse(readFileSync(new URL(`${id}/flavor.json`, themes), "utf8"));
  } catch {
    continue;
  }
  for (const [key, texts] of Object.entries(flavor))
    if (!key.startsWith("$") && !(texts?.en?.trim() && texts?.fr?.trim()))
      missing.set(`${key} (en and fr)`, `themes/${id}/flavor.json`);
}
// And the other way: an entry no code, server message or theme uses any more is dead weight.
// (Keys built at runtime are listed here: the avatar names, t(Capitalised id) in me.tsx.)
const built = ["Moon", "Bat", "Crest", "Raven", "Rose", "Ghost"];
const sources = (dir, test) =>
  readdirSync(new URL(dir, import.meta.url), { recursive: true })
    .filter((f) => test.test(f) && !/locale_fr|generated\//.test(f))
    .map((f) => readFileSync(new URL(`${dir}/${f}`, import.meta.url), "utf8"));
const used = [
  ...sources("../src", /\.tsx?$/),
  ...sources("../../backend/houseos", /\.py$/),
  ...sources("../../themes", /\.json$/),
]
  .join("\n")
  .replace(/\s+/g, " ");
const unused = Object.keys(dictionary).filter(
  (key) =>
    !built.includes(key) &&
    !used.includes(normalize(key)) &&
    !used.includes(JSON.stringify(key).slice(1, -1)),
);
for (const key of unused) console.error(`unused French entry: ${JSON.stringify(key)}`);
// French typography: the curly apostrophe (l’heure), and a narrow no-break space (U+202F)
// before : ; ? ! (never inside https:// or a time like 04:15).
const typography = /(?<=\p{L})'(?=\p{L})|[ \u00a0][:;?!]|[\p{L}\d)»][;?!]|\p{L}:(?![/\d])/u;
for (const [key, french] of Object.entries(dictionary))
  if (typography.test(french)) {
    console.error(`French typography (’ and U+202F before : ; ? !): ${JSON.stringify(key)}`);
    process.exitCode = 1;
  }
if (process.exitCode) process.exit(1);
if (unused.length) {
  console.error(`${unused.length} French entr(ies) no longer used: remove them`);
  process.exit(1);
}
if (missing.size) {
  for (const [text, file] of missing)
    console.error(`missing French: ${JSON.stringify(text)} (${file})`);
  console.error(`${missing.size} string(s) need a French entry in src/locale_fr.ts`);
  process.exit(1);
}
console.log(`i18n: ${known.size} French entries cover every literal t() string`);
