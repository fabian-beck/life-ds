"""
AI prompts for person data review system.

These prompts guide the AI to review and improve generated biographical data
with focus on readability, accuracy, and UI optimization.
"""

import json
from typing import Dict, Any, List, Set

# UI Context documentation embedded in prompts
UI_CONTEXT = """
DISPLAY CONSTRAINTS:
- Event titles: Displayed as large headings (h2, 1.35-1.85rem)
  → Should be concise, ~5-10 words max, ~80-100 characters
- Event descriptions: Constrained to 25vh with fade effect
  → ~200-400 words visible on mobile, ~400-800 on desktop
  → Warn if >1000 words (excessive scrolling)
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
   - Can add missing annotations to resolve orphaned [[term]] references
   - Can add missing people to existing events' "involved_people" arrays (if empty or incomplete)
   - Can add missing location data to existing events (if null/empty)
   - CANNOT add new events or new network connections
4. Moderate text reduction: Target 500-800 words for descriptions, suggest specific cuts
5. All changes must be traceable to Wikipedia cache or logical inference
6. Preserve the narrative voice and storytelling style
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
1. **Readability & Conciseness**: Tighten prose, remove redundancies, optimize for mobile viewing
2. **Factual Accuracy**: Cross-reference all claims against the Wikipedia sources provided
3. **Completeness**: Fill in missing information from Wikipedia sources (dates, locations, people, annotations)
4. **Storytelling Quality**: Ensure narrative flow, proper pacing, emotional resonance
5. **UI Optimization**: Respect display constraints (event titles, description length, annotations)
6. **Metadata Quality**: Verify and complete dates, locations, involved people, icons
7. **Annotation Cleanup**: Resolve orphaned [[term]] references - remove trivial ones, add definitions for important ones
8. **Cross-File Consistency**: Ensure people mentioned in events appear in network and vice versa; avoid redundancy between event descriptions and relationship descriptions

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

**Event Descriptions**:
- Target 500-800 words for readability on mobile
- First 200-300 words are most visible (before scroll)
- Remove redundancies between title and opening sentence
- Use active voice and vivid language
- Break into paragraphs for readability
- **CRITICAL - Plain text only**: Descriptions must be plain text without markdown syntax (no **bold**, *italic*, `code`, ## headings, etc.)

**Annotations**:
- Use [[term]] or [[term|display text]] format
- Provide helpful, concise explanations (not Wikipedia dumps)
- Only annotate terms on first occurrence
- Include Wikipedia URL if helpful for further reading
- Focus on technical terms, foreign words, historical concepts
- **CRITICAL - No redundancy**: Annotation explanations must NOT repeat information already in the event description. Provide additional context or clarification only.
- **IMPORTANT - Orphaned Annotations**: If you find [[term]] markup in description but no annotation definition:
  * For trivial info (city names, common terms): Remove the [[]] markup entirely
  * For important concepts: Add a proper annotation definition with explanation
- **IMPORTANT - Missing Annotations**: Look for technical terms, historical events, or concepts that should be annotated but aren't

**Chapter Structure**:
- Headlines: 2-5 words, evocative and story-like (NOT lists)
  - GOOD: "Breaking the Code", "The Thinking Machine", "Persecution"
  - BAD: "Wartime Work and Codebreaking", "Early Life, Education, and Career"
- Events should fit thematically within their chapter

**Metadata**:
- **Involved People**: Add missing people mentioned in event description who played a key role
- **Locations**: Fill in missing location data if the event clearly happened somewhere specific
- **Dates**: Add more precise dates if available in Wikipedia (e.g., upgrade "1936" to "1936-11-28")
- **Icons**: Verify event_type_icon matches event semantics, change if more appropriate icon exists
- Ensure historical accuracy for all metadata

**Source Verification**:
- All factual claims must be verifiable in the Wikipedia sources
- If you can't verify a claim, flag it as uncertain (low confidence)
- Cite which Wikipedia article supports the claim

**Network-Specific Guidelines**:
- **Relationship Descriptions**: 1-2 sentences max, informative but brief (shown in tooltips)
  - GOOD: "PhD supervisor who introduced Turing to the Entscheidungsproblem and remained a lifelong collaborator."
  - BAD: "Newman was Turing's PhD supervisor at Cambridge University and supervised Turing's PhD thesis in mathematical logic and also worked with him later on computer design projects."
- **Cross-References**: People with strong/moderate network connections should appear in life events where relevant
- **Balance**: Check for both parents, mix of professional and personal relationships, gender balance
- **No Redundancy**: Relationship descriptions should complement, not repeat, information in event descriptions

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
Rate each change's confidence 1-5. Ensure consistency between the two perspectives - they should complement each other without redundancy.
Focus on changes that will noticeably improve the reader's experience on mobile devices.
"""

    return prompt


