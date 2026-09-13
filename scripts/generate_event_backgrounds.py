#!/usr/bin/env python3
"""Write the depth-layer background reports for a person's deep events.

The story offers a way down on roughly one event per chapter — the deep-event
selection in ``src/utils/story/eventDepth.js``, ported in
``scripts/utils/event_depth.py`` — and the layer it opens is a written report
plus the pictures that illustrate it. This step runs after the events and the
ego network exist, computes that selection, and writes a report exactly for
the events the story will offer one on. The research used to write a report for
every event; most of them could never be reached, and each cost the run a
long-prose call and an illustration critic.

A selected event is where a report may go, not where one has to: the call
notes what its sources say about the event before it writes, and an event they
record without documenting — a wedding in half a sentence, a move in one — gets
none. The story then offers no way down there, which is what
``hasBackgroundReport`` in ``src/utils/story/eventDepth.js`` is for.

The report is the one thing in the pipeline written for a reader rather than
extracted for a schema. Its material is the same material the research sees — the
event, the subject, and the cached related articles filtered down to the ones
about this event — plus what only this later step can know: the annotations,
chips, and citations already on the slide, and the rest of the story as the
reader can swipe to it.

Inside ``generate_person.py`` this runs after review and before translation,
so the reports build on the reviewed English text and the translator sees
them. Standalone it fills exactly the same events:

    python scripts/generate_event_backgrounds.py alan_turing
    python scripts/generate_event_backgrounds.py                # every person
    python scripts/generate_event_backgrounds.py --dry-run
    python scripts/generate_event_backgrounds.py --overwrite    # rewrite
"""

from __future__ import annotations

import argparse
import json
import os
import re
from typing import Any, Dict, List, Optional, Set, cast
from urllib.parse import unquote

from openai import OpenAI
from pydantic import BaseModel, Field, ValidationError

from config import (
    BULK_REASONING_EFFORT,
    DEFAULT_MODEL,
    DEFAULT_REASONING_EFFORT,
    enable_utf8_console,
)
from events.images.assign import STAND_IN_REJECTION_INSTRUCTIONS, image_year_taken
from events.images.scoring import filter_images_by_quality
from events.images.sources import search_wikimedia_commons
from events.pipeline import PEOPLE_DIR
from events.prompts.research import (
    RELATED_ARTICLE_COUNT,
    _related_articles_prompt_section,
    _subject_article_prompt_section,
    filter_related_articles_for_event,
)
from events.schemas import CLASSIFICATION_MODELS, EventSkeleton
from utils.citations import citable_urls, keep_citable
from utils.concurrency import map_concurrently, worker_count
from utils.datasets import person_ids
from utils.event_depth import get_event_weight, select_deep_event_indexes
from utils.json_io import read_json, write_json
from utils.model_calls import Prompt, parse_structured
from utils.prose_style import PROSE_STYLE_INSTRUCTIONS
from utils.wikipedia_cache import get_cache_dir

enable_utf8_console()

# The report is prose checked by nobody, which is what keeps it off the bulk
# tier (see config.py): a wrong extraction is caught, a thin report ships.
REPORT_MODEL = DEFAULT_MODEL

# The effort, unlike the tier, can come down. What the report needs from the
# model is recall across a long article and control of a paragraph, not
# deliberation: the material is supplied, the questions to answer are listed,
# and the shape is prescribed to the paragraph. Reasoning was a third of what
# this step spent and bought a plan for prose that the instructions had
# already planned. The gate put a judgment back in front of that, which is the
# kind of thing an effort tier usually decides, so it was measured here rather
# than assumed: on a subject article that carries a career and records a
# wedding in one sentence, four runs on this tier gathered one to three notes
# and refused the report every time, and four on the same event with an
# article that actually discusses it gathered seventeen to twenty-two and
# wrote one every time. The judgment is a reading, and reading is what this
# tier does well.
REPORT_REASONING_EFFORT = BULK_REASONING_EFFORT

# ``[[term|display]]`` markers, and the bare ``[[term]]`` the research writes
# about one marker in eight, are an interface detail; the event is shown to the
# model as the reader reads it.
_MARKER = re.compile(r"\[\[([^\[\]|]+)(?:\|([^\[\]]*))?\]\]")


def _plain(text: str) -> str:
    """A description with its annotation markup reduced to the words it wraps."""
    return _MARKER.sub(lambda m: m.group(2) or m.group(1), text or "")


