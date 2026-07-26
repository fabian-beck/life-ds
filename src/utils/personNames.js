/**
 * Person-name matching for prose.
 *
 * Every place the app emphasizes a person's name inside running text — story
 * slide descriptions, meta story prose, the network and map narration cards —
 * asks the same question: *where in this paragraph is this person mentioned?*
 * This module answers it once, so all of them behave identically.
 *
 * ## Why not regex-per-variant
 *
 * The obvious approach — build `\bAda Lovelace\b`, `\bLovelace\b`, … and run
 * them over the text — fails in ways that show up constantly in this dataset:
 *
 * - `\b` is ASCII-only in JavaScript, so `\bGaudí\b` never matches "Gaudí"
 *   (the boundary after a non-ASCII letter is not a boundary at all).
 * - German genitives glue an "s" onto the name ("Zuses Software",
 *   "Ada Lovelaces Notes"), which `\b` refuses to match.
 * - A bare surname regex cannot tell "Adams’s letters" (Abigail Adams) from
 *   "John Adams" (her husband, not in the story) — both contain "Adams".
 *
 * ## What this does instead
 *
 * The text is scanned for **name runs**: maximal stretches of capitalized
 * tokens, joined across spaces, hyphens, name particles ("von", "of") and the
 * dots of initials ("E. T. A. Hoffmann"). A run is the unit a reader sees as
 * one name phrase, so matching happens *against whole runs* rather than
 * against raw substrings, and the tokens around a match are available as
 * evidence. Each person's name is compiled into a token spec (given names,
 * surname, regnal numeral, geographic epithet); a run slice matches when its
 * tokens are an in-order subsequence of the spec that covers the name's
 * primary token. Comparison is diacritic-folded and accepts genitive forms.
 *
 * The guards that follow from having the run available are what make short
 * forms safe:
 *
 * - a surname-only slice preceded by another capitalized token is rejected,
 *   because that token is almost certainly a *different* given name
 *   ("John Adams" ≠ Abigail Adams);
 * - a slice that does not reach the surname is rejected when a capitalized
 *   token follows it, unless the match itself carries a genitive ending
 *   ("George III" ≠ George Washington, but "Heinrichs Mutter" is Henry II);
 * - a run carrying a regnal numeral only matches a person with that same
 *   numeral ("Otto III" is nobody's Otto Wagner);
 * - when two people match the same span equally well the span is left plain,
 *   because a wrong link is worse than a missing one.
 *
 * Given-name-only matching stays off unless the given name *is* the person's
 * identity (mononyms, regnal names, "X of Y") or is long and distinctive
 * enough to stand alone — "Alan" and "John" never match on their own, while
 * "Cunigunde" and "Vannevar" do.
 */

// Character-class fragments, written as escapes because they are spliced into
// RegExp sources: a literal hyphen in the middle of a class would silently
// become a range.

/** Hyphen-like characters that may sit inside or between name tokens. */
const HYPHEN_CHARS = "\\-\\u2010\\u2011\\u2012\\u2013\\u2014\\u2015\\u2212";

/** Apostrophe-like characters (possessives, O’Neill, transliterations). */
const APOSTROPHE_CHARS = "'\\u2019\\u02BC\\u02BB\\u00B4";

/** Spaces that keep a name run together. */
const SPACE_CHARS = " \\u00A0\\u2009\\u202F";

/**
 * Lowercase words that belong to a name and therefore may not break a run.
 * "of" and "the" are here for epithets ("Cunigunde of Luxembourg",
 * "Alexander the Great"), "i" and "y" join Iberian double surnames
 * ("Francesc Gaudí i Serra"); the rest are nobiliary/patronymic particles.
 */
const NAME_PARTICLES = new Set([
  "i",
  "y",
  "von",
  "vom",
  "van",
  "zu",
  "zur",
  "zum",
  "de",
  "del",
  "della",
  "der",
  "den",
  "des",
  "di",
  "du",
  "da",
  "das",
  "dos",
  "le",
  "la",
  "el",
  "al",
  "af",
  "av",
  "ten",
  "ter",
  "bin",
  "ibn",
  "of",
  "the",
]);

