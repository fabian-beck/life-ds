#!/usr/bin/env python3
"""How the prose the reader sees is written, stated once.

Every phase that writes for a reader imports this block into its prompt: the
event descriptions and the conclusion, the background reports, the review
pass, the composer's article text, and the circle and stop cards of a meta
story. The translator carries the same rules for German. Stating them in one
place keeps the phases from asking for different prose, and keeps a rule that
turns out to be wrong from having to be found in seven prompts.

Each rule names a habit of model prose by the shape it takes on the slide,
with the sentence to write instead. Generic instructions moved nothing: the
Phase 1 prompt asked for "no verbose constructions" for a year while its
descriptions kept contrasting each fact against an alternative nobody had
proposed, and the background prompt asked for "tension" and "what is
contested" and got "not X but Y" in three reports of four. The composer, the
one prompt that named the constructions it did not want, was the one phase
whose prose had none of them.
"""

PROSE_STYLE_INSTRUCTIONS = """\
HOW THE PROSE READS. The reader is on a phone, reading one slide at a time, and
knows nothing of the field. Every sentence says what happened, to whom, where,
or when, in plain words, and stops.
- One statement per sentence. A sentence that needs a second clause to finish
  its thought is two sentences. No semicolon joining two clauses. No colon
  introducing an explanation, an example, or a list; write the sentence the
  colon stood in for. No dash setting off an aside; give the aside its own
  sentence or cut it.
- Say what was, never what it was not. No "rather than", "instead of", "not X
  but Y", "not only X but also Y", "less X than Y", "as much X as Y", "more X
  than Y" between two abstractions. Each of these argues against a reading
  nobody proposed. State the fact.
  * BAD: "The obstacle was not simply entrance examinations but university
    status."
  * GOOD: "Women could sit the examinations. They could not enroll."
- Report, do not interpret. An event does what it did. It does not "mark",
  "signal", "reflect", "underscore", "confirm", "cement", "embody", "affirm",
  "highlight", "demonstrate", "illustrate", "showcase", or "reinforce"
  anything. A sentence whose subject is "the move", "the decision", "the
  appointment", "the episode", "the period", "this", or "that" and whose verb
  is one of these is a verdict on the fact before it. Cut it, or put the next
  fact in its place.
  * BAD: "The book reflected his sustained interest in industrial production
    and political economy."
  * GOOD: "The book compared the factories he had visited in Britain and on
    the continent."
- Begin on a fact and end on the last fact. No opening sentence announcing what
  the paragraph will show. No sentence opening on "therefore", "thus", "in
  this way", "in short", or "taken together" to sum up the sentences before
  it. No closing sentence that generalizes the paragraph, weighs its
  significance, or looks ahead. When the facts are told, stop.
  * BAD: "The Kiel years therefore supplied a period of institutional
    stability and scholarly consolidation."
  * BAD: "The moment highlighted how far his early work had traveled."
- Plain words. Name what an insider would assume, and use the common word over
  the term of art. No "pivotal", "landmark", "seminal", "testament", "legacy",
  "journey", "trajectory", "hallmark", "cornerstone", "tapestry", "profound",
  "transformative", "enduring". No triad of adjectives or nouns set out for
  rhythm. One concept keeps one name throughout a text.
These rules hold for every field a reader sees, from a two-sentence
description to a four-paragraph report. They say how a sentence reads, not how
many there are: each prompt states the length its text needs, and a text under
that length has left out a fact the sources hold. Cut the construction, keep
the fact it carried."""


def description_contract_prompt() -> str:
    """What an event description is, as a prompt block.

    PROSE_STYLE_INSTRUCTIONS says how a sentence reads; this says what a
    description contains. Three calls may write one — Phase 1, Phase 2's
    refinement, and the review — and each used to carry its own partial copy
    of the content rules, grown one incident at a time, so that the rule
    keeping a description in its own moment was stated in one phase and
    absent from the class guidance another read last, and a birthplace
    dispute copied from the article passed every phase (issue #141). Stated
    as what a description is rather than a list of what it must not be,
    because a definition generalizes to the next case and a list of banned
    phrases covers exactly the cases it names. A function rather than a
    constant so the technical report renders it in every step drawer that
    lists it.
    """
    return (
        "WHAT AN EVENT DESCRIPTION IS:\n"
        "A description narrates one moment of a life. The slide around it shows the "
        "date, the place at city level, the people involved, the sources, and, for a "
        "classified event, the structured facts — the parents, the partner, the work, "
        "the destination. The prose says what those fields cannot.\n"
        "- It stands in the present of the event: what was happening, who was there, why "
        "it mattered then. Nothing that happened later belongs in it — not a consequence, "
        "a later move, or a retrospect. The chapters and the conclusion carry those.\n"
        "- It asserts. The story commits to one telling; the sources carry the evidence "
        "and the metadata carries the uncertainty (date_precision, date_note). Where the "
        "sources disagree — about a date, a place, an attribution — state the "
        "best-supported version at the precision the sources support, and keep the "
        "disagreement, the historiography, and the talk of sources out of the sentence.\n"
        "- It stands on its own. A reader who sees the prose alone learns who did what, "
        "with whom, and where, so the partner, the collaborator, the institution, and "
        "the place are named in the sentence even when a chip or a card beside it shows "
        "them too. What it does not restate is the structured detail the card holds: "
        "the duration of a marriage, the number of children, the cause of death as a "
        "term, the specification of an invention, the publisher of a work.\n"
        "- It is complete in two to four sentences: the event, the people and the place "
        "named, and what led to it or what it was for. One sentence is a caption, and a "
        "description of one sentence has left out a fact the sources hold.\n"
        "- It stays at the slide's granularity: no street addresses or house numbers "
        "where the location is a city.\n"
        "- It is plain text in American English: no Markdown, no emphasis marks, no "
        "links; a title of a work stands plain in the sentence.\n"
        "GOOD: 'Schönlein studied medicine in Landshut, learning from Andreas Röschlaub "
        "and Friedrich Tiedemann.'\n"
        "BAD (a later year): 'Schönlein studied medicine in Landshut, training that would "
        "later shape his bedside teaching.'\n"
        "BAD (talk of sources, street level): 'He was most likely born at 44 Crosby Row, "
        "though the exact birthplace is disputed.'\n"
        "BAD (leans on the card, one sentence): 'In 1930, she married a New York "
        "University professor.'\n"
        "GOOD: 'In 1930 she married Vincent Foster Hopper, who taught English at New "
        "York University. She had just finished her master's degree in mathematics at "
        "Yale.'\n"
    )
