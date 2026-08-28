# Fact-Checking Evaluation

An internal measurement tool: how much of what a generated person story asserts is actually supported by the sources it was generated from. Nothing here is deployed, nothing here writes to `data/`, and no stage is part of either generation pipeline. It runs when someone wants a number for the corpus, not on every build.

The round has four stages. The first two call a model, the third is a page an evaluator works in, and the fourth is arithmetic.

```powershell
python -m evaluation.factcheck.extract_facts alan_turing ada_lovelace
python -m evaluation.factcheck.gather_evidence --sample 40 --seed 7 --name round-1
# open evaluation/out/rounds/round-1.html, judge, download the results
python -m evaluation.factcheck.merge_results --bundle evaluation/out/bundles/round-1.json
```

Everything the stages write lands under `evaluation/out/`, which is not committed: a bundle carries quoted source text and a result file carries one person's judgments, and both belong to a round rather than to the repository.

## 1. Extract the claims

`extract_facts.py` cuts a person's dataset into units — the registry entry, the chapter frame, the conclusion, each event, each event's depth-layer prose, and the ego network — and asks the model for every assertion each unit makes. Structured fields count: a date claims when, a location claims where, an `involved_people` entry claims who was there, an annotation claims what a term means, an image caption claims what a picture shows, and a relationship claims how two people were connected. One event's prose alone yields twenty to forty claims, and a whole story around seven hundred.

Claims are written to stand alone, with pronouns resolved and the date carried in, because an evaluator sees one claim at a time and a bundle mixes people. Each claim records the field it came from and the exact span of the dataset that carries it; that span is then looked for in the unit afterwards, so a claim whose provenance was invented is marked rather than trusted.

Links and credits are left out. An event's `sources` list, an annotation's `wikipedia_url`, and an image's `creator` each yield a claim about a link or a byline that the biographical materials cannot settle either way, and whether a listed source resolves is already checked by `scripts/validate_source_links.py`; the sources travel in the unit's context, so an evaluator still sees what the event cites. A chapter's `illustration` block is left out for a different reason: it holds the prompt its artwork was generated from, and "the illustration shows luminous planes in darkness" is true of the picture by construction.

The depth layer is extracted as its own unit per event, because it is several times the length of the slide it sits behind and is written by a different phase. The report then breaks the verdicts down by unit scope, which is what makes the two comparable.

Output: `evaluation/out/facts/<person_id>.json`, one file per person, carrying a fingerprint of the dataset it was extracted from.

## 2. Research the evidence

`gather_evidence.py` draws a reproducible sample and searches for what the materials say about each sampled claim.

The sample is stratified by person, so people are represented in proportion to how many claims their story makes, and it is seeded, so the same `--sample` and `--seed` always draw the same facts. Pass `--checkable-only` to exclude the claims stage one marked as interpretation.

The materials searched are the ones the generation pipeline read: the Wikipedia cache in `data/people/<person_id>/_cache/` — the main article, the lead summary, the German article, the related articles, the Deutsche Biographie record, and the Commons image descriptions. Checking a story against material it never saw would confuse two different failures, and only one of them is the pipeline's. The cache is not committed; when it is missing, the stage says so and names the command that rebuilds it:

```powershell
python scripts/cache_wikipedia_materials.py "Alan Turing" --id alan_turing
```

For each fact the materials are chunked into paragraphs and ranked against the claim, and the best of them, up to `--max-excerpts` and `--budget` characters, are sent with a request for verbatim quotes that support or contradict it. Every quote that comes back is then looked for in the source text, with punctuation folded so that a straightened apostrophe still matches. A quote that is in no material is kept and flagged, never dropped: a fabricated quote is a result of the evaluation. A quote filed under the wrong material but found in another is credited to the one it is really in.

Output: one bundle, `evaluation/out/bundles/<name>.json`, holding the sampled facts, their evidence with each quote in context, the material index, and a deep link to the slide each claim appears on.

## 3. Judge the claims

Stage two also writes `evaluation/out/rounds/<name>.html`: the evaluator page with the round inside it. Open that file — double-click it, or send it to whoever is judging — type your initials, and judge. There is no server to run, no second file to keep beside it, and the page makes no network request at any point.

`app/index.html` is the same page unpackaged, for the two other ways in: drop a bundle onto it, or serve the folder and pass `?bundle=../out/bundles/round-1.json`. Repackage an existing bundle with `python -m evaluation.factcheck.package_round evaluation/out/bundles/round-1.json`.

