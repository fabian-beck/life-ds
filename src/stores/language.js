import { writable, derived } from "svelte/store";

// Detect initial language from localStorage or browser
const browserLang =
  typeof navigator !== "undefined" ? navigator.language.split("-")[0] : "en";
const storedLang =
  typeof localStorage !== "undefined"
    ? localStorage.getItem("preferredLanguage")
    : null;
const initialLang = storedLang || (browserLang === "de" ? "de" : "en");

// Current language code
export const currentLanguage = writable(initialLang);

// Translation strings
export const translations = writable({});

// Persist language preference and update HTML lang attribute
currentLanguage.subscribe((lang) => {
  if (typeof localStorage !== "undefined") {
    localStorage.setItem("preferredLanguage", lang);
  }
  if (typeof document !== "undefined") {
    document.documentElement.lang = lang;
  }
});

// Derived store for reactive translation
export const _ = derived([currentLanguage, translations], ([, $trans]) => {
  return (key, params = {}) => {
    let str = $trans[key] || key;
    Object.entries(params).forEach(([k, v]) => {
      str = str.replace(new RegExp(`\\{${k}\\}`, "g"), v);
    });
    return str;
  };
});

// Load translation file dynamically. The generation counter ensures that when
// the language is switched rapidly, only the most recent request applies —
// otherwise the last load to resolve would win regardless of order.
let loadGeneration = 0;
export async function loadTranslations(lang) {
  const generation = ++loadGeneration;
  try {
    const module = await import(`../locales/${lang}.json`);
    if (generation !== loadGeneration) return;
    translations.set(module.default);
  } catch (error) {
    console.error(`Failed to load translations for ${lang}:`, error);
    // Fallback to English
    if (lang !== "en") {
      try {
        const fallback = await import("../locales/en.json");
        if (generation !== loadGeneration) return;
        translations.set(fallback.default);
      } catch (fallbackError) {
        console.error("Failed to load English fallback:", fallbackError);
        if (generation !== loadGeneration) return;
        translations.set({});
      }
    }
  }
}