/**
 * Capitalized words that routinely open a sentence without naming anybody.
 *
 * A surname on its own is normally rejected when another capitalized token
 * sits in front of it, because that token is usually a *different* person's
 * given name ("John Adams" is not Abigail Adams). At the start of a sentence
 * that inference breaks down — "Later Wagner joined the Secession" capitalizes
 * "Later" for grammar, not for a name — so these words are allowed to precede
 * a bare surname. Anything not listed stays conservative: no highlight rather
 * than a link to the wrong person.
 */
const SENTENCE_LEAD_WORDS = new Set(
  [
    // English
    "a",
    "after",
    "afterwards",
    "again",
    "all",
    "also",
    "although",
    "an",
    "and",
    "another",
    "as",
    "at",
    "back",
    "because",
    "before",
    "both",
    "but",
    "by",
    "during",
    "each",
    "even",
    "eventually",
    "every",
    "finally",
    "first",
    "for",
    "from",
    "further",
    "he",
    "her",
    "here",
    "his",
    "how",
    "however",
    "if",
    "in",
    "indeed",
    "inside",
    "instead",
    "into",
    "it",
    "its",
    "just",
    "last",
    "late",
    "later",
    "meanwhile",
    "more",
    "moreover",
    "most",
    "much",
    "neither",
    "next",
    "no",
    "nor",
    "not",
    "now",
    "of",
    "on",
    "once",
    "one",
    "only",
    "or",
    "other",
    "our",
    "out",
    "over",
    "second",
    "she",
    "since",
    "so",
    "some",
    "soon",
    "still",
    "such",
    "that",
    "the",
    "their",
    "then",
    "there",
    "these",
    "they",
    "this",
    "those",
    "though",
    "three",
    "through",
    "throughout",
    "thus",
    "to",
    "today",
    "together",
    "two",
    "under",
    "until",
    "up",
    "we",
    "what",
    "when",
    "where",
    "which",
    "while",
    "who",
    "why",
    "with",
    "within",
    "without",
    "yet",
    "you",
    "your",
    // German
    "aber",
    "alle",
    "als",
    "am",
    "an",
    "auch",
    "auf",
    "aus",
    "bei",
    "beide",
    "bevor",
    "bis",
    "da",
    "dabei",
    "dadurch",
    "dafür",
    "daher",
    "damals",
    "damit",
    "danach",
    "dann",
    "daraufhin",
    "darum",
    "das",
    "dass",
    "dem",
    "den",
    "denn",
    "der",
    "des",
    "deshalb",
    "dennoch",
    "die",
    "diese",
    "diesem",
    "diesen",
    "dieser",
    "dieses",
    "doch",
    "dort",
    "durch",
    "ein",
    "eine",
    "einem",
    "einen",
    "einer",
    "eines",
    "endlich",
    "er",
    "erst",
    "es",
    "für",
    "gegen",
    "hier",
    "ihm",
    "ihn",
    "ihr",
    "ihre",
    "im",
    "immer",
    "in",
    "inzwischen",
    "jedoch",
    "jetzt",
    "kaum",
    "man",
    "mit",
    "nach",
    "nachdem",
    "noch",
    "nur",
    "ob",
    "obwohl",
    "oder",
    "ohne",
    "schließlich",
    "schon",
    "sein",
    "seine",
    "seit",
    "sie",
    "so",
    "sogar",
    "spät",
    "später",
    "stattdessen",
    "tatsächlich",
    "über",
    "um",
    "und",
    "unter",
    "vom",
    "von",
    "vor",
    "während",
    "weil",
    "wenig",
    "wenn",
    "wer",
    "wie",
    "wieder",
    "wir",
    "wo",
    "zu",
    "zum",
    "zunächst",
    "zur",
    "zwar",
    "zwei",
    "zwischen",
  ].map((word) => fold(word))
);

/**
 * Titles and honorifics that introduce a person rather than name one, so a
 * surname behind them is still that surname's owner ("General Washington",
 * "Präsident Washington"). They deliberately do *not* license a given name on
 * its own for someone who has a surname: "King George" is a monarch, not
 * George Washington.
 */
