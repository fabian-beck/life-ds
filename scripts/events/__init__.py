"""The person event pipeline, split out of `generate_person_events.py`.

Marks this directory as a package. Without it, mypy can reach the modules here
under two names and refuses to guess which is intended; the code only ever
imports them as `events.*`.
"""