Each evaluator sees the facts in their own order, derived from their initials and the bundle id, so that fatigue and anchoring do not fall on the same claims for everyone. Judgments are saved to the browser's local storage as they are made and survive a reload, from `file://` as much as from a served page; **Download results** writes the result file the merge reads. Nothing leaves the browser until then.

The verdicts:

| Verdict | When |
| --- | --- |
| Supported | The materials establish the whole claim. |
| Partly supported | The core holds, but a detail is off, overstated, or unconfirmed. |
| Unsupported | Nothing in the materials establishes it. Not necessarily false. |
| Contradicted | The materials state something incompatible. |
| Not a factual claim | Interpretation or framing, so there is nothing to verify. |
| Misextracted | The story does not assert this. Stage one got it wrong. |
| Cannot decide | The materials are ambiguous, or the claim is. |

The last two matter as much as the first four. They separate a defect in the story from a defect in the evaluation of it, so a round can report that a story is sound and that its own extraction was not.

Each verdict is followed by how good the evidence was — whether the quotes settle the claim, help, miss the point, or were never offered — which measures stage two independently of the story. A verdict that says something is wrong also asks how far it would mislead a reader, and every judgment can carry a confidence and a note.

Keys: `1`–`7` for the verdict, `Q W E R` for the evidence rating, `N` and `P` to move, `C` to show a quote in context, `O` for the overview.

## 4. Merge and report

Collect the downloaded result files in `evaluation/out/results/`, which is where the script looks when no paths are given. `merge_results.py` joins them on the fact id, resolves one verdict per fact by majority — a tie is reported as contested rather than broken — and writes a self-contained HTML report with the merged data beside it.

The report gives the verdict distribution overall and per person, per part of the story, and per kind of claim; what the evidence search delivered, including how many of its quotes were really in the sources; how the search's own verdict lines up against the evaluators'; the agreement between evaluators; every claim the round found fault with, and every claim in the round.

Agreement is reported twice. Percent agreement says how often two evaluators picked the same verdict, which flatters a round in which one verdict dominates. Krippendorff's α discounts the agreement chance alone would produce and tolerates the facts that only one evaluator reached; a second α asks only whether they agreed that something was wrong, which is the number to read before trusting the problem count.

Result files that name a different bundle are refused. The same fact id under a different extraction is a different claim about different evidence, and averaging the two would produce a number about nothing.

## Reading a round honestly

- **A sample is a sample.** Forty facts out of seven hundred bound the error rate loosely. Widen the sample before drawing a conclusion about a person, and widen it much further before drawing one about the corpus.
- **Unsupported is not false.** It says the cached materials do not establish the claim. A pipeline that went beyond its sources and a source that is thin about a year look identical from here; the evaluator's note is where that distinction gets recorded.
- **The evidence search can fail on its own.** A claim marked unsupported after a search that returned nothing may still be in the article, three paragraphs from anything the ranking thought relevant. That is what the evidence rating is for, and a round in which the quotes often miss the point is measuring stage two, not the stories.
- **One evaluator is not agreement.** With a single result file the report gives no α, and its verdicts are one reader's.

## Files

| Path | What it is |
| --- | --- |
| `factcheck/extract_facts.py` | Stage one: claims per person. |
| `factcheck/gather_evidence.py` | Stage two: sample, search, verify, bundle. |
| `factcheck/merge_results.py` | Stage four: merge, measure, report. |
| `factcheck/units.py` | How a dataset is cut into extraction units. |
| `factcheck/materials.py` | The cached sources, as documents to quote. |
| `factcheck/evidence.py` | Retrieval and quote verification. |
| `factcheck/sampling.py` | Seeded, stratified sampling. |
| `factcheck/agreement.py` | Majority verdicts, percent agreement, Krippendorff's α. |
| `factcheck/package_round.py` | Bundle plus page as one file to open from disk. |
| `factcheck/report.py` | The HTML report. |
| `factcheck/prompts.py` | The two prompts, kept apart so a change to them is visible. |
| `app/index.html` | The evaluator page. |
| `tests/test_factcheck.py` | The deterministic parts, in the repository test suite. |

The verdict vocabulary lives in `factcheck/models.py` and again in the page; a test holds the two to the same list, because a rename on one side would split a category in every report without failing anything.