const PERSON_TITLE_WORDS = new Set(
  [
    // English
    "admiral",
    "archbishop",
    "bishop",
    "cardinal",
    "captain",
    "chancellor",
    "colonel",
    "count",
    "countess",
    "dr",
    "doctor",
    "duchess",
    "duke",
    "emperor",
    "empress",
    "general",
    "governor",
    "judge",
    "king",
    "lady",
    "lieutenant",
    "lord",
    "major",
    "miss",
    "mr",
    "mrs",
    "ms",
    "pope",
    "president",
    "prince",
    "princess",
    "professor",
    "queen",
    "saint",
    "secretary",
    "senator",
    "sir",
    "st",
    // German
    "admiral",
    "bischof",
    "erzbischof",
    "kaiser",
    "kaiserin",
    "kanzler",
    "kardinal",
    "könig",
    "königin",
    "oberst",
    "papst",
    "präsident",
    "professor",
    "doktor",
    "fürst",
    "fürstin",
    "graf",
    "gräfin",
    "herr",
    "herzog",
    "herzogin",
    "hauptmann",
    "heilige",
    "leutnant",
    "major",
    "richter",
    "sankt",
    "senator",
  ].map((word) => fold(word))
);

/** Roman numerals up to XX — enough for any regnal name. */
const ROMAN_NUMERAL_RE = /^(?:x{0,2})(?:ix|iv|v?i{0,3})$/;

/**
 * Words too common to stand alone as a person's name. Shared with the older
 * variant-based matching so both agree on what is too generic to link.
 */
const COMMON_NAME_WORDS = new Set([
  "church",
  "grace",
  "hope",
  "faith",
  "love",
  "king",
  "queen",
  "prince",
  "lord",
  "duke",
  "white",
  "black",
  "green",
  "brown",
  "young",
  "old",
  "good",
  "new",
  "long",
  "short",
  "stone",
  "wood",
  "hill",
  "field",
  "well",
  "strong",
  "bright",
  "rich",
  "poor",
]);

/**
 * Minimum length for a given name to be matched on its own when the person
 * also has a surname. Keeps "Alan", "John", "Ada" and "Otto" from matching
 * every other Alan, John, Ada or Otto in the prose.
 */
const MIN_STANDALONE_GIVEN_LENGTH = 6;

/**
 * Check whether a word is too common to use as a standalone name match.
 * @param {string} word - Word to check
 * @returns {boolean} True when the word is too generic
 */
export function isCommonNameWord(word) {
  return COMMON_NAME_WORDS.has(fold(word));
}

/**
 * Fold a string for comparison: strip diacritics and case, normalize the
 * German sharp s and every apostrophe variant to one form.
 * @param {string} value - String to fold
 * @returns {string} Folded string
 */
function fold(value) {
  return String(value ?? "")
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(new RegExp(`[${APOSTROPHE_CHARS}]`, "g"), "'")
    .replace(/ß/g, "ss")
    .toLowerCase();
}

/**
 * Whether a token starts with an uppercase letter (i.e. reads as a name part).
 * @param {string} token - Token text
 * @returns {boolean} True when capitalized
 */
function isCapitalized(token) {
  return /^\p{Lu}/u.test(token);
}

/**
 * Whether a token is a Roman numeral like "II" or "XIV".
 * @param {string} token - Token text
 * @returns {boolean} True when the token is a Roman numeral
 */
function isRomanNumeral(token) {
  const folded = fold(token).replace(/\.$/, "");
  return folded.length > 0 && ROMAN_NUMERAL_RE.test(folded);
}

/**
 * Whether a token is a single-letter initial ("E." in "E. T. A. Hoffmann").
 * @param {string} token - Token text
 * @returns {boolean} True when the token is an initial
 */
function isInitial(token) {
  return /^\p{L}$/u.test(token);
}

// --- Tokenizing -----------------------------------------------------------

