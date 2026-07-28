"""Tooling that documents the story generation pipeline as an interactive chart.

The package is deliberately read-only with respect to the pipeline: it parses
`scripts/*.py` statically, optionally replays a recorded run, and renders a
standalone HTML page. Nothing here is imported by the generators themselves.
"""
