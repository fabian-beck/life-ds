"""
AI prompts for person data review system.

These prompts guide the AI to review and improve generated biographical data
with focus on readability, accuracy, and UI optimization.
"""

import json
from typing import Dict, Any, List, Set

from events.event_classes import boundary_description_prompt
from utils.prose_style import PROSE_STYLE_INSTRUCTIONS, description_contract_prompt

# UI Context documentation embedded in prompts
UI_CONTEXT = """
DISPLAY CONSTRAINTS:
- Event titles: Displayed as large headings (h2, 1.35-1.85rem)
  → Should be concise, ~5-10 words max, ~80-100 characters
- Event descriptions: Constrained to 25vh with fade effect
  → 2-4 sentences; anything longer scrolls behind the fade
- Chapter headlines: Prominent colored labels, ~2-5 words, max ~50 chars
- Person chips: Names truncated at 150px (~15-20 chars)
  → Full details shown in tooltip on click
- Sources: Collapsed by default, expandable

ANNOTATION SYSTEM:
- Format: [[term|display]] or [[term]] in description text
- Visual: Dotted underline + "?" bubble
- Interaction: Click to show popup below description
- De-duplication: Only first occurrence of each term is annotated
- Content: Brief explanation + optional Wikipedia link

PERSON HIGHLIGHTING:
- Automatic bold highlighting of names in involved_people
- Fuzzy matching (threshold 0.6) handles name variants

MOBILE OPTIMIZATION:
- Smaller fonts, vertical layout priority
- Touch targets for interactive elements
- Aggressive truncation for long text
"""


CONFIDENCE_SCALE = """
CONFIDENCE SCORING (1-5):
- 5 = Verifiable fact from Wikipedia cache, obvious improvement
- 4 = Strong inference from sources, clear benefit
- 3 = Reasonable interpretation, moderate benefit
- 2 = Uncertain inference, minor benefit
- 1 = Speculative, questionable benefit

Only propose changes you're confident about. When in doubt, leave it unchanged.
"""


CRITICAL_CONSTRAINTS = """
CRITICAL CONSTRAINTS - YOU MUST FOLLOW THESE:
1. NO structural changes: Never add/remove JSON fields or change field types
2. NO new content: Cannot add new events, new network connections, new chapters
3. EDIT & COMPLETE existing data:
   - Can modify/improve existing text strings, dates, metadata values
   - Can fill in EMPTY/NULL fields with missing information from Wikipedia
   - Can add missing annotations, both for orphaned [[term]] references and for terms a general reader would not know from the sentence
   - Can add missing people to existing events' "involved_people" arrays (if empty or incomplete)
   - Can add missing location data to existing events (if null/empty)
   - CANNOT add new events or new network connections
4. Text edits keep the facts and change the wording: a description stays at 2-4 sentences, and a rewrite never adds a claim the sources do not carry
5. All changes must be traceable to Wikipedia cache or logical inference
6. Preserve the third-person, in-the-moment telling; the prose rules below say how every sentence reads
"""