const TOKEN_RE = new RegExp(
  `[\\p{L}\\p{N}]+(?:[${APOSTROPHE_CHARS}][\\p{L}]*)?`,
  "gu"
);

/**
 * Split text into word tokens, keeping their character offsets.
 * A trailing possessive ("Washington’s", "Adams’") stays part of its token so
 * the genitive can be recognized and trimmed from the highlighted span.
 * @param {string} text - Text to tokenize
 * @returns {Array<{text: string, start: number, end: number}>} Tokens
 */
function tokenize(text) {
  const tokens = [];
  TOKEN_RE.lastIndex = 0;
  let match;
  while ((match = TOKEN_RE.exec(text)) !== null) {
    tokens.push({
      text: match[0],
      start: match.index,
      end: TOKEN_RE.lastIndex,
    });
  }
  return tokens;
}

const RUN_GAP_SPACE_RE = new RegExp(`^[${SPACE_CHARS}]+$`);
const RUN_GAP_HYPHEN_RE = new RegExp(`^[${HYPHEN_CHARS}]$`);
const RUN_GAP_DOT_RE = new RegExp(`^\\.[${SPACE_CHARS}]*$`);

/**
 * Whether the characters between two tokens keep them in the same name run.
 * A period only continues a run after an initial or a numeral ("E. T. A.",
 * "Heinrich II."); anywhere else it ends a sentence and therefore the run.
 * @param {string} gap - Text between the two tokens
 * @param {string} previousToken - The token before the gap
 * @returns {boolean} True when the run continues
 */
function gapKeepsRun(gap, previousToken) {
  if (gap === "") return false; // e.g. "3rd" — digits and letters fused
  if (RUN_GAP_SPACE_RE.test(gap)) return true;
  if (RUN_GAP_HYPHEN_RE.test(gap)) return true;
  if (RUN_GAP_DOT_RE.test(gap)) {
    return isInitial(previousToken) || isRomanNumeral(previousToken);
  }
  return false;
}

/**
 * Scan text for name runs: stretches of capitalized tokens (plus the
 * lowercase particles that belong to a name) that a reader takes as one
 * name phrase.
 * @param {string} text - Text to scan
 * @returns {Array<{tokens: Array}>} Runs of tokens
 */
function scanNameRuns(text) {
  const tokens = tokenize(text);
  const runs = [];
  let current = null;

  for (let i = 0; i < tokens.length; i += 1) {
    const token = tokens[i];
    const particle = NAME_PARTICLES.has(fold(token.text));
    const eligible = isCapitalized(token.text) || particle;

    if (!eligible) {
      current = null;
      continue;
    }

    const previous = tokens[i - 1];
    const connected =
      current &&
      previous &&
      gapKeepsRun(text.slice(previous.end, token.start), previous.text);

    if (connected) {
      current.tokens.push(token);
      continue;
    }

    current = { tokens: [token] };
    // A run starting on a capitalized token may still need the lowercase
    // particle in front of it ("… and von Neumann met …").
    if (
      !particle &&
      previous &&
      NAME_PARTICLES.has(fold(previous.text)) &&
      !isCapitalized(previous.text) &&
      gapKeepsRun(text.slice(previous.end, token.start), previous.text)
    ) {
      current.tokens.unshift(previous);
    }
    runs.push(current);
  }

  // A run of nothing but particles ("of the") is not a name.
  return runs.filter((run) => run.tokens.some((t) => isCapitalized(t.text)));
}

// --- Name specs -----------------------------------------------------------

/**
 * Strip the decorations that surround a name in the data but never appear in
 * prose: parentheticals, brackets, appended titles and honorific suffixes.
 * @param {string} name - Raw name
 * @returns {string} Cleaned name
 */
function cleanName(name) {
  return String(name)
    .replace(/_/g, " ")
    .replace(/\s*\([^)]*\)/g, "")
    .replace(/\s*\[[^\]]*\]/g, "")
    .replace(
      /,\s*(?:Holy Roman Emperor|Holy Roman Empress|King|Queen|Emperor|Empress|Duke|Duchess|Count|Countess|Prince|Princess|Bishop|Archbishop|Pope|Saint)\b.*$/i,
      ""
    )
    .replace(/\s+(?:Jr|Sr)\.?$/i, "")
    .replace(/\s+/g, " ")
    .trim();
}

