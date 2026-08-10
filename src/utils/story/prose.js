/**
 * Description prose: splitting an event's text into plain, annotated, and
 * person-mention segments.
 */
import { findPersonMentions } from "../personNames.js";

/** Characters that make a neighbor part of the same word. */
const WORD_CHARACTER = /[\p{L}\p{N}]/u;
/**
 * Escape a literal string for use inside a regular expression.
 * @param {string} value - Literal text
 * @returns {string} Pattern source matching that text
 */
function escapeForRegExp(value) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}
/**
 * Locate an annotated term in prose that carries no `[[…]]` markup for it.
 *
 * The generator is asked to define an annotation *and* mark its term in the
 * description, and it regularly does only the first — across the current data
 * roughly one annotation in nine is defined but never marked, so its
 * explanation is written, translated, and then never shown. The terms this
 * strands are mostly institutions ("Glasgow School of Art", "Risø",
 * "Cercle Artístic de Sant Lluc"), which is what the reader notices: the very
 * names that need a gloss are the ones without one.
 *
 * Finding the term in the text is the same move the app already makes for
 * people, whose names are matched in the prose rather than marked up in it.
 * The markup therefore stops being the only way to place an annotation and
 * becomes what it is actually needed for: annotating a phrase whose wording
 * differs from the term (`[[Modernisme|the modernista style]]`).
 *
 * @param {string} description - Prose to scan
 * @param {string} termKey - Annotation key, as prose or as a slug
 * @param {Array<{start: number, end: number}>} occupied - Ranges already taken
 * @returns {{start: number, end: number}|null} First free whole-word match
 */
function findAnnotationTerm(description, termKey, occupied) {
  // Keys come both as prose ("Glasgow School of Art") and as slugs
  // ("Greek_War_of_Independence"); both stand for the same words.
  const spelled = termKey.replace(/_/g, " ");
  // A key names a place in full where the sentence names it plainly
  // ("Portland, Oregon" for "moved from Portland"), so the qualifier behind
  // the comma is dropped — but only after the full key has failed to match.
  const unqualified = spelled.replace(/,[^,]*$/, "");
  const candidates = [termKey, spelled, unqualified];

  for (const candidate of candidates) {
    const term = candidate.trim();
    if (!term) continue;

    // Case-insensitive: a term is keyed as the concept ("photoelectric_effect")
    // as often as it is spelled the way the sentence spells it.
    const pattern = new RegExp(escapeForRegExp(term), "giu");
    let match;
    while ((match = pattern.exec(description)) !== null) {
      const start = match.index;
      const end = pattern.lastIndex;
      const before = description[start - 1];
      const after = description[end];
      if (before && WORD_CHARACTER.test(before)) continue;
      if (after && WORD_CHARACTER.test(after)) continue;
      if (occupied.some((range) => start < range.end && range.start < end)) {
        continue;
      }
      return { start, end };
    }
  }

  return null;
}
/**
 * Parse event description into segments with annotations AND person names.
 * Annotations take priority over person name matches.
 * @param {string} description - Event description text
 * @param {Object} annotations - Annotation dictionary
 * @param {Array} relevantPeople - Array of connection objects
 * @param {string} [subjectName] - The story's own subject. Family shares
 *   surnames, so without them a bare "Hamilton" in Alexander Hamilton's story
 *   is handed to his father. Matching the subject too lets the shared surname
 *   come out ambiguous — and therefore plain — while "James Hamilton" still
 *   resolves to the father.
 * @returns {Array} Segments: {type: 'text'|'annotation'|'person', ...}
 */