class BackgroundOnly(BaseModel):
    """The report, asked for on its own — and its sources and searches.

    The material comes first, before the prose, because the order of the
    fields is the order the call writes them in: a report asked for straight
    away is a report already being written by the time the question of whether
    there is one to write comes up. Engelbart's wedding is what that cost. The
    article records it in a sentence, the call had a word budget to fill, and
    the layer under a 1951 wedding opened on his 1948 degree, went on to
    Berkeley, and closed on the company he founded in 1956 — every sentence
    true, sourced, and about four other slides. Listing what the sources say
    about this event in particular is a question that can be answered with
    nothing, and a call that has just answered it with nothing writes null.

    The sources come along because the depth layer prints them under the
    passage, which is the first time in this application that an event's own
    provenance is put in front of a reader: they used to be pooled on the
    conclusion slide, where a wrong one was invisible. Several were wrong. The
    prompt that produced them said "provide 1-3 Wikipedia URLs from the related
    articles below", so an event no related article documents got the closest
    one anyway — Morcom's death, in 1930, cited the article on Turing's 1936
    proof. Re-deciding them costs nothing here: the call is already looking at
    this event and at those same articles.
    """

    event_specific_material: List[str] = Field(
        default_factory=list,
        description=(
            "FILL THIS BEFORE WRITING ANYTHING ELSE, and be exhaustive: "
            "every fact the articles give that stands around THIS event — how "
            "it came about, what it took, the circumstances, the room, the "
            "machine, the money, the people in it and what they were to the "
            "subject, how it went, how it was received, what followed from "
            "it. One short note per fact, in your own words. Working material "
            "rather than prose, so a fact the description also carries belongs "
            "here when the sources give more of it; what does not belong is a "
            "fact about something else — the era, the subject's career at "
            "large, the institution in general. Empty when the sources record "
            "the event without saying anything around it, which is a normal "
            "and frequent answer."
        ),
    )
    background: Optional[str] = Field(
        None,
        description=(
            "NULL unless event_specific_material says something around the "
            "event; a list that only restates that it happened is an event "
            "with no background to report, and the story then simply offers "
            "no way down. Otherwise a "
            "background report for this event, up to 350 words in 2-4 "
            "paragraphs separated by blank lines, written from those notes "
            "and going no wider than they reach: the situation this event sat "
            "in, its concrete specifics, one thing told at length, and what "
            "came of it. Shorter where the notes are fewer — never padded "
            "toward a length with the era, the city, or the rest of the "
            "life. One or two '## Section heading' lines may divide it "
            "where it turns to a different thing, never above the first "
            "paragraph; that heading line is the only markup allowed — the "
            "prose is plain text with no other Markdown. Prose for a reader, "
            "not a list."
        ),
    )
    sources: List[str] = Field(
        default_factory=list,
        description=(
            "1-3 Wikipedia URLs that document THIS event. The subject's own "
            "article when no related article covers it specifically."
        ),
    )
    background_image_queries: List[str] = Field(
        default_factory=list,
        description=(
            "3-4 Wikimedia Commons search queries, each for a DIFFERENT thing "
            "the background report names — the machine, the building, the "
            "document, the place. Not portraits of the subject. Empty when "
            "the background is null: there is no report to illustrate."
        ),
    )


SYSTEM = (
    "You are a research assistant specializing in biographical event details. "
    "You decide first whether the sources have anything to say around one "
    "event, and only then write it: a short passage of background, in prose, "
    "for a reader who has just read the event's own description and wants to "
    "know what surrounded it. It must add to that description rather than "
    "restate it, and it must be about that event rather than about the life "
    "or the era around it. An event the sources record without documenting "
    "gets no passage, and you say so by returning null. All output must be in "
    "American English only."
)