/**
 * Compile a name into the token spec the matcher works with.
 *
 * Roles matter for the guards: `given` tokens are weak evidence on their own,
 * `surname` is the token that identifies the person, `numeral` distinguishes
 * rulers, and `epithet` covers the "of Luxembourg" tail, which is optional in
 * prose and must never match on its own.
 *
 * @param {string} rawName - Name as stored in the data
 * @returns {Object|null} Spec, or null when the name is unusable
 */
function buildNameSpec(rawName) {
  if (!rawName || typeof rawName !== "string") return null;
  const cleaned = cleanName(rawName);
  if (!cleaned) return null;

  const words = cleaned
    .split(new RegExp(`[${SPACE_CHARS}${HYPHEN_CHARS}]+`))
    .map((word) => word.replace(/\.$/, ""))
    .filter(Boolean);
  if (words.length === 0) return null;

  const tokens = [];
  let numeral = null;

  // "X of Y" / "X the Great": everything from the epithet particle on is a
  // qualifier, not a surname — "Luxembourg" must not match Cunigunde.
  const epithetIndex = words.findIndex((word, index) => {
    const folded = fold(word);
    return index > 0 && (folded === "of" || folded === "the");
  });

  const particleIndex = words.findIndex(
    (word, index) =>
      index > 0 &&
      index < words.length - 1 &&
      NAME_PARTICLES.has(fold(word)) &&
      fold(word) !== "of" &&
      fold(word) !== "the"
  );

  const head = epithetIndex > -1 ? words.slice(0, epithetIndex) : words;
  const tail = epithetIndex > -1 ? words.slice(epithetIndex) : [];

  // A regnal numeral closes the name ("Henry II", "Elizabeth I"). Requiring it
  // to be last keeps a numeral-shaped word in the middle of a name from being
  // read as one — the Catalan "i" of "Francesc Gaudí i Serra" is not a One.
  const headNumeralIndex =
    head.length > 1 && isRomanNumeral(head[head.length - 1])
      ? head.length - 1
      : -1;
  const nameWords =
    headNumeralIndex > -1 ? head.slice(0, headNumeralIndex) : head;
  if (headNumeralIndex > -1) numeral = fold(head[headNumeralIndex]);

  // Iberian double surnames join the paternal and maternal name with "i"/"y"
  // ("Francesc Gaudí i Serra", "Villar y Lozano"). Both words plus the
  // conjunction are the surname, and it is the *first* of them the person is
  // known by — so this must be found before the generic "last word is the
  // surname" rule turns "Serra" into the family name.
  const conjunctionIndex = nameWords.findIndex(
    (word, index) =>
      index > 1 &&
      index < nameWords.length - 1 &&
      (fold(word) === "i" || fold(word) === "y")
  );

  let givenWords;
  let surnameWords;
  if (epithetIndex > -1 || nameWords.length === 1) {
    // Mononym, regnal name or "X of Y": the given name is the identity.
    givenWords = nameWords;
    surnameWords = [];
  } else if (conjunctionIndex > -1) {
    givenWords = nameWords.slice(0, conjunctionIndex - 1);
    surnameWords = nameWords.slice(conjunctionIndex - 1);
  } else if (particleIndex > -1 && particleIndex < nameWords.length - 1) {
    givenWords = nameWords.slice(0, particleIndex);
    surnameWords = nameWords.slice(particleIndex);
  } else {
    givenWords = nameWords.slice(0, -1);
    surnameWords = nameWords.slice(-1);
  }

  for (const word of givenWords)
    tokens.push({ text: fold(word), role: "given" });
  for (const word of surnameWords) {
    tokens.push({
      text: fold(word),
      role: NAME_PARTICLES.has(fold(word)) ? "particle" : "surname",
    });
  }
  if (numeral) tokens.push({ text: numeral, role: "numeral" });
  for (const word of tail) tokens.push({ text: fold(word), role: "epithet" });

  const hasSurname = tokens.some((t) => t.role === "surname");
  const givenHead = givenWords.length > 0 ? fold(givenWords[0]) : "";
  const surnameHead = tokens.find((t) => t.role === "surname")?.text ?? "";

  return {
    tokens,
    numeral,
    hasSurname,
    // Index of the first given token: only *that* one stands for the person on
    // its own. A middle name does not — "Quincy" in "Elizabeth Quincy Smith"
    // is far more likely to be the town or another Quincy.
    givenHeadIndex: tokens.findIndex((t) => t.role === "given"),
    // Likewise for the surname: a double surname is shortened to its first
    // half, so "Serra" alone is not Francesc Gaudí i Serra.
    surnameHeadIndex: tokens.findIndex((t) => t.role === "surname"),
    // A surname that is also an everyday word ("King", "Church") needs the
    // given name beside it before it counts as a mention.
    surnameIsCommon: !!surnameHead && isCommonNameWord(surnameHead),
    // Without a surname the given name carries the identity, so it may match
    // alone; with one it must be long and distinctive to do so.
    allowsStandaloneGiven:
      !!givenHead &&
      !isCommonNameWord(givenHead) &&
      (!hasSurname || givenHead.length >= MIN_STANDALONE_GIVEN_LENGTH),
  };
}

