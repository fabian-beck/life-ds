import { writable, derived } from "svelte/store";
import { localStore } from "../utils/safeStorage.js";

// Eagerly bundle every locale file. They are tiny (~8-9 KB each), so pulling
// them into the entry chunk is cheap and — crucially — makes the strings
// available *synchronously*. Without this, the very first render happens
// before the async translation import resolves, so every `$_('some.key')`
// falls back to rendering the raw key ("story.loading_life"), which then
// flickers to the real text once the JSON arrives. Eager loading removes that
// flash entirely, including on slow connections.
const localeModules = import.meta.glob("../locales/*.json", {
  eager: true,
  import: "default",
});

// Map "en" -> parsed translations, keyed off the filename.
const locales = {};
for (const [path, data] of Object.entries(localeModules)) {
  const match = path.match(/\/([^/]+)\.json$/);
  if (match) locales[match[1]] = data;
}

function getLocale(lang) {
  return locales[lang] || locales.en || {};
}

// Detect initial language from localStorage or browser
const browserLang =
  typeof navigator !== "undefined" ? navigator.language.split("-")[0] : "en";
const storedLang = localStore.get("preferredLanguage");
const initialLang = storedLang || (browserLang === "de" ? "de" : "en");

// Current language code
export const currentLanguage = writable(initialLang);

// Translation strings — seeded synchronously so the first paint already has
// real text (no flash of raw translation keys).
export const translations = writable(getLocale(initialLang));

// Keep the active strings, persisted preference, and document language in sync.
currentLanguage.subscribe((lang) => {
  translations.set(getLocale(lang));
  localStore.set("preferredLanguage", lang);
  if (typeof document !== "undefined") {
    document.documentElement.lang = lang;
  }
});

// Derived store for reactive translation
export const _ = derived([currentLanguage, translations], ([, $trans]) => {
  return (key, params = {}) => {
    let str = $trans[key] || key;
    Object.entries(params).forEach(([k, v]) => {
      // Function replacement so values containing "$&" etc. are inserted verbatim
      str = str.replace(new RegExp(`\\{${k}\\}`, "g"), () => v);
    });
    return str;
  };
});

// Swap the active translation strings. Locales are already bundled, so this is
// a synchronous lookup — no network round-trip and no chance of the switch
// resolving out of order.
export function loadTranslations(lang) {
  translations.set(getLocale(lang));
}
