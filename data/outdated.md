# Outdated Data

Generated data is never repaired in place: when a generator or schema change leaves shipped datasets behind, the datasets are flagged here and regenerated from scratch with the current pipeline (see the no-repair rule in `AGENTS.md`). This file is maintained by hand — a session that notices outdated data adds an entry with the reason; whoever regenerates removes the entry once the fresh data is committed.

An entry names the affected data as precisely as known (a person id, a meta story id, or a corpus-wide condition), the generator change that outdated it, and what the reader loses until regeneration.

## Flagged for regeneration

- **All persons except `alan_turing`, `emmy_noether`, `franz_kafka`, `max_planck`, `otto_wagner`** — events carry no `weight` (751 of 831 corpus events, as of 2026-08-28): they predate Phase 1 weighting. The interface still derives a fallback weight, but the deep-event selection is weaker than the weighed one, and `generate_event_backgrounds.py` refuses to fill reports for unweighted datasets. Regenerate with `scripts/generate_person.py`.
- **Most persons** — events carry no `background` report where the story would offer a depth layer (only the five weighed persons above are filled): datasets predate the background-report step. Until regeneration, those stories offer no way down on the affected events; regeneration plus the pipeline's background step fills them.