/**
 * Read every name a person may be called by: the display name plus any
 * aliases (e.g. the English name kept in technical data alongside the
 * translated registry name).
 * @param {Object} person - Person-ish object
 * @returns {Array<string>} Names
 */
function namesOf(person) {
  const names = [person?.name ?? person?.person_name];
  if (Array.isArray(person?.aliases)) names.push(...person.aliases);
  return names.filter((name) => typeof name === "string" && name.trim());
}

/**
 * Compile the specs for a list of people, keeping each spec attached to the
 * person object the caller passed in.
 * @param {Array<Object>} people - People to match
 * @returns {Array<{person: Object, specs: Array}>} Compiled people
 */
function buildPeopleSpecs(people) {
  const compiled = [];
  for (const person of people) {
    const specs = namesOf(person).map(buildNameSpec).filter(Boolean);
    if (specs.length) compiled.push({ person, specs });
  }
  return compiled;
}

// --- Matching -------------------------------------------------------------

/**
 * Compare one text token against one name token, accepting genitive forms.
 * @param {string} tokenText - Token from the prose
 * @param {string} nameToken - Folded token from the name spec
 * @returns {{matched: boolean, trimEnd: number, genitive: boolean}} Result
 */
function compareToken(tokenText, nameToken) {
  const folded = fold(tokenText);
  if (folded === nameToken) {
    return { matched: true, trimEnd: 0, genitive: false };
  }
  // "Washington’s", "Adams’" — the possessive marker is not part of the name,
  // so it stays outside the highlight.
  if (folded === `${nameToken}'s`) {
    return { matched: true, trimEnd: 2, genitive: true };
  }
  if (folded === `${nameToken}'`) {
    return { matched: true, trimEnd: 1, genitive: true };
  }
  // German genitive: "Zuses", "Ada Lovelaces". The "s" reads as part of the
  // word, so it stays inside the highlight.
  if (folded === `${nameToken}s`) {
    return { matched: true, trimEnd: 0, genitive: true };
  }
  return { matched: false, trimEnd: 0, genitive: false };
}

/**
 * Try to align a slice of run tokens against a name spec.
 * The slice must be an in-order subsequence of the spec's tokens — prose may
 * drop middle names and epithets, but never reorder a name.
 * @param {Array} runTokens - Tokens of the run
 * @param {number} from - Slice start index (inclusive)
 * @param {number} to - Slice end index (exclusive)
 * @param {Object} spec - Compiled name spec
 * @returns {Object|null} Alignment details, or null when it does not fit
 */