# The slide already carries the event. The report is the one part of the
# pipeline asked to write rather than to extract, and every rule here exists
# to keep it from restating what the reader has just read: the description is
# given as the thing to go beyond, and the questions name what the reader
# cannot get from it. How the sentences read is the shared block appended at
# the end; the earlier wording here asked for "tension" and for "what is
# contested", and the reports answered with a contrast in three sentences of
# four, each fact set against an alternative nobody had proposed.
#
# The gate opens the block because "do not restate the description" and "write
# 250-350 words" between them leave exactly one way out for an event the
# sources record in a sentence, and the reports took it: they wrote the life
# instead. A wedding got the groom's degree, his doctorate and the company he
# founded five years later; Otto Wagner's two marriages each got the
# Ringstrasse. None of it repeated the description, all of it was sourced, and
# none of it was background to a wedding. What the earlier wording lacked was
# not a prohibition but a decision to make first — the instructions assumed a
# report and asked only how to write it, so the model never reached the
# question of whether there was one. Returning null costs the reader nothing:
# `hasBackgroundReport` in eventDepth.js offers the way down only where a
# report stands, so an event without one is a slide the reader swipes past.
REPORT_INSTRUCTIONS = """\
IS THERE A REPORT HERE AT ALL? GATHER, THEN DECIDE:
- The layer you are writing does not have to exist. The story offers the way down
  only where a report was written, so an event without one costs the reader
  nothing — they finish the description and swipe on. A report that had nothing to
  say and said it anyway costs them a screen of prose that is not about what they
  opened
- GATHER FIRST, IN EVENT_SPECIFIC_MATERIAL, before you write a word of prose. Read
  the articles below properly, past their opening paragraphs, and note EVERY fact
  they give that stands around this event: how it came about, what it took, the
  circumstances it happened in, the room, the machine, the money, the people in it
  and what they were to the subject, how it went, how it was received, what
  followed from it. One short note per fact. Be exhaustive here — this list is
  where the reading happens, and a list of one from an article that discusses the
  event at length means you skimmed it
- Notes are working material, not prose, so the rules about the description do not
  apply to them: note a fact the description also carries if the sources give more
  of it. What disqualifies a note is being about something else — the era, the
  city, the institution, the subject's career at large — rather than about this
  event
- THEN JUDGE THE LIST YOU HAVE. Several notes that say something around the event
  are a report; write it from them. A list that only restates that the event
  happened — its date, its names, the bare fact — is not a report, however famous
  the person or eventful the decade
- WHEN THE LIST COMES TO NOTHING, RETURN NULL FOR THE BACKGROUND. This is a correct
  answer and a frequent one. Lives are documented unevenly: the famous paper has
  twenty paragraphs behind it and the wedding has half a sentence — "in 1951 he
  married her", "the family moved to Bern" — and the honest report on the wedding
  is no report. Null is also the answer when the call fails to find material it
  suspects exists; write nothing rather than filling in from memory
- THE FAILURE THIS EXISTS TO STOP: an event the sources record in a sentence, and a
  passage that fills the space with everything around it. A 1951 wedding whose
  report opens on the groom's 1948 degree, moves to the doctorate he began after
  it, and ends on the company he founded in 1956 is a résumé printed under a
  wedding — true in every sentence, sourced, and about four other slides. Ask of
  each paragraph before you keep it: would this sit just as well under the slide
  before or the slide after? Then it is not background to this event, and if
  nothing is left once you have cut it, the answer is null
- Thin sources are a reason to write less or nothing. They are never a reason to
  write wider

THE BACKGROUND REPORT, once the gate above is passed:
- Write for a curious reader who has finished the description and wants the story
  behind it. This is by far the longest thing you write here and the only one
  addressed to a reader rather than to a schema.
  Depth here is specificity, not length: a reader who has chosen to scroll down
  has asked for what the description could not hold, and every sentence that
  restates it or hedges toward the general spends the budget on nothing
- LENGTH FOLLOWS THE MATERIAL: up to 350 words in 2-4 paragraphs where your notes
  carry it, fewer where they do not. There is no minimum. One paragraph that is
  entirely about this event is a better layer than three that reach past it, and
  padding a thin report out to a length is precisely how a report stops being
  about its event. Never write toward a word count
- Prose. Complete sentences, no bullets, no lists
- Separate paragraphs with a blank line
- HEADINGS, where the report turns to a genuinely different thing: a line of its
  own beginning with '## ', two to five words, naming what the paragraphs under it
  are about. Use at most one in a report of this length, never one per paragraph,
  and never above the opening paragraph — the reader has just arrived from the
  event and wants prose, not a table of contents. A report that runs as a single
  argument takes none at all
- A heading names the thing it is about, not the part of the report it is,
  and is set in sentence case: the first word and proper nouns, nothing else
  * GOOD: '## The bombe on the floor', '## What Bletchley kept quiet'
  * BAD: '## Background', '## Aftermath', '## A Cover Kafka Rejected'
- The '## ' heading line is the ONLY markup the interface understands here. The
  prose itself is rendered verbatim, so never write Markdown in it: no *emphasis*
  or **bold**, no `code`, no [links](url). A title of a work stands plain in the
  sentence — 'after Childe Harold's Pilgrimage', not 'after *Childe Harold's
  Pilgrimage*' — and any asterisks you write will show on screen as asterisks
- BUILD IT LIKE A REPORT, roughly in this order, as the material allows:
  1. THE SITUATION THIS EVENT SAT IN. Not the era and not the life, but the
     circumstances the sources attach to this event: the institution as it bore on
     it, the state of the work it belonged to, the household it happened in, the
     politics that reached it. Open here, not on the subject's name
  2. THE SPECIFICS. The concrete detail that makes it real: who else was working on
     it, what the state of the art was, how long it took, what it cost, what it was
     competing against, the machine, the room, the number, the rule
  3. ONE THING AT LENGTH. Pick the single most telling episode, object, argument or
     obstacle the sources describe and give it a paragraph of its own — how it
     actually worked, how it actually went, what was actually said. A whole paragraph
     on one thing beats a sentence each on five
  4. WHAT CAME OF IT. What changed afterward, who took it up, how it was received at
     the time, stated as the facts the sources give. End on the last of them; the
     report has no closing sentence that weighs the event
- DETAIL IS THE POINT. A sentence that could be written about any event of this kind
  is a wasted sentence. Prefer the specific over the general every time:
  * WEAK: 'The work was important for the development of computing.'
  * STRONG: 'The bombe reduced a search of 159 quintillion settings to a few hours,
    and by 1943 more than two hundred of them were running.'
- Name names, places, institutions, machines, titles, quantities and dates that the
  sources give you. A background report with no proper nouns in it is not a report
- Where the sources disagree or correct a common account, give each position as a fact
  with who held it, in its own sentence. Do not frame it as a contrast ("not X but Y",
  "less X than Y"); say what each source says
- HARD RULE - ADD, NEVER RESTATE:
  * The reader has just read the description. Repeating any of it is a failure
  * Do not re-tell what happened, who was there, when, or where
  * Every sentence must carry a fact or a consequence the description lacks
- HARD RULE - BE ABOUT THIS EVENT:
  * Every paragraph answers "what surrounded THIS event". A paragraph about the
    subject's career, the city's century, or the field's development is off the
    slide unless this event is what it is about
  * A sentence equally true printed under a different event of this life belongs to
    that event. The other slides tell their own stories, and the outline below says
    which ones they are
  * Test each paragraph before you keep it: if this event were struck from the
    story, would the paragraph still stand exactly as written? Then it is not
    background to it
- GROUNDING: the articles below are your material — use them. Read past their first
  paragraph. Do not speculate, and do not invent numbers, names, or dates. Where the
  sources are thin, write less rather than padding with generalities
- Do NOT use [[term|display]] markers here - they belong in the description only
- Write for someone who does not know the field. Name what an insider would assume
- American English. No bullet points, no meta-commentary about sources
- Return null whenever the gate at the top is not passed, and whenever cutting the
  paragraphs that are not about this event would leave nothing standing

SOURCES (1-3 Wikipedia URLs):
- URLs that document THIS event, chosen from the subject's article and the related
  articles below. A related article is a source ONLY if it actually recounts this
  event; the subject's own article is the right answer whenever none does

BACKGROUND_IMAGE_QUERIES (3-4 short Commons searches):
- What would ILLUSTRATE the report you just wrote: the machine, the
  building, the document, the instrument, the place, the diagram
- Name the thing, not the person. The slide already carries the subject's own
  pictures, and a second portrait of them illustrates nothing
- 2-5 words each, the words a photograph of it would be filed under
  * GOOD: 'Bombe machine Bletchley Park', 'Enigma machine naval four-rotor'
  * BAD: 'Alan Turing portrait', 'cryptanalysis', 'World War II'
- Each query names a DIFFERENT thing, drawn from a different part of the report.
  Four searches for four angles on one machine return the same photograph four times
- Only things the report actually mentions. Return an empty list rather than
  guessing at something that might exist
"""


