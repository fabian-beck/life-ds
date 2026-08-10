/**
 * Matching events to their icons, by classification and text content.
 */
import {
  mdiCircleSmall,
  mdiBabyFaceOutline,
  mdiSkullOutline,
  mdiSchoolOutline,
  mdiRing,
  mdiCrownOutline,
  mdiStarCircleOutline,
  mdiSwordCross,
  mdiBookOpenVariant,
  mdiBriefcaseOutline,
  mdiNavigationVariant,
} from "@mdi/js";

/**
 * Icon rules for matching events to icons based on content.
 */
export const EVENT_ICON_RULES = [
  {
    icon: mdiBabyFaceOutline,
    matches: (event, text) =>
      event?.age === 0 || text.includes("birth") || text.includes("born"),
  },
  {
    icon: mdiSkullOutline,
    matches: (_event, text) =>
      text.includes("death") ||
      text.includes("died") ||
      text.includes("passed away"),
  },
  {
    icon: mdiSchoolOutline,
    matches: (_event, text) =>
      text.includes("graduat") ||
      text.includes("degree") ||
      text.includes("diploma"),
  },
  {
    icon: mdiRing,
    matches: (_event, text) =>
      text.includes("marriage") ||
      text.includes("married") ||
      text.includes("wedding"),
  },
  {
    icon: mdiCrownOutline,
    matches: (_event, text) =>
      text.includes("crowned") ||
      text.includes("coronation") ||
      text.includes("enthroned"),
  },
  {
    icon: mdiStarCircleOutline,
    matches: (_event, text) =>
      text.includes("award") ||
      text.includes("prize") ||
      text.includes("honor") ||
      text.includes("medal"),
  },
  {
    icon: mdiSwordCross,
    matches: (_event, text) =>
      text.includes("battle") ||
      text.includes("war") ||
      text.includes("campaign"),
  },
  {
    icon: mdiBookOpenVariant,
    matches: (_event, text) =>
      text.includes("publish") ||
      text.includes("publication") ||
      text.includes("book") ||
      text.includes("paper"),
  },
  {
    icon: mdiBriefcaseOutline,
    matches: (_event, text) =>
      text.includes("appointed") ||
      text.includes("elected") ||
      text.includes("named") ||
      text.includes("assumes"),
  },
  {
    icon: mdiNavigationVariant,
    matches: (_event, text) =>
      text.includes("voyage") ||
      text.includes("expedition") ||
      text.includes("travels") ||
      text.includes("journey"),
  },
];
/**
 * Resolve the appropriate icon for an event based on its content.
 * @param {Object} event - Event object
 * @returns {string} MDI icon path
 */
export function resolveEventIcon(event) {
  const text = `${event?.title ?? ""} ${event?.description ?? ""}`
    .toLowerCase()
    .replace(/\s+/g, " ")
    .trim();
  for (const rule of EVENT_ICON_RULES) {
    try {
      if (rule.matches(event, text)) {
        return rule.icon;
      }
    } catch {
      // ignore rule errors to avoid breaking icon rendering
    }
  }
  return mdiCircleSmall;
}
