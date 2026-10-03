// The design system's guards (docs/design/SYSTEM.md): every visual value comes from a token,
// every stylesheet declares its layer, rooms use the design system's controls, no emoji as icons.
// Any problem fails the build. `--census` prints the counts of each kind.
import { readFileSync, readdirSync } from "node:fs";
import { join, relative } from "node:path";

const src = new URL("../src/", import.meta.url).pathname;
const files = readdirSync(src, { recursive: true })
  .map((f) => join(src, f))
  .filter((f) => /\.(css|tsx?)$/.test(f) && !f.includes("/generated/"));
const rel = (f) => relative(src, f);

// Values a token must provide, by property; keywords that mean "no value" are fine.
const COLOUR = /#[0-9a-f]{3,8}\b|\b(?:rgba?|hsla?|oklch|oklab|lab|lch|hwb)\(/i;
const PROPS = {
  colour: /^(color|background(-color)?|border(-(top|right|bottom|left|block|inline))?(-color)?|outline(-color)?|fill|stroke|caret-color|accent-color|text-decoration-color|column-rule-color|box-shadow|text-shadow)$/,
  "font-size": /^font-size$/,
  "font-family": /^font-family$/,
  radius: /^border(-(top|bottom|start|end)-(left|right|start|end))?-radius$/,
  shadow: /^(box-shadow|text-shadow)$/,
  "z-index": /^z-index$/,
  duration: /^(transition(-duration)?|animation(-duration)?)$/,
};
const SIZED = /^(width|height|min-width|min-height|max-width|max-height|flex|flex-basis|gap|row-gap|column-gap|padding(-[a-z-]+)?|margin(-[a-z-]+)?|grid-template-columns|grid-template-rows|inset|top|right|bottom|left)$/;
const FREE = /^(inherit|initial|unset|revert|currentcolor|transparent|none|0|0px|auto|normal)$/i;
const BREAKPOINTS = new Set(["599.98px", "600px", "899.98px", "900px", "1231.98px", "1232px", "1599.98px", "1600px"]);
// Emoji used as pictures (people and objects), not the arrows or check marks of plain text.
const EMOJI = /\p{Extended_Pictographic}/u;
const PLAIN = /[←→↑↓↔✓✗×·•…©®™]/u;

function cssProblems(text) {
  const out = [];
  if (!/^\s*(\/\*[\s\S]*?\*\/\s*)*@layer\s+[a-z-]+(\s*,\s*[a-z-]+)*\s*[{;]/.test(text)) out.push("no @layer");
  for (const m of text.matchAll(/(?:^|[;{\s])([a-z-]+)\s*:\s*([^;{}]+?)\s*(?:;|})/g)) {
    const [, prop, value] = m;
    if (prop.startsWith("--")) continue;
    const bare = value.replace(/var\([^()]*(\([^()]*\)[^()]*)*\)/g, "").replace(/!important/, "").trim();
    for (const [kind, pattern] of Object.entries(PROPS)) {
      if (!pattern.test(prop)) continue;
      if (kind === "colour" && COLOUR.test(bare)) out.push(`${prop}: ${value} (colour)`);
      else if (kind === "font-size" && /\d/.test(bare) && !FREE.test(bare)) out.push(`${prop}: ${value}`);
      else if (kind === "font-family" && bare && !FREE.test(bare)) out.push(`${prop}: ${value}`);
      else if (kind === "radius" && /[1-9]/.test(bare)) out.push(`${prop}: ${value}`);
      else if (kind === "shadow" && bare && !FREE.test(bare) && /\d/.test(bare)) out.push(`${prop}: ${value}`);
      else if (kind === "z-index" && /\d/.test(bare)) out.push(`${prop}: ${value}`);
      else if (kind === "duration" && /\d(m?s)\b/.test(bare)) out.push(`${prop}: ${value}`);
    }
    // Sizes never follow a theme's face: no em/lh/ex lengths (rem is the browser's, px is fixed).
    // The one exception centres a single line in a fixed box.
    if (SIZED.test(prop) && /[\d.](em|lh|ex)\b/.test(value.replace("calc((40px - 1lh) / 2)", "")))
      out.push(`${prop}: ${value} (a size in em/lh follows the theme's type)`);
  }
  for (const m of text.matchAll(/@(?:media|container)[^{]*?\((?:min|max)-width:\s*([\d.]+px)\)/g))
    if (!BREAKPOINTS.has(m[1])) out.push(`breakpoint ${m[1]} (use 600, 900, 1232 or 1600)`);
  return out;
}

function tsProblems(text, file) {
  const out = [];
  const code = text.replace(/\/\*[\s\S]*?\*\/|\/\/[^\n]*/g, "");
  for (const m of code.matchAll(/["'`]([^"'`\n]*)["'`]/g))
    if (COLOUR.test(m[1]) && !/^(image|data):/.test(m[1])) out.push(`colour literal ${m[0]}`);
  if (file.endsWith(".tsx") && !file.startsWith("design/")) {
    for (const m of code.matchAll(/<(button|input|select|textarea|dialog)\b/g)) out.push(`raw <${m[1]}>`);
    for (const m of code.matchAll(/style=\{\{([^}]*)\}\}/g))
      for (const key of m[1].matchAll(/(?:^|,)\s*("?)([\w-]+)\1\s*:/g))
        if (!key[2].startsWith("--")) out.push(`inline style ${key[2]}`);
  }
  for (const line of code.split("\n"))
    for (const char of line.match(new RegExp(EMOJI.source, "gu")) ?? [])
      if (!PLAIN.test(char) && !/emoji/i.test(file)) out.push(`emoji ${char}`);
  return out;
}

let errors = 0;
const census = { files: 0, classes: new Set(), selectors: 0, colours: 0, buttons: 0, breakpoints: new Set() };
for (const file of files.sort()) {
  const name = rel(file);
  const text = readFileSync(file, "utf8");
  if (name === "design/layers.css") continue;
  const problems = file.endsWith(".css") ? cssProblems(text) : tsProblems(text, name);
  census.files++;
  census.colours += (text.match(new RegExp(COLOUR.source, "gi")) ?? []).length;
  if (file.endsWith(".css")) {
    census.selectors += (text.match(/[^{}]+\{/g) ?? []).filter((s) => !s.trim().startsWith("@")).length;
    for (const m of text.matchAll(/@media[^{]*?\(\s*(?:min|max)-width:\s*([\d.]+px)/g)) census.breakpoints.add(m[1]);
  } else {
    census.buttons += (text.match(/<button\b/g) ?? []).length;
    for (const m of text.matchAll(/className=(?:"([^"]*)"|\{`([^`]*)`\})/g))
      for (const c of (m[1] ?? m[2]).split(/\s+/)) if (/^[a-z][\w-]*$/.test(c)) census.classes.add(c);
  }
  errors += problems.length;
  for (const p of problems.slice(0, 20)) console.error(`design-check: ${name}: ${p}`);
}
if (process.argv.includes("--census"))
  console.log(
    JSON.stringify(
      {
        files: census.files,
        classNames: census.classes.size,
        cssSelectors: census.selectors,
        colourLiterals: census.colours,
        rawButtons: census.buttons,
        breakpoints: [...census.breakpoints].sort((a, b) => parseFloat(a) - parseFloat(b)),
      },
      null,
      2,
    ),
  );
console.log(`design-check: ${errors} error(s)`);
process.exit(errors ? 1 : 0);