def accepted_report(parsed: Optional[BackgroundOnly]) -> str:
    """The passage the call is allowed to keep, or "" when it has no ground.

    The gate at the top of the instructions asks the call to note what the
    sources say about this event before it writes anything, and to return null
    when that comes to nothing. A call that notes nothing and then writes three
    paragraphs anyway has written exactly the report the gate exists to refuse,
    and it is refused here: the two answers contradict each other, and the one
    made before the prose was under way is the one to believe.

    This is the whole of the enforcement. How much material is enough stays a
    judgment for the call that read the articles — a count would only teach it
    to pad the list instead of the prose — so a single honest note that
    carries a paragraph is accepted, and an empty list is not.
    """
    if parsed is None:
        return ""
    passage = (parsed.background or "").strip()
    if not passage:
        return ""
    if not [note for note in parsed.event_specific_material if str(note).strip()]:
        return ""
    return passage


def _decline_reason(parsed: Optional[BackgroundOnly]) -> str:
    """Why an event ends the step without a report, for the run log.

    The three cases read the same in the dataset and mean different things in
    a log: a refusal the gate was built for, a call that contradicted its own
    gate, and a call that failed. Only the last is a defect.
    """
    if parsed is None:
        return "the call gave no answer"
    if (parsed.background or "").strip():
        return "it wrote one with nothing event-specific behind it"
    return "the sources say nothing around this event"


# ============================================================================
# BACKGROUND ILLUSTRATIONS
# ============================================================================

# Three per report: the layer deals them out between the paragraphs, so a
# report of four or five paragraphs can carry three without turning into a
# gallery — and one picture on a page this long reads as a token.
BACKGROUND_IMAGE_LIMIT = 3


class ChosenImages(BaseModel):
    """Which candidates, if any, actually illustrate the report."""

    keep: List[int] = Field(
        default_factory=list,
        description=(
            "Indexes of candidates that genuinely depict what the report "
            "describes, best first, at most three. Empty when none do."
        ),
    )


CHOOSER_SYSTEM = (
    "You decide whether a picture illustrates a text. You are strict: a picture "
    "that merely shares a word with the text illustrates nothing, and an "
    "irrelevant picture printed beside a report is worse than no picture."
)


# A Commons description field is whatever the uploader typed there, and often
# what they typed was their own paperwork. The layer prints the caption under
# the picture, where "Author: Schadel URL: http://turing.izt.uam.mx Made by me
# on..." reads as a bug.
_CAPTION_JUNK = re.compile(
    r"(author\s*:|source\s*:|https?://|own work|made by me|permission\s*:"
    r"|other[_ ]versions|photographer[,:]|owner of|\{\{|\[\[)",
    re.IGNORECASE,
)


def background_image_key(url: str) -> str:
    """A Commons file identified by its filename, not by the size asked for."""
    name = unquote(str(url or "")).split("/")[-1].split("?")[0]
    return re.sub(r"^\d+px-", "", name).lower()


def background_caption(candidate: Dict[str, Any], query: str) -> str:
    """A line fit to print under the picture.

    The uploader's description when it reads like one, the filename when it
    does not — a filename is at least always about the thing — and the query
    when there is neither.
    """
    caption = " ".join(str(candidate.get("caption") or "").split())
    if caption and not _CAPTION_JUNK.search(caption):
        if len(caption) > 160:
            head = caption[:160].rsplit(". ", 1)[0]
            caption = (head + ".") if len(head) > 40 else caption[:157].rstrip() + "…"
        return caption
    filename = str(candidate.get("filename") or "")
    stem = re.sub(r"\.[A-Za-z0-9]+$", "", filename).replace("_", " ").strip()
    return stem or query


def _background_candidates(
    queries: List[str], already_shown: Set[str]
) -> List[Dict[str, Any]]:
    """What Commons returns for the call's own queries, deduplicated.

    The event's own pictures are excluded: the slide above is already showing
    them, and an illustration the reader has just scrolled past illustrates
    nothing. Only images carrying a license are kept, because the layer prints
    a credit under every picture and one with no credit cannot be published.
    """
    found: List[Dict[str, Any]] = []
    seen = set(already_shown)
    for query in queries[:4]:
        # Commons ranks by keyword match, and the thing itself is often a few
        # places down behind a map, a modern plaque, and somebody's holiday
        # photograph. The critic reads all of them and mostly says no, so a
        # deeper pool costs one longer prompt and is the difference between a
        # report with one illustration and one with three.
        results = filter_images_by_quality(search_wikimedia_commons(query, limit=12))
        for candidate in results[:6]:
            url = candidate.get("url")
            if not url or background_image_key(url) in seen:
                continue
            if not candidate.get("license"):
                continue
            found.append(
                {
                    "url": url,
                    "caption": background_caption(candidate, query),
                    "source": candidate.get("source"),
                    "creator": candidate.get("creator"),
                    "license": candidate.get("license"),
                    "licenseUrl": candidate.get("licenseUrl"),
                    "query": query,
                    # Not stored — the filename is shown to the critic and then
                    # dropped. Commons captions are often a sentence about the
                    # upload rather than about the subject, and the filename is
                    # the one field that always names the thing.
                    "_filename": candidate.get("filename") or "",
                    # Shown to the critic for the same reason: a present-day
                    # photograph of a building names the building as if it had
                    # always stood there, and only its date says otherwise.
                    "_taken": image_year_taken(candidate),
                }
            )
            seen.add(background_image_key(url))
    return found


