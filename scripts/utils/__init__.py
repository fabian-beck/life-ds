"""Shared helpers for the generation scripts.

Marks this directory as a package. Without it, mypy can reach the modules here
as both `wikipedia_cache` and `utils.wikipedia_cache` and refuses to guess which
is intended; the code only ever imports them as `utils.*`.
"""