function alignSlice(runTokens, from, to, spec) {
  let specIndex = 0;
  const roles = new Set();
  let hasGivenHead = false;
  let hasSurnameHead = false;
  let trimEnd = 0;
  let lastGenitive = false;

  for (let i = from; i < to; i += 1) {
    const token = runTokens[i];
    let hit = null;
    while (specIndex < spec.tokens.length) {
      const candidate = compareToken(token.text, spec.tokens[specIndex].text);
      specIndex += 1;
      if (candidate.matched) {
        hit = { ...candidate, index: specIndex - 1 };
        break;
      }
    }
    if (!hit) return null;
    roles.add(spec.tokens[hit.index].role);
    if (hit.index === spec.givenHeadIndex) hasGivenHead = true;
    if (hit.index === spec.surnameHeadIndex) hasSurnameHead = true;
    trimEnd = hit.trimEnd;
    lastGenitive = hit.genitive;
  }

  // The slice has to carry a name proper. An epithet, particle or numeral on
  // its own ("Luxembourg", "von", "II") names nobody. Whether a given name
  // alone is enough is decided by the caller, which can see the context.
  if (!roles.has("surname") && !roles.has("given")) return null;

  return {
    roles,
    trimEnd,
    lastGenitive,
    hasSurname: roles.has("surname"),
    hasGiven: roles.has("given"),
    hasGivenHead,
    hasSurnameHead,
  };
}

/**
 * Collect every acceptable (person, span) candidate inside one run.
 * @param {Object} run - Name run
 * @param {Array} compiled - Compiled people
 * @returns {Array<Object>} Candidates
 */
function candidatesInRun(run, compiled) {
  const tokens = run.tokens;
  // Regnal numbers are written in capitals ("Henry II"), which keeps the
  // lowercase Catalan "i" of a double surname out of this. A lone "I" is the
  // English pronoun far more often than a number, so it only counts as one
  // when something in the run precedes it.
  const runNumerals = tokens
    .filter(
      (token, index) =>
        isRomanNumeral(token.text) &&
        token.text === token.text.toUpperCase() &&
        (index > 0 || token.text.length > 1)
    )
    .map((token) => fold(token.text).replace(/\.$/, ""));
  const candidates = [];

  for (const { person, specs } of compiled) {
    for (const spec of specs) {
      // A regnal reference belongs to exactly one ruler: "Otto III" is not
      // Otto Wagner, and "Henry III" is not Henry II.
      if (
        runNumerals.length > 0 &&
        (!spec.numeral || !runNumerals.includes(spec.numeral))
      ) {
        continue;
      }

      for (let from = 0; from < tokens.length; from += 1) {
        for (let to = tokens.length; to > from; to -= 1) {
          const alignment = alignSlice(tokens, from, to, spec);
          if (!alignment) continue;

          // A given name on its own is only evidence for people whose given
          // name is their identity, or whose given name is distinctive — and
          // only their *first* given name, never a middle one.
          if (
            !alignment.hasSurname &&
            !(spec.allowsStandaloneGiven && alignment.hasGivenHead)
          ) {
            continue;
          }

          // A match must reach one of the name's head words. Middle names and
          // the second half of a double surname never stand in for the person.
          if (!alignment.hasGivenHead && !alignment.hasSurnameHead) continue;

          // A surname that doubles as an everyday word needs the given name
          // beside it: "King" on its own is a title, not William King-Noel.
          if (spec.surnameIsCommon && !alignment.hasGiven) continue;

          // "John Adams" is not Abigail Adams: a capitalized token in front of
          // the match is usually a *different* person's given name. Three
          // things clear it — a word capitalized only because it opens a
          // sentence ("Later Wagner joined"), a match that already spells out
          // the full name ("Die Politikerin Abigail Adams"), and a title
          // introducing its bearer ("General Washington"). A title in front of
          // a lone given name still fails for anyone who has a surname, which
          // is what separates "King George" from Henry II.
          const before = tokens[from - 1];
          if (before && isCapitalized(before.text)) {
            const folded = fold(before.text);
            const allowed =
              SENTENCE_LEAD_WORDS.has(folded) ||
              (alignment.hasGiven && alignment.hasSurname) ||
              (PERSON_TITLE_WORDS.has(folded) &&
                (alignment.hasSurname || !spec.hasSurname));
            if (!allowed) continue;
          }

          // "George III" is not George Washington: a match that stops short
          // of the surname cannot absorb a capitalized token after it —
          // unless it carries a genitive ending, which closes the name
          // ("Heinrichs Mutter", "Ada Lovelaces Notes").
          const after = tokens[to];
          if (
            after &&
            isCapitalized(after.text) &&
            !alignment.hasSurname &&
            !alignment.lastGenitive
          ) {
            continue;
          }

          const start = tokens[from].start;
          const end = tokens[to - 1].end - alignment.trimEnd;
          if (end <= start) continue;

          candidates.push({
            person,
            start,
            end,
            score: (to - from) * 2 + (alignment.hasSurname ? 1 : 0),
          });
          break; // longest slice starting here wins; shorter ones are subsets
        }
      }
    }
  }

  return candidates;
}