def fetch_background_images(
    client: OpenAI,
    report: str,
    queries: List[str],
    already_shown: Set[str],
    wanted: int = BACKGROUND_IMAGE_LIMIT,
) -> List[Dict[str, Any]]:
    """Pictures for the report: searched by its own queries, then read.

    A Commons keyword search is a keyword search. Asking it for "On Computable
    Numbers manuscript" returned a 16th-century Mexican codex, and asking after
    Christopher Morcom returned a steam engine built by Belliss & Morcom.
    Roughly half of what came back shared a word with the report and nothing
    else, so what comes back is now read against the report before any of it is
    kept, and keeping none is a normal outcome.
    """
    candidates = _background_candidates(queries, already_shown)
    if not candidates:
        return []

    listing = "\n".join(
        f"[{index}] {candidate['_filename'] or '(no filename)'} — {candidate['caption']}"
        + (
            f" (taken {candidate['_taken']})"
            if candidate.get("_taken") is not None
            else ""
        )
        for index, candidate in enumerate(candidates)
    )
    parsed = parse_structured(
        client,
        # A critic, and config.py is explicit that a critic weaker than the
        # generator is worse than no critic. On the small model this one kept
        # letting the Belliss & Morcom steam engine through, which is the exact
        # confusion its instructions name.
        model=DEFAULT_MODEL,
        reasoning_effort=DEFAULT_REASONING_EFFORT,
        input=[
            {"role": "system", "content": CHOOSER_SYSTEM},
            {
                "role": "user",
                "content": (
                    "Which of these pictures illustrate the report below?\n\n"
                    "Each candidate is given as its Commons filename and its "
                    "caption. Read both: a caption is often about the upload, "
                    "and the filename is what names the thing. A '(taken "
                    "YEAR)' note is when the photograph was made, from the "
                    "file's own metadata: a photograph taken decades after "
                    "the report's events shows what stands there now.\n\n"
                    "KEEP a picture that shows a thing the report actually "
                    "names: the machine, the building, the room, the document, "
                    "the instrument, the place. Ask of each one: could this "
                    "picture be printed beside this paragraph with a straight "
                    "face? If you have to explain the connection, the answer "
                    "is no.\n"
                    "REJECT, without exception:\n"
                    + STAND_IN_REJECTION_INSTRUCTIONS
                    + "- a map, plan, chart, or diagram of somewhere, unless the "
                    "report is about that ground itself\n"
                    "- a montage, collage, poster, book cover, film still, or "
                    "'events of the year' composite: it depicts nothing in "
                    "particular, and a film the report merely alludes to is "
                    "not an illustration of the report\n"
                    "- a portrait of any person, and any picture of the "
                    "subject: the slide above already carries those\n"
                    "- a picture of a different subject from the same era or "
                    "field, however evocative\n"
                    "- a reenactment standing in for the thing itself\n"
                    "- a picture whose caption is about some later incident at "
                    "the place (building works, a protest, a fire) rather than "
                    "the place in the role the report gives it\n"
                    "Keep at most three, and every one you keep must show a "
                    "DIFFERENT thing: two photographs of the same machine are "
                    "one illustration printed twice, so keep the better one "
                    "and move on. Best first.\n"
                    "THREE IS A CEILING, NOT A TARGET. Do not reach for it. "
                    "One picture that plainly shows what the report describes "
                    "beats three that gesture at it, and keeping none is a "
                    "normal answer.\n\n"
                    f"REPORT:\n{report}\n\n"
                    f"CANDIDATES:\n{listing}\n"
                ),
            },
        ],
        text_format=ChosenImages,
        label="Illustrations for a background report",
    )
    if parsed is None:
        return []

    # One picture per query, enforced here rather than asked for: the two
    # queries are the two things the report wanted illustrated, so taking two
    # answers to the same one prints the same thing twice — which is what kept
    # happening with the Manchester Mark I no matter how the instruction was
    # worded.
    kept: List[Dict[str, Any]] = []
    used_queries = set()
    for index in parsed.keep:
        if not 0 <= index < len(candidates) or len(kept) >= wanted:
            continue
        candidate = candidates[index]
        if candidate["query"] in used_queries:
            continue
        used_queries.add(candidate["query"])
        kept.append({k: v for k, v in candidate.items() if not k.startswith("_")})
    return kept


def illustrate_event(
    client: OpenAI,
    event: Dict[str, Any],
    report: str,
    queries: List[str],
) -> List[Dict[str, Any]]:
    """Put the report's illustrations on the event, or take them off."""
    shown = {
        background_image_key(image.get("url", ""))
        for image in (event.get("images") or [])
        if isinstance(image, dict)
    }
    pictures = (
        fetch_background_images(client, report, queries, shown) if queries else []
    )
    if pictures:
        event["background_images"] = pictures
        for picture in pictures:
            print(f"    image: {picture['query']} -> {picture['caption'][:60]}")
    else:
        event.pop("background_images", None)
        print("    no illustrations found for the report")
    return pictures


