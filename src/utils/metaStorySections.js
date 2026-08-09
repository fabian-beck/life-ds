/**
 * The order of a meta story's three component sections.
 *
 * Chronology, circle and geography answer different questions — when, who with
 * whom, where — and which one a story turns on differs, so the sequence is a
 * composition decision carried in the story document as `section_order` (see
 * `scripts/compose_meta_story.py`). This module resolves that stored order the
 * same way the composer stores it: only sections the story actually has, each
 * once, and anything the order forgets appended in the historical default —
 * so no component can go missing from the page over a careless list.
 */

/** The component sections, in the order a story without a composed one uses. */
export const DEFAULT_SECTION_ORDER = ["timeline", "network", "map"];

/** Whether the story carries the data this section needs to render. */
export function hasSection(metaStoryData, section) {
  if (section === "timeline") return !!metaStoryData?.chapters?.length;
  if (section === "network")
    return !!metaStoryData?.social_network?.links?.length;
  if (section === "map") return !!metaStoryData?.geo_map?.clusters?.length;
  return false;
}

/** The component sections this story renders, in the order it asks for. */
export function resolveSectionOrder(metaStoryData) {
  const available = DEFAULT_SECTION_ORDER.filter((section) =>
    hasSection(metaStoryData, section)
  );
  const composed = Array.isArray(metaStoryData?.section_order)
    ? metaStoryData.section_order
    : [];
  const named = [...new Set(composed)].filter((section) =>
    available.includes(section)
  );
  return named.concat(available.filter((section) => !named.includes(section)));
}
