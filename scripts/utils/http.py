"""Types and address handling shared by the scripts that call HTTP APIs."""

from typing import Dict, Optional, Union
from urllib.parse import urlsplit, urlunsplit

QueryParams = Dict[str, Union[str, int]]
"""Query string parameters for a `requests` call.

Written out rather than inferred. A literal that mixes the strings and the
numbers a query string carries — `"format": "json"` beside `"srlimit": 20` —
infers as `dict[str, object]`, and requests, typed inline since 2.34, rejects
that: `object` is not one of the value types it will encode. Annotating the
dict is what tells mypy the union is the type, not the join.
"""


COMMONS_FILE_HOST = "upload.wikimedia.org"
"""The host the corpus stores Wikimedia file addresses under.

Commons serves the same paths from more than one name — the API began handing
back `thumb.wikimedia.org` for the thumbnails it renders — and every consumer
of a stored URL is written against this one. `getThumbnailUrl` in
`src/utils/story/images.js` only rewrites widths for it, the portrait
generator's size lookup only recognizes it, and the privacy notice names it as
one of the three hosts a reader's browser contacts. An alias in the data
therefore costs the reader the width the slide asked for and makes the notice
untrue, while pointing at the same bytes.
"""

_COMMONS_FILE_HOST_ALIASES = frozenset({COMMONS_FILE_HOST, "thumb.wikimedia.org"})


def canonical_commons_url(url: Optional[str]) -> Optional[str]:
    """A Commons file address under the canonical host, without the analytics.

    The API answers with `?utm_source=commons.wikimedia.org&...` appended to
    every URL. It is tracking, not identity: it makes one photograph look like
    two when a stored URL is compared with a fresh one, and the interface's
    thumbnail rewriter — which appends a size to the path — builds a broken
    address out of it when the query string sits between the two.
    """
    if not url:
        return url
    parsed = urlsplit(url)
    if parsed.netloc.lower() not in _COMMONS_FILE_HOST_ALIASES:
        return url
    return urlunsplit(
        (parsed.scheme, COMMONS_FILE_HOST, parsed.path, "", parsed.fragment)
    )