# ============================================================================
# THE PROMPT
# ============================================================================


def build_background_avoidance(
    known_annotations: Optional[Dict[str, str]] = None,
    story_outline: Optional[List[str]] = None,
    person_summary: Optional[str] = None,
    known_people: Optional[Dict[str, str]] = None,
    cited_sources: Optional[List[str]] = None,
) -> str:
    """What the report must be steered around: everything the reader has.

    The annotations are the popups under the very description the report sits
    below, and a passage written without being shown them repeats them. The
    outline is the whole story, not just the two events either side: a report
    shown only its neighbours wanders into whatever is a slide or two further
    along — Turing's death opened on the Manchester laboratory and spent two
    paragraphs on the morphogenesis paper, which is its own slide, two events
    back.
    """
    if not (
        known_annotations
        or story_outline
        or person_summary
        or known_people
        or cited_sources
    ):
        return ""

    section = "\n" + "=" * 60 + "\n"
    section += "WHAT THE READER ALREADY HAS — DO NOT SAY IT AGAIN:\n"
    section += "=" * 60 + "\n"

    if person_summary:
        section += f"\nWho the subject is (assume this is known):\n{person_summary}\n"

    if known_annotations:
        section += (
            "\nTerms already explained ON THIS SLIDE. A tap opens each of these, "
            "word for word, under the description your passage follows. Explaining "
            "any of them again is the most visible way to waste this passage — "
            "write past them, and where one is relevant, USE it as known ground "
            "rather than defining it:\n"
        )
        for term, explanation in known_annotations.items():
            section += f"  - {term}: {explanation}\n"

    if known_people:
        section += (
            "\nPeople already introduced ON THIS SLIDE. Each is a chip the reader "
            "can open, carrying exactly this description of who they were to the "
            "subject. Name them freely where the story needs them, but do not "
            "introduce them — that is the chip's job, and doing it again here is "
            "the same words twice:\n"
        )
        for name, described in known_people.items():
            section += f"  - {name}: {described}\n"

    if story_outline:
        section += (
            "\nThe rest of this life as the story tells it — every other slide the "
            "reader can swipe to. Each of these gets its own description, so a "
            "paragraph about one of them is a paragraph stolen from a slide that "
            "already has it. Stay on YOUR event: mention another only as the thing "
            "yours led to or came out of, in a clause, never as a subject to be "
            "told:\n"
        )
        for entry in story_outline:
            section += f"  - {entry}\n"

    if cited_sources:
        section += (
            "\nWhat this event cites today. Keep any that genuinely documents it "
            "and drop any that does not; an article about a different episode of "
            "the same life is not one:\n"
        )
        for url in cited_sources:
            section += f"  - {url}\n"

    section += (
        "\nWhat is left is what you are for: the situation around the event that "
        "neither the description, nor these explanations, nor the other slides "
        "supply.\n"
    )
    return section


def _related_articles(person_id: str) -> List[Dict[str, Any]]:
    """The cached related articles, or none — the event alone still works."""
    try:
        path = get_cache_dir(person_id) / "related_articles.json"
    except Exception:  # noqa: BLE001 — an absent cache is a normal state here
        return []
    if not path.exists():
        return []
    try:
        return cast(List[Dict[str, Any]], json.loads(path.read_text(encoding="utf-8")))
    except json.JSONDecodeError:
        return []


def _wikipedia_page(person_id: str) -> Optional[Dict[str, Any]]:
    """The cached subject article, or nothing — the report degrades to the
    related articles alone, which is all it had before the article joined the
    prompt."""
    try:
        path = get_cache_dir(person_id) / "wikipedia_page.json"
    except Exception:  # noqa: BLE001 — an absent cache is a normal state here
        return None
    if not path.exists():
        return None
    try:
        return cast(Dict[str, Any], json.loads(path.read_text(encoding="utf-8")))
    except json.JSONDecodeError:
        return None


def _skeleton(event: Dict[str, Any]) -> EventSkeleton:
    """The parts of a stored event the article filter reads.

    The classification comes along: a background has to work for every kind of
    event, and knowing which kind it is is how.
    """
    return EventSkeleton(
        date=event.get("date", ""),
        date_precision=event.get("date_precision", "day"),
        date_end=event.get("date_end"),
        date_end_precision=event.get("date_end_precision"),
        date_note=event.get("date_note"),
        age=event.get("age"),
        title=event.get("title", ""),
        description=event.get("description", ""),
        event_class=_classification(event.get("event_class")),
    )


def _classification(raw: Any) -> Optional[Any]:
    """The stored classification as the pipeline's model, or nothing."""
    if not isinstance(raw, dict) or not raw.get("type"):
        return None
    model = CLASSIFICATION_MODELS.get(raw["type"])
    if model is None:
        return None
    try:
        return model(**raw)
    except ValidationError:
        # A block the schema has since moved on from is not worth failing a
        # background over; the event is simply presented unclassified.
        return None


def _story_outline(events: List[Dict[str, Any]], index: int) -> List[str]:
    """Every other slide of this story, as the reader can swipe to them.

    The two either side come with their descriptions, because those are what a
    report is most likely to run straight into. The rest come as a line each,
    which is enough to mark the ground as taken: shown only its neighbours, the
    report for Turing's death spent half its length on the morphogenesis paper,
    two slides back and a landmark with a report of its own.
    """
    lines = []
    for position, event in enumerate(events):
        if position == index:
            continue
        entry = f"{event.get('date', '?')} — {event.get('title', '')}"
        if abs(position - index) == 1:
            description = _plain(event.get("description") or "")
            if description:
                entry += f": {description}"
        lines.append(entry)
    return lines