def get_style_review_prompt(
    style_data: Dict[str, Any], events_data: Dict[str, Any]
) -> str:
    """
    Generate prompt for visual style review.

    Args:
        style_data: Current style entry from person_styles.json
        events_data: Life events data for context about person

    Returns:
        Formatted prompt string
    """
    person = events_data.get("person", {})
    person_name = person.get("name", "Unknown")
    birth_year = (person.get("birth_date") or "")[:4]
    death_year = (person.get("death_date") or "")[:4]
    primary_roles = person.get("primary_roles") or []

    prompt = f"""You are reviewing visual identity/styling for {person_name} ({birth_year}-{death_year}).

PRIMARY ROLES: {', '.join(primary_roles)}

{CRITICAL_CONSTRAINTS}

{CONFIDENCE_SCALE}

TASK: Review the visual style and propose improvements focused on:
1. **Color appropriateness**: Do colors suit the person's era and character?
2. **Contrast**: Is there sufficient contrast between background and primary/secondary colors?
3. **Pattern quality**: Is the SVG pattern culturally relevant and visually distinctive?
4. **Font selection**: Are fonts appropriate to the person's era and readable?

CURRENT STYLE DATA:
```json
{json.dumps(style_data, indent=2)}
```

REVIEW GUIDELINES:

**Color Palette**:
- Primary and secondary colors should be harmonious
- Background should provide good contrast for readability
- Consider era-appropriate palettes (muted for historical figures, vibrant for modern)
- Check accessibility (WCAG contrast ratios)

**SVG Pattern**:
- Must use ONLY pure black (#000000) and white (#FFFFFF)
- Must include at least one white element
- Should be 160x160 tileable pattern
- Should reflect person's era, culture, or field
- Strong strokes preferred over thin lines
- Examples: geometric patterns for mathematicians, organic for artists, mechanical for engineers

**Fonts**:
- heading_font: Should be distinctive and era-appropriate
- body_font: Must be highly readable
- Both must be available on Google Fonts
- Consider: Serif for classical/historical, sans-serif for modern/technical

**Cultural Sensitivity**:
- Patterns for non-Western figures should avoid stereotypes
- Colors should respect cultural associations
- Fonts should match linguistic/regional context when possible

PERSON CONTEXT:
{(person.get("summary") or "")[:500]}...

Please provide specific, actionable improvements. Only propose changes if there are clear issues or obvious enhancements.
Most generated styles are already good - focus on genuine problems, not minor tweaks.
"""

    return prompt


def get_examples_of_good_content() -> str:
    """Return examples of well-written event content for reference."""
    return """
EXAMPLES OF WELL-WRITTEN CONTENT:

**Good Event Title**:
"Publishes On Computable Numbers"
- Concise, active voice, clear subject

**Good Event Description** (opening):
"Turing's 1936 paper introduced the concept of a universal computing machine—an abstract device that could perform any calculation. The Turing machine, as it became known, laid the theoretical foundation for modern computers. This work answered Hilbert's [[Entscheidungsproblem|decision problem]], proving that no algorithm could solve all mathematical questions."

- Starts with impact
- Uses active voice
- Includes annotation for technical term
- Flows naturally

**Good Chapter Headline**:
"Breaking the Code"
- Evocative, suggests action/achievement
- Short and memorable
- Not a list or summary

**Good Relationship Description**:
"PhD supervisor who introduced Turing to the Entscheidungsproblem and remained a lifelong collaborator on computer design."
- Concise (one sentence)
- Captures relationship essence
- Mentions key contribution
"""
