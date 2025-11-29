import { writable, derived, get } from 'svelte/store';

// Detect initial language from localStorage or browser
const browserLang = typeof navigator !== 'undefined'
  ? navigator.language.split('-')[0]
  : 'en';
const storedLang = typeof localStorage !== 'undefined'
  ? localStorage.getItem('preferredLanguage')
  : null;
const initialLang = storedLang || (browserLang === 'de' ? 'de' : 'en');

// Current language code
export const currentLanguage = writable(initialLang);

// Translation strings
export const translations = writable({});

// Persist language preference and update HTML lang attribute
currentLanguage.subscribe(lang => {
  if (typeof localStorage !== 'undefined') {
    localStorage.setItem('preferredLanguage', lang);
  }
  if (typeof document !== 'undefined') {
    document.documentElement.lang = lang;
  }
});

// Translation helper function with interpolation
export function t(key, params = {}) {
  const trans = get(translations);
  let str = trans[key] || key;

  // Interpolate parameters
  Object.entries(params).forEach(([k, v]) => {
    str = str.replace(new RegExp(`\\{${k}\\}`, 'g'), v);
  });

  return str;
}

// Derived store for reactive translation
export const _ = derived(
  [currentLanguage, translations],
  ([$lang, $trans]) => {
    return (key, params = {}) => {
      let str = $trans[key] || key;
      Object.entries(params).forEach(([k, v]) => {
        str = str.replace(new RegExp(`\\{${k}\\}`, 'g'), v);
      });
      return str;
    };
  }
);

// Load translation file dynamically
export async function loadTranslations(lang) {
  try {
    const module = await import(`../locales/${lang}.json`);
    translations.set(module.default);
  } catch (error) {
    console.error(`Failed to load translations for ${lang}:`, error);
    // Fallback to English
    if (lang !== 'en') {
      try {
        const fallback = await import('../locales/en.json');
        translations.set(fallback.default);
      } catch (fallbackError) {
        console.error('Failed to load English fallback:', fallbackError);
        translations.set({});
      }
    }
  }
}

// Date formatter
export const dateFormatter = derived(
  currentLanguage,
  ($lang) => new Intl.DateTimeFormat($lang, {
    year: 'numeric',
    month: 'long',
    day: 'numeric'
  })
);

// Number formatter
export const numberFormatter = derived(
  currentLanguage,
  ($lang) => new Intl.NumberFormat($lang)
);