/**
 * Find where the given people are mentioned in a piece of prose.
 *
 * @param {string} text - Prose to scan
 * @param {Array<Object>} people - Objects carrying `name` (or `person_name`)
 *   and optionally `aliases`; each returned match points back at its object
 * @param {Object} [options] - Options
 * @param {Array<{start: number, end: number}>} [options.exclude] - Character
 *   ranges that must stay untouched (e.g. annotation markup)
 * @returns {Array<{start: number, end: number, person: Object}>} Matches in
 *   document order, never overlapping
 */
export function findPersonMentions(text, people, options = {}) {
  if (!text || typeof text !== "string") return [];
  if (!Array.isArray(people) || people.length === 0) return [];

  const compiled = buildPeopleSpecs(people);
  if (compiled.length === 0) return [];

  const exclude = options.exclude ?? [];
  const candidates = [];
  for (const run of scanNameRuns(text)) {
    candidates.push(...candidatesInRun(run, compiled));
  }

  const overlaps = (a, b) => a.start < b.end && b.start < a.end;
  const usable = candidates.filter(
    (candidate) => !exclude.some((range) => overlaps(candidate, range))
  );

  // Best matches first; a longer, surname-bearing span beats a shorter one.
  usable.sort(
    (a, b) => b.score - a.score || a.start - b.start || b.end - a.end
  );

  const taken = [];
  const accepted = [];
  for (const candidate of usable) {
    if (taken.some((range) => overlaps(candidate, range))) continue;

    // Two people fit the same words equally well: leave the text plain rather
    // than link to the wrong story.
    const ambiguous = usable.some(
      (rival) =>
        rival.person !== candidate.person &&
        rival.score === candidate.score &&
        overlaps(rival, candidate) &&
        !taken.some((range) => overlaps(rival, range))
    );
    if (ambiguous) {
      taken.push({ start: candidate.start, end: candidate.end });
      continue;
    }

    taken.push({ start: candidate.start, end: candidate.end });
    accepted.push(candidate);
  }

  return accepted.sort((a, b) => a.start - b.start);
}

/**
 * Split prose into text and person segments, emphasizing every mention of the
 * given people. The rendering components turn `person` segments into the
 * `.person-mention` treatment (a link into that person's story where one
 * exists).
 *
 * @param {string} text - Prose to segment
 * @param {Array<Object>} people - People to emphasize (see findPersonMentions)
 * @returns {Array<{type: "text"|"person", content: string, person?: Object}>}
 */
export function segmentPersonMentions(text, people) {
  if (!text) return [{ type: "text", content: "" }];
  const matches = findPersonMentions(text, people);
  if (matches.length === 0) return [{ type: "text", content: text }];

  const segments = [];
  let cursor = 0;
  for (const match of matches) {
    if (match.start > cursor) {
      segments.push({ type: "text", content: text.slice(cursor, match.start) });
    }
    segments.push({
      type: "person",
      content: text.slice(match.start, match.end),
      person: match.person,
    });
    cursor = match.end;
  }
  if (cursor < text.length) {
    segments.push({ type: "text", content: text.slice(cursor) });
  }
  return segments;
}
