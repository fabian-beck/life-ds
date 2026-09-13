#!/usr/bin/env python3
"""How much of one piece of prose already stands in another.

An annotation is worth a tap when it says something the slide does not. The
rule for "does not" is lexical and deliberately crude: strip the words that
carry no content, stem what is left, and ask how much of the shorter text the
longer one already holds. It catches the restatement written in the same
words and lets a paraphrase through, which is the trade a generator can make
without a model in the loop.

`events/normalize.py` drops a gloss that restates its own slide under this
rule.
"""

from __future__ import annotations

import re

STOPWORDS = frozenset(
    """a an the of to in on at for and or by with from as is was were be been
    being it its this that these those his her their he she they them into over
    under than then there here which who whom whose what when where while not
    no nor so such but if also very more most much many some any each both all
    one first later early after before during between within without through
    about against among across per via up out off""".split()
)

# How much of an explanation may already stand in the slide before the reader
# learns nothing by tapping the term.
RESTATED_SHARE = 0.6

_SUFFIXES = (
    "ically",
    "ical",
    "ing",
    "ions",
    "ion",
    "ies",
    "ers",
    "er",
    "ed",
    "es",
    "s",
    "al",
    "ly",
)


def stem(word: str) -> str:
    """A word reduced to what it shares with its own inflections."""
    for suffix in _SUFFIXES:
        if word.endswith(suffix) and len(word) - len(suffix) >= 4:
            return word[: -len(suffix)]
    return word


def content_words(text: str) -> set:
    """The stemmed words of a text that carry its content."""
    return {
        stem(word)
        for word in re.findall(r"[a-z0-9]+", text.lower())
        if word not in STOPWORDS and len(word) > 1
    }


def restates(explanation: str, context: str, term: str = "") -> bool:
    """Whether the explanation is mostly words the context already carries.

    The share is measured against the context and the term together, so a
    gloss that names the term it explains is not charged for doing so. An
    explanation with no content words at all restates nothing.
    """
    words = content_words(explanation)
    if not words:
        return False
    known = words & (content_words(context) | content_words(term))
    return len(known) / len(words) >= RESTATED_SHARE