export function parseDescriptionSegments(
  description,
  annotations = {},
  relevantPeople = [],
  subjectName = null
) {
  if (!description) return [];

  // Step 1: Parse annotations first (they take priority)
  const annotationPattern = /\[\[([^\]|]+)(?:\|([^\]]+))?\]\]/g;
  const annotationRanges = [];
  const seenTermKeys = new Set(); // Track which terms we've already annotated
  let match;

  while ((match = annotationPattern.exec(description)) !== null) {
    const termKey = match[1];
    const displayText = match[2] || match[1];
    const annotation = annotations[termKey];

    // Track this range regardless of whether annotation exists
    // If annotation exists AND we haven't seen this term before, mark it as an annotation
    // Otherwise, mark it as plain text (to strip the markup)
    if (annotation && !seenTermKeys.has(termKey)) {
      seenTermKeys.add(termKey); // Mark this term as used
      annotationRanges.push({
        start: match.index,
        end: annotationPattern.lastIndex,
        type: "annotation",
        termKey,
        displayText,
        annotation,
      });
    } else {
      // Annotation markup exists but no annotation definition, or duplicate
      // Add as a plain text replacement (strip the markup, keep display text)
      annotationRanges.push({
        start: match.index,
        end: annotationPattern.lastIndex,
        type: "unresolved-annotation",
        displayText,
      });
    }
  }

  // Step 2: Find person name matches, skipping anything the annotation
  // markup already claims (annotations win, and their `[[term|display]]`
  // syntax would otherwise be highlighted mid-marker).
  const subject = subjectName
    ? { person_name: subjectName, isSubject: true }
    : null;
  const personMatches = findPersonMentions(
    description,
    subject ? [...relevantPeople, subject] : relevantPeople,
    { exclude: annotationRanges }
  )
    // The subject is only in the list to compete for their own name; their
    // mentions stay plain text (this is their story — nothing to link to).
    .filter((match) => !match.person.isSubject)
    .map((match) => ({
      start: match.start,
      end: match.end,
      type: "person",
      person: match.person,
      matchedText: description.slice(match.start, match.end),
    }));

  // Step 2b: An annotation the description never marked up is still an
  // annotation — find its term in the prose (see findAnnotationTerm). Names are
  // settled first and an emphasized one is off limits: the generator is told
  // never to annotate a person, and where it did anyway ("Lord Byron" in Ada
  // Lovelace's birth) the person's card is the richer answer. The subject's own
  // name is not a match to protect — it renders as plain text — so a term that
  // merely contains it ("Zuse KG") is still free. Explicit markup keeps its
  // precedence, having been written into the sentence on purpose.
  for (const [termKey, annotation] of Object.entries(annotations ?? {})) {
    if (seenTermKeys.has(termKey) || !annotation) continue;
    const range = findAnnotationTerm(description, termKey, [
      ...annotationRanges,
      ...personMatches,
    ]);
    if (!range) continue;
    seenTermKeys.add(termKey);
    annotationRanges.push({
      start: range.start,
      end: range.end,
      type: "annotation",
      termKey,
      // The prose spells the term the way the sentence needed it; that is what
      // the reader tapped, so that is what the popup labels.
      displayText: description.slice(range.start, range.end),
      annotation,
    });
  }

  // Step 3: Merge all ranges and sort by position
  const allRanges = [...annotationRanges, ...personMatches].sort((a, b) => {
    if (a.start !== b.start) return a.start - b.start;
    // If same start, annotations win
    if (a.type === "annotation") return -1;
    if (b.type === "annotation") return 1;
    return 0;
  });

  // Step 4: Remove overlapping person matches
  const filteredRanges = [];
  let lastEnd = 0;

  for (const range of allRanges) {
    if (range.start >= lastEnd) {
      filteredRanges.push(range);
      lastEnd = range.end;
    }
    // Skip overlapping ranges
  }

  // Step 5: Build final segment array
  const segments = [];
  let currentPos = 0;

  for (const range of filteredRanges) {
    // Add text before this range
    if (range.start > currentPos) {
      segments.push({
        type: "text",
        content: description.slice(currentPos, range.start),
      });
    }

    // Add the range itself
    if (range.type === "annotation") {
      segments.push({
        type: "annotation",
        termKey: range.termKey,
        displayText: range.displayText,
        annotation: range.annotation,
      });
    } else if (range.type === "unresolved-annotation") {
      // Unresolved annotation: just add the display text as plain text
      segments.push({
        type: "text",
        content: range.displayText,
      });
    } else if (range.type === "person") {
      segments.push({
        type: "person",
        content: range.matchedText,
        person: range.person,
      });
    }

    currentPos = range.end;
  }

  // Add remaining text
  if (currentPos < description.length) {
    segments.push({
      type: "text",
      content: description.slice(currentPos),
    });
  }

  return segments;
}