def _connections_for(
    event: Dict[str, Any], network: Dict[str, Any]
) -> List[Dict[str, Any]]:
    """The network entries for the people this event names.

    Matched on the name as the event writes it, which is how the interface
    matches them too: a person the network does not know gets no chip, and so
    is not something the passage has to avoid introducing.
    """
    involved = {str(name).strip() for name in (event.get("involved_people") or [])}
    if not involved:
        return []
    return [
        connection
        for connection in (network.get("connections") or [])
        if str(connection.get("person_name", "")).strip() in involved
    ]


def _panel_lines(event: Dict[str, Any]) -> List[str]:
    """The classification fields the interface already presents in a panel."""
    classification = event.get("event_class")
    if not isinstance(classification, dict):
        return []
    lines = []
    for key, value in classification.items():
        if value in (None, "", []):
            continue
        lines.append(f"  - {key}: {value}")
    return lines


def build_report_prompt(
    event: Dict[str, Any],
    person_name: str,
    related: List[Dict[str, Any]],
    *,
    events: List[Dict[str, Any]],
    index: int,
    person_summary: Optional[str] = None,
    network: Optional[Dict[str, Any]] = None,
    subject_article: Optional[Dict[str, Any]] = None,
) -> Prompt:
    """The whole prompt for one report, cut where its reusable part ends.

    The material and the rules are the same for every report of a person; the
    event, the story around it and the articles chosen for it are not. The call
    site marks the boundary so the provider reuses the first part instead of
    reading it again per report.
    """
    skeleton = _skeleton(event)
    network = network or {}
    filtered = filter_related_articles_for_event(
        skeleton, related, max_articles=RELATED_ARTICLE_COUNT
    )
    cited = [url for url in (event.get("sources") or []) if url]
    known = {
        term: (annotation or {}).get("explanation", "")
        for term, annotation in (event.get("annotations") or {}).items()
        if (annotation or {}).get("explanation")
    }
    people = {
        connection.get("person_name", ""): connection.get(
            "relationship_description", ""
        )
        for connection in _connections_for(event, network)
        if connection.get("relationship_description")
    }

    # The material and the rules first, this event last: a provider reuses a
    # repeated prefix only while nothing varying precedes it.
    event_section = "\n" + "=" * 60 + "\n"
    event_section += "WRITE THE BACKGROUND REPORT FOR THIS EVENT:\n"
    event_section += "=" * 60 + "\n\n"
    event_section += f"Title: {event.get('title', '')}\n"
    event_section += f"Date: {event.get('date', '')}\n"
    description = _plain(event.get("description") or "")
    event_section += f"Description: {description}\n"
    event_section += f"Subject: {person_name}\n"

    panel = _panel_lines(event)
    if panel:
        event_section += (
            "\nThis event is classified, and the interface already presents "
            "these fields in a panel of their own beside the description. "
            "Never repeat them in the report:\n"
        )
        event_section += "\n".join(panel) + "\n"

    shared = _subject_article_prompt_section(subject_article)

    shared += "\n" + "=" * 60 + "\n"
    shared += REPORT_INSTRUCTIONS
    shared += "\n" + PROSE_STYLE_INSTRUCTIONS + "\n"

    specific = event_section

    specific += build_background_avoidance(
        known_annotations=known,
        story_outline=_story_outline(events, index),
        person_summary=person_summary,
        known_people=people,
        cited_sources=cited,
    )

    specific += _related_articles_prompt_section(filtered)
    return Prompt(shared=shared, specific=specific)


# ============================================================================
# WRITING ONE PERSON
# ============================================================================


def _ego_network(person_id: str) -> Dict[str, Any]:
    """The network the chips are drawn from, or nothing."""
    path = PEOPLE_DIR / person_id / "ego_network.json"
    if not path.exists():
        return {}
    try:
        return cast(Dict[str, Any], json.loads(path.read_text(encoding="utf-8")))
    except json.JSONDecodeError:
        return {}


def _propagate_sources(person_id: str, events: List[Dict[str, Any]]) -> None:
    """Carry corrected citations into the translated copies.

    A URL is not prose and is never translated, so a translated copy keeps
    whatever citation it was written with — which, for these events, is the
    wrong one. The passage itself is prose and waits for the translator.
    """
    for lang_dir in sorted((PEOPLE_DIR / person_id).iterdir()):
        if not lang_dir.is_dir() or lang_dir.name.startswith("_"):
            continue
        target = lang_dir / "life_events.json"
        if not target.exists():
            continue
        payload = read_json(target)
        target_events = payload.get("events") or []
        if len(target_events) != len(events):
            print(f"    [!] {lang_dir.name}: different event count, sources not synced")
            continue
        changed = False
        for target_event, event in zip(target_events, events):
            if event.get("sources") and target_event.get("sources") != event["sources"]:
                target_event["sources"] = list(event["sources"])
                changed = True
        if changed:
            write_json(target, payload)
            print(f"    sources synced to {lang_dir.name}")


