"""Which URLs a generation step may cite.

A model asked for a citation writes a plausible one, and a plausible Wikipedia
URL that leads nowhere is worse than no citation: Babbage's network cited
``en.wikipedia.org/wiki/Georg_Scheutz``, which is no article. A step therefore
keeps only the URLs of the articles it was shown.
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional, Set
from urllib.parse import unquote


def normalize_url(url: Any) -> str:
    """Compare URLs the way Wikipedia treats them: percent-encoding and
    underscores are spelling, not identity."""
    return unquote(str(url or "")).replace("_", " ").rstrip("/").lower()


def citable_urls(
    subject_url: Optional[str],
    related: Iterable[Dict[str, Any]],
    existing: Optional[Iterable[Any]] = None,
) -> Set[str]:
    """Every URL a call is allowed to cite, normalized.

    The subject's article, the related articles the call was shown, and
    whatever the record already cites — the last because a citation already in
    the corpus is a real article whether or not this call's article filter
    happened to surface it, and dropping a good one for being absent from a
    five-item shortlist is how "Published the Turing test paper" lost its
    citation of the paper.
    """
    urls = {normalize_url(subject_url)} if subject_url else set()
    for article in related:
        if isinstance(article, dict) and article.get("url"):
            urls.add(normalize_url(article["url"]))
    for url in existing or []:
        if url:
            urls.add(normalize_url(url))
    urls.discard("")
    return urls


def keep_citable(urls: Any, allowed: Set[str]) -> List[str]:
    """The URLs among ``urls`` that ``allowed`` holds, in their order."""
    if isinstance(urls, str):
        urls = [urls]
    return [str(url) for url in urls or [] if normalize_url(url) in allowed]