def get_combined_review_prompt(
    events_data: Dict[str, Any],
    network_data: Dict[str, Any],
    wikipedia_content: str,
    related_articles: List[Dict[str, str]],
) -> str:
    """
    Generate comprehensive prompt for combined life events and network review.

    Args:
        events_data: Current life_events.json content
        network_data: Current ego_network.json content
        wikipedia_content: Main Wikipedia article text
        related_articles: List of related Wikipedia articles

    Returns:
        Formatted prompt string
    """
    person_name = events_data.get("person", {}).get("name", "Unknown")
    num_events = len(events_data.get("events", []))
    num_chapters = len(events_data.get("chapters", []))
    num_connections = len(network_data.get("connections", [])) if network_data else 0

    # Extract involved_people from events for cross-reference
    involved_people: Set[str] = set()
    for event in events_data.get("events", []):
        people = event.get("involved_people") or []
        involved_people.update(people)

    related_articles_summary = (
        "\n".join(
            [
                f"- {article.get('title', 'Unknown')}: {article.get('summary', '')[:200]}..."
                for article in (related_articles or [])[:5]  # Show first 5 for context
            ]
        )
        if related_articles
        else "No related articles cached"
    )

    prompt = f"""You are reviewing biographical data for {person_name} - both life events and social network - that will be displayed as full-screen slides and interactive chips in a mobile app.

{UI_CONTEXT}

{CRITICAL_CONSTRAINTS}

{CONFIDENCE_SCALE}

TASK: Review BOTH the life events and ego network data below together, ensuring consistency and complementary perspectives. Propose improvements focused on:
1. **Prose**: Rewrite every sentence that breaks HOW THE PROSE READS below - a "rather than" or "not X but Y", a colon or dash carrying an aside, a closing sentence that says what the event "marked" or "reflected" - keeping its facts and dropping the construction. This is the most common change and needs no source: the fact is already there, only the wording goes
2. **Story Continuity**: Read the events in order, as the reader does, and hold each description to THE STORY SO FAR below. You are the first pass that sees the finished sequence: the research refined every description with only its own event in view, so a slide can lean on a term the story never introduced, or tell again what the slide before it told
3. **Factual Accuracy**: Cross-reference all claims against the Wikipedia sources provided
4. **Completeness**: Fill in missing information from Wikipedia sources (dates, locations, people, annotations)
5. **Storytelling Quality**: Ensure narrative flow, proper pacing, emotional resonance
6. **UI Optimization**: Respect display constraints (event titles, description length, annotations)
7. **Metadata Quality**: Verify and complete dates, locations, involved people, icons
8. **Annotation Cleanup**: Resolve orphaned [[term]] references - remove trivial ones, add definitions for important ones
9. **Cross-File Consistency**: Ensure people mentioned in events appear in network and vice versa; avoid redundancy between event descriptions and relationship descriptions

CURRENT DATA SUMMARY:
- Person: {person_name}
- Events: {num_events}
- Chapters: {num_chapters}
- Conclusion: {"Yes" if events_data.get("conclusion") else "No"}
- Network connections: {num_connections}
- People in events: {len(involved_people)}
- People in network: {num_connections}

WIKIPEDIA SOURCES AVAILABLE:
{related_articles_summary}

REVIEW GUIDELINES:

**Event Titles**:
- Must be concise (5-10 words, max 100 chars)
- Should be engaging and clear
- Avoid redundancy with description opening
- Examples of GOOD titles: "Publishes On Computable Numbers", "Breaks Enigma Code", "Flees Nazi Germany"
- Examples of BAD titles: "Alan Turing publishes his groundbreaking paper...", "The discovery of...", "Important work on..."

**Event Descriptions** — hold every description to this definition, and rewrite via `new_description` where it falls short (a later year in an event's own prose, a disputed birthplace narrated as a dispute, a street address, a restated classification):
{description_contract_prompt()}
- 2-4 sentences, each carrying a fact about the event; a description of one sentence is extended from the sources, with the people and the place named and what led to the event, and a description that has grown past four is cut, not paragraphed
- The title and the opening sentence do not say the same thing twice, but a name the title carries stays in the sentence as well, because the prose is read on its own

**The Story So Far** — every description is read after the ones before it, and the reader knows what those said and nothing else. Walk the events in order and, for every event, fill an `event_reviews` entry in order:
- `contribution`: what this slide adds to the story that the slides before it have not told, in one sentence. If you cannot name it, the slide has a problem, and the fields below say which
- `unintroduced_terms`: what the description leans on that no earlier slide has introduced and this one does not explain. A section (Hut 8), a machine, a method, an office, a work, a group. The reader who has not met the term reads a sentence about nothing. Rewrite via `new_description` so the description names the thing for what it is where the story first meets it, in a phrase, from what the sources say it was. The naming belongs in the sentence, because an annotation is opened by choice and most readers never open it; an annotation may add depth to a term the sentence has already placed, and never stands in for placing it
- `restated_facts`: what this description tells that an earlier slide already told. The reader has just read that slide. Rewrite via `new_description` so the slide carries what changed at this moment and drops the repetition, unless the one fact is the hinge the new sentence needs
- `redundant_with`: when a slide tells nothing the slides before it have not told, look for what the sources say happened at this moment and write that into `new_description`. When the sources supply nothing, set `redundant_with` to the index of the earlier event that already covers it and leave the description alone. The review cannot remove events; the run prints this so a human can decide
- A description that merely restates its own title, or places the event where the map already places it, has the same problem in miniature: its sentences must carry the facts the slide does not already show
- Example of the problem: after "Joined Bletchley Park" and "Designs the Bombe for Enigma", a slide reading "Turing leads Hut 8 at Bletchley Park. The section works on German naval Enigma messages." adds nothing the reader can use, and "Hut 8" is a name the story never explained. Rewritten, it says what Hut 8 was, what made the naval traffic harder than the traffic the bombe was designed against, and what changed when Turing took charge, all from the sources

**Birth and Death Descriptions** — the two boundary events carry the slide's facts in their `event_class`, so their prose is held to a definition of its own. Rewrite via `new_description` a birth that narrates the birth the slide already shows, or a death that restates the cause, from what the Wikipedia sources say about the household or about the road to the end:
{boundary_description_prompt()}

{PROSE_STYLE_INSTRUCTIONS}

**Annotations**:
- An annotation is a tap-to-open gloss under the slide, the reader's only way to learn what a term in the description is
- The test for a missing annotation: would an educated general reader who is not a specialist in this person's field know from the sentence what the term is and why it matters? If not, the event needs one. The standard terms of a field count ('central limit theorem', 'general relativity'): a mathematician knows them, the reader does not
- Read every description for such terms — technical and scientific concepts, inventions and machines, institutions whose role the name does not tell, movements and laws, foreign and regional terms, works named by title — and add each via `new_annotations`, with the `[[term|display text]]` marker inserted into the description via `new_description` so the term is tappable
- Never annotate a person name, the subject of the event's classification, a well-known place or period, or a common term
- Only annotate a term at its first occurrence in the story
- Provide helpful, concise explanations (1-2 sentences, not Wikipedia dumps), with a Wikipedia URL if helpful for further reading
- **CRITICAL - No redundancy**: Read every existing explanation against its description. One that says the sentence again in other words (a description reading 'Banburismus, a statistical method for reducing bombe work' with a popup reading 'a statistical cryptanalytic method that reduced the settings bombes had to test') is removed: name the term in `dropped_annotations`, and its marker is unwrapped for you. Where the term deserves more than the sentence gives, rewrite the explanation via `new_annotations` so it adds what the description lacks and repeats none of it.
- **IMPORTANT - Orphaned Annotations**: If you find [[term]] markup in description but no annotation definition:
  * For trivial info (city names, common terms): Remove the [[]] markup entirely
  * For important concepts: Add a proper annotation definition with explanation

**Chapter Structure**:
- Headlines: 2-5 words, evocative and story-like (NOT lists)
  - GOOD: "Breaking the Code", "The Thinking Machine", "Persecution"
  - BAD: "Wartime Work and Codebreaking", "Early Life, Education, and Career"
- Events should fit thematically within their chapter

**Metadata**:
- **Involved People**: Add missing people mentioned in event description who played a key role
- **Locations**: Fill in missing location data if the event clearly happened somewhere specific. Give `name_historic` as the place was called at the time and `name_modern` as it is called today and would be searched for (omit `name_modern` when the two are the same), and mark exactly one location `primary`. Do not supply coordinates — the geocoder resolves the names you give.
- **Dates**: The event's anchor date is not editable. When an event spans a period and its own description proves a later end (losses running to 1919 while the metadata ends in 1917), set `new_date_end` (YYYY, YYYY-MM, or YYYY-MM-DD); its precision is read off the value you give
- **Icons**: Verify event_type_icon matches event semantics, change if more appropriate icon exists
- Ensure historical accuracy for all metadata

**Classification Impact** (`event_class.impact` on publication and invention events):
- The field is shown to readers under the label "Impact", so it must state what happened BECAUSE OF the work — documented reception, influence, consequences, what changed — NEVER what the work depicts or contains (content belongs in the event description)
- GOOD: "The novella became one of the most analyzed works of twentieth-century fiction and shaped the modern sense of the Kafkaesque."
- BAD (content shipped as impact): "The novella presented a family crisis through Gregor Samsa's sudden and grotesque transformation."
- When an impact line only summarizes content, rewrite it via `new_impact` with reception or influence the Wikipedia sources actually document
- When the sources document no impact, set `new_impact` to an empty string to drop the line — this removal is sanctioned despite the no-field-removal constraint, because a plot summary under the label "Impact" misleads the reader

**Source Verification**:
- All factual claims must be verifiable in the Wikipedia sources
- If you can't verify a claim, flag it as uncertain (low confidence)
- Cite which Wikipedia article supports the claim

**Network-Specific Guidelines**:
- **Relationship Descriptions**: 1-2 sentences max, informative but brief (shown in tooltips)
  - GOOD: "PhD supervisor who introduced Turing to the Entscheidungsproblem and remained a lifelong collaborator."
  - BAD: "Newman was Turing's PhD supervisor at Cambridge University and supervised Turing's PhD thesis in mathematical logic and also worked with him later on computer design projects."
- **Cross-References**: People with strong/moderate network connections should appear in life events where relevant
- **Relationship Types**: `relationship_type` values come from a closed vocabulary; when proposing a new type, keep the `category/role` shape and reuse a role that already appears in the data — an invented role is skipped on apply
  - For a state or regime official the role must name the action toward the subject (`political/censor`, `political/persecutor`, `political/banned_by`, `political/patron`), never a neutral office word, and never `opponent` or `rival` for one-sided persecution
- **Balance**: Check for both parents, mix of professional and personal relationships, gender balance
- **No Redundancy**: Relationship descriptions should complement, not repeat, information in event descriptions
- **Category Summaries**: Shown as a paragraph beside the labeled person chips of that category, so the names are already on screen
  - Flag any summary that mainly enumerates names ("A was his teacher, B his colleague, C his student") and rewrite it to explain what the circle meant for the person's life and work
  - A good summary opens with the claim that holds the category together, then develops it: the decisive figures and what they changed, the shift over time, where it led. Anchor points in a place, institution, year, or work, and write it under the prose rules above
  - Length follows the evidence, not a quota. One or two sentences when the sources say little; a substantial paragraph when they support it. Do not shorten a rich, well-sourced summary for the sake of brevity, and do not pad a thin one
  - Summaries should differ in shape between categories and between people — flag templated phrasing
  - Summaries must not restate relationship descriptions verbatim, and must be plain prose without markdown

CURRENT LIFE EVENTS DATA:
```json
{json.dumps(events_data, indent=2)}
```

CURRENT EGO NETWORK DATA:
```json
{json.dumps(network_data, indent=2) if network_data else "{}"}
```

MAIN WIKIPEDIA ARTICLE:
{wikipedia_content[:5000]}...
[Full article available in context]

Please provide a comprehensive review with specific, actionable proposed changes for BOTH life events and network.
Give every event an `event_reviews` entry, in order, with its `contribution` filled in, so that no slide is judged without the slides before it in view.
Rate each change's confidence 1-5. Ensure consistency between the two perspectives - they should complement each other without redundancy.
Focus on changes that will noticeably improve the reader's experience on mobile devices.
"""

    return prompt
