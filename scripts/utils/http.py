"""Types shared by the scripts that call HTTP APIs."""

from typing import Dict, Union

QueryParams = Dict[str, Union[str, int]]
"""Query string parameters for a `requests` call.

Written out rather than inferred. A literal that mixes the strings and the
numbers a query string carries — `"format": "json"` beside `"srlimit": 20` —
infers as `dict[str, object]`, and requests, typed inline since 2.34, rejects
that: `object` is not one of the value types it will encode. Annotating the
dict is what tells mypy the union is the type, not the join.
"""
