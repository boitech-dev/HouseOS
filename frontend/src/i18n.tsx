import { createContext, useContext, useState, type ReactNode } from "react";
/** "en", "fr" (built in) or a language the house added (translated once by Nox's AI). */
export type Language = string;
// Built-in dictionaries load only for the people who use them (the French is ~250 KB).
const builtIn: Record<string, () => Promise<Record<string, string>>> = {
  fr: () => import("./locale_fr").then((m) => m.default),
};
const pending: Record<string, Promise<Record<string, string>>> = {};
const loadBuiltIn = (value: string) =>
  (pending[value] ||= builtIn[value]().catch((error) => {
    delete pending[value];
    throw error;
  }));
let translations: Record<string, string> = {};
let currentLanguage: Language = "en";
export function getLanguage() {
  return currentLanguage;
}
export function t(text: string): string {
  if (currentLanguage === "en") return text;
  const key = text.replace(/\s+/g, " ").trim();
  const result = translations[key];
  return result === undefined
    ? text
    : (/^\s/.test(text) ? " " : "") + result + (/\s$/.test(text) ? " " : "");
}
function use(value: Language, strings: Record<string, string>) {
  translations = strings;
  currentLanguage = value;
  document.documentElement.lang = value;
  try {
    localStorage.setItem("houseos-language", value);
  } catch {}
}
/** Before the first render: the device's last built-in language, so French paints in French. */
export function restoreLanguage(): Promise<void> {
  let value = "en";
  try {
    value = localStorage.getItem("houseos-language") || "en";
  } catch {}
  return builtIn[value]
    ? loadBuiltIn(value)
        .then((strings) => use(value, strings))
        .catch(() => {})
    : Promise.resolve();
}
const I18n = createContext({
  language: "en" as Language,
  t,
  setLanguage: (_language: string) => {},
});
let requested = "";
export function I18nProvider({ children }: { children: ReactNode }) {
  const [language, update] = useState<Language>(currentLanguage);
  function apply(value: Language, strings: Record<string, string>) {
    if (value !== requested && requested) return; // a later choice already won
    use(value, strings);
    update(value);
  }
  function setLanguage(asked: string) {
    const value = (requested = /^[a-z]{2,3}$/.test(asked) ? asked : "en");
    if (value === "en") return apply(value, {});
    // Built-in languages load their chunk; an added one gets its texts from the house.
    // English until they arrive.
    void (
      builtIn[value]
        ? loadBuiltIn(value)
        : fetch("/api/v1/languages/" + value + "/strings", { credentials: "same-origin" }).then(
            (response) => (response.ok ? response.json() : Promise.reject()),
          )
    )
      .then((strings) => apply(value, strings))
      .catch(() => {
        requested = "en";
        apply("en", {});
      });
  }
  return <I18n.Provider value={{ language, t, setLanguage }}>{children}</I18n.Provider>;
}
export const useI18n = () => useContext(I18n);