def generate_event_backgrounds(
    person_id: str,
    client: Optional[OpenAI] = None,
    *,
    overwrite: bool = False,
    dry_run: bool = False,
) -> int:
    """Write the reports for one person's deep events. Returns how many.

    The selection is the story's own: the ported deep-event rule, computed on
    the events and the ego network as they stand on disk. An event the rule
    does not select gets no report — the story would never show it — and a
    selected event that already carries one is left alone unless ``overwrite``.
    A selected event whose sources say nothing around it gets none either, and
    under ``overwrite`` loses the one it has: the refusal is the point of the
    rewrite, so it has to reach the dataset.
    """
    path = PEOPLE_DIR / person_id / "life_events.json"
    data = read_json(path)
    events = data.get("events") or []
    person = data.get("person") or {}
    person_name = person.get("name") or person_id
    person_summary = person.get("summary")
    person_wikipedia = person.get("wikipedia")
    network = _ego_network(person_id)

    unweighted = sum(
        1 for event in events if not isinstance(event.get("weight"), (int, float))
    )
    if unweighted:
        print(
            f"  {person_id}: {unweighted} event(s) carry no weight — the dataset "
            "predates proposal weighting. Flag it in data/outdated.md and "
            "regenerate it instead of filling reports here."
        )
        return 0

    selected = select_deep_event_indexes(events, network)
    targets = [
        index
        for index in sorted(selected)
        if overwrite or not (events[index].get("background") or "").strip()
    ]
    if not targets:
        print(f"  {person_id}: nothing to write ({len(selected)} deep event(s))")
        return 0

    if dry_run:
        for index in targets:
            weight = get_event_weight(events[index])
            print(
                f"  {person_id}[{index}] would write ({weight:.2f}): "
                f"{events[index].get('title')}"
            )
        return 0

    if client is None:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY is not set.")
        client = OpenAI(api_key=api_key)

    related = _related_articles(person_id)
    subject_article = _wikipedia_page(person_id)

    # The reports are written side by side. Each one reads the story as it
    # stands on disk and writes only its own event, so no report waits on
    # another; the shared material above is read only.
    workers = min(worker_count(), len(targets))
    if workers > 1:
        print(f"  {person_id}: writing {len(targets)} report(s), {workers} at a time")

    def write_report(index: int) -> str:
        """Report, sources, and pictures for one event; what became of it.

        Returns what the event ended up with: ``"written"`` for a report,
        ``"dropped"`` where a report already on the event did not survive the
        gate, ``"sources"`` where only the citations moved, and ``"none"``
        where the event is left exactly as it was found.
        """
        event = events[index]
        title = str(event.get("title", "")).encode("ascii", "replace").decode("ascii")
        print(f"  {person_id}[{index}] {title}")

        parsed = parse_structured(
            client,
            model=REPORT_MODEL,
            reasoning_effort=REPORT_REASONING_EFFORT,
            input=build_report_prompt(
                event,
                person_name,
                related,
                events=events,
                index=index,
                person_summary=person_summary,
                network=network,
                subject_article=subject_article,
            ).messages(SYSTEM),
            text_format=BackgroundOnly,
            label=f"Background for '{title}'",
        )
        passage = accepted_report(parsed)
        outcome = "written"
        if parsed is not None and passage:
            event["background"] = passage
            illustrate_event(client, event, passage, parsed.background_image_queries)
        else:
            outcome = "none"
            print(f"    [!] no report for [{index}]: {_decline_reason(parsed)}")
            # An overwrite pass is how a sharpened gate clears the reports the
            # old one let through, so a refused event loses the passage it had
            # along with the pictures that illustrated it. Without this the
            # rewrite that was meant to remove a report leaves it standing.
            had_report = event.pop("background", None)
            had_pictures = event.pop("background_images", None)
            if had_report or had_pictures:
                outcome = "dropped"
                print(f"    the report already on [{index}] is dropped")

        # Only URLs the call was actually shown. A model asked for a citation
        # will write a plausible one, and a plausible Wikipedia URL that 404s is
        # worse than the wrong-but-real article it replaces. This runs whether
        # or not there is a report: the call read this event against these
        # articles either way, and a refused report is no reason to leave a
        # citation that documents a different episode in place.
        if parsed is not None:
            allowed = citable_urls(person_wikipedia, related, event.get("sources"))
            chosen = keep_citable(parsed.sources, allowed)
            if chosen and chosen != event.get("sources"):
                print(f"    sources of [{index}]: {event.get('sources')} -> {chosen}")
                event["sources"] = chosen
                if outcome == "none":
                    outcome = "sources"
        return outcome

    outcomes = map_concurrently(targets, write_report, workers=workers)
    written = outcomes.count("written")
    dropped = outcomes.count("dropped")

    if any(outcome != "none" for outcome in outcomes):
        write_json(path, data)
        refused = len(outcomes) - written
        summary = f"wrote {written} report(s)"
        if refused:
            summary += f", refused {refused}"
        if dropped:
            summary += f" (dropping {dropped} that had one)"
        print(f"  {person_id}: {summary} in {path.name}")
        _propagate_sources(person_id, events)
    return written


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Write depth-layer background reports for deep events."
    )
    parser.add_argument("person_ids", nargs="*", help="Person IDs (default: all)")
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Rewrite reports that are already there.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Say what would be written, call nothing.",
    )
    args = parser.parse_args()

    ids = args.person_ids or person_ids()

    client = None
    if not args.dry_run:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            print("OPENAI_API_KEY is not set.")
            return 1
        client = OpenAI(api_key=api_key)

    total = 0
    for person_id in ids:
        if not (PEOPLE_DIR / person_id / "life_events.json").exists():
            print(f"  {person_id}: no dataset, skipping")
            continue
        total += generate_event_backgrounds(
            person_id,
            client,
            overwrite=args.overwrite,
            dry_run=args.dry_run,
        )

    print(f"\nWrote {total} report(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
