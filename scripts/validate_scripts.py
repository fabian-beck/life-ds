#!/usr/bin/env python3
"""Check the data's words for mixed writing systems.

The translator works token by token, and twice now a token has come back with
another alphabet spliced into a German word: "Zwillინგstöchter" with three
Georgian letters where "ing" belongs, "лекtionierte" opening in Cyrillic. Both
read fine at a glance, both render as tofu or worse on the slide, and nothing
in the pipeline looked at the characters.

The precise symptom is the mix, not the foreign script. A Cyrillic name in an
image credit ("Олег Мариненко") is attribution and correct; a German word
that is half Cyrillic is corrupt in any language. So this flags exactly one
shape: a single word carrying Latin letters and letters of another script.
One Greek letter alongside Latin is exempt — that is how physics writes
"hν" — but two are not, and one Cyrillic homoglyph is enough to flag,
because there is no notation that mixes those.

A URL is exempt, because its spelling belongs to the resource it names
rather than to a language. Commons holds the Houghton shelfmark
"AC85.Aℓ245" in a file name, and the link that reaches that file has to
carry the same letter.

Everything under ``data/`` is scanned — English references, translated
copies, registries, meta stories — except the caches, whose text is quoted
source material. There is no ACCEPTED list: no legitimate word mixes
alphabets this way, so every finding is a defect.

Usage:
    python scripts/validate_scripts.py            # exit 1 on any finding
    python scripts/validate_scripts.py --verbose  # list the files as scanned
"""

from __future__ import annotations

import argparse
import re
import sys
import unicodedata
from pathlib import Path
from typing import Any, Iterator, List, Optional, Tuple

from config import DATA_DIR
from utils.json_io import read_json

WORD = re.compile(r"[^\W\d_]+", re.UNICODE)
URL = re.compile(r"https?://\S+", re.UNICODE)

LATIN = (
    (0x0041, 0x005A),
    (0x0061, 0x007A),
    (0x00C0, 0x024F),
    (0x1E00, 0x1EFF),
    (0x2C60, 0x2C7F),
    (0xA720, 0xA7FF),
)
GREEK = ((0x0370, 0x03FF), (0x1F00, 0x1FFF))


def script_of(char: str) -> str:
    point = ord(char)
    for start, end in LATIN:
        if start <= point <= end:
            return "latin"
    for start, end in GREEK:
        if start <= point <= end:
            return "greek"
    return "other"


def control_characters(text: str) -> List[str]:
    """Control characters that have no business in prose or names.

    Frank Lloyd Wright's wife shipped as "Lazovi\\x0107" — the ć's escape
    sequence half-lost, leaving a control byte and stray digits the slide
    renders as garbage. Newlines and tabs are structure; everything else in
    Cc is corruption.
    """
    return [
        f"U+{ord(c):04X}"
        for c in text
        if unicodedata.category(c) == "Cc" and c not in "\n\r\t"
    ]


def mixed_script_words(text: str) -> List[str]:
    """The words whose letters come from more than one writing system.

    URLs are blanked out first. A link spells whatever the resource is called,
    so the mix that is corruption in prose is the address in a link.
    """
    corrupt: List[str] = []
    for match in WORD.finditer(URL.sub(" ", text)):
        word = match.group(0)
        letters = [c for c in word if unicodedata.category(c).startswith("L")]
        scripts = {script_of(c) for c in letters}
        if "latin" not in scripts or scripts == {"latin"}:
            continue
        greek = [c for c in letters if script_of(c) == "greek"]
        if scripts == {"latin", "greek"} and len(greek) == 1:
            continue
        corrupt.append(word)
    return corrupt


def strings_in(value: Any, path: str = "") -> Iterator[Tuple[str, str]]:
    if isinstance(value, str):
        yield path, value
    elif isinstance(value, dict):
        for key, child in value.items():
            yield from strings_in(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from strings_in(child, f"{path}[{index}]")


def data_files() -> List[Path]:
    return sorted(
        path for path in DATA_DIR.rglob("*.json") if "_cache" not in path.parts
    )


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args(argv)

    findings = 0
    scanned = 0
    for path in data_files():
        document = read_json(path)
        scanned += 1
        if args.verbose:
            print(f"scanning {path.relative_to(DATA_DIR.parent)}")
        for field, text in strings_in(document):
            for word in mixed_script_words(text):
                scripts = sorted(
                    {
                        unicodedata.name(c, "?").split()[0]
                        for c in word
                        if script_of(c) == "other"
                    }
                ) or ["GREEK"]
                print(
                    f"ERROR: {path.relative_to(DATA_DIR.parent)}{field}: "
                    f'"{word}" mixes Latin with {", ".join(scripts)}'
                )
                findings += 1
            for control in control_characters(text):
                print(
                    f"ERROR: {path.relative_to(DATA_DIR.parent)}{field}: "
                    f"control character {control}"
                )
                findings += 1

    print(f"\nScanned {scanned} data file(s), {findings} finding(s).")
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
