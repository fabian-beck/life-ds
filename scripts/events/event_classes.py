"""The rubric that decides which events carry a structured block, and what goes in it.

One entry per kind of event that is more than prose—a birth, a death, a
marriage, a migration, an invention, a publication. Each entry is read three
times: Phase 1 builds its detection guidelines out of the entries, Phase 2
builds the research focus that tells a call not to repeat what the
classification already holds, and the run log formats what was found. Keeping
the three in one table is what stops a kind from being detected under one
description and researched under another.

The models these entries describe live in `events/schemas.py`; nothing here
imports them, because the table is read as data.
"""

from typing import Any, Dict

# HOW TO ADD A NEW CLASSIFICATION:
# 1. Create a Pydantic model in events/schemas.py (e.g., AwardClassification)
# 2. Add it to the EventClassification Union there
# 3. Add a configuration entry below
#
# The system automatically handles:
# - Phase 1 prompts (detection guidelines)
# - Phase 2 prompts (class-specific research guidance)
# - Logging (formatted output)
#
# CONFIGURATION KEYS:
# - name: UPPERCASE name for prompts
# - display_name: Name for logs/UI
# - description: Brief description of classification
# - keywords: Detection keywords (documentation only)
# - detection_rules: When to apply this classification
# - fields: {field_name: description} of what classification contains
# - phase1_guidance: Multi-line detection guidelines for AI
# - phase2_focus: List of research focus areas (emphasize what NOT to repeat)
# - log_format: lambda cls: str for formatting log output

EVENT_CLASS_CONFIG: Dict[str, Dict[str, Any]] = {
    "birth": {
        "name": "BIRTH",
        "display_name": "BIRTH",
        "description": "The subject's own birth — the event that opens the story",
        "keywords": ["born", "birth", "birthplace"],
        "detection_rules": [
            "The event describes the SUBJECT being born (not the birth of a child, sibling, or anyone else)",
            "Usually the first event, dated on the subject's birth date, with age 0",
        ],
        "fields": {
            "father": "Full name of the father, if documented",
            "mother": "Full name of the mother, with maiden name when documented",
            "birth_name": "Optional: full name given at birth, only when it differs from the known name",
            "characterization": "Optional: the household born into, e.g. 'academic family', 'farming household' (1-4 words)",
        },
        "phase1_guidance": (
            "- BIRTH: The SUBJECT's own birth — never the birth of a child, sibling, or anyone else\n"
            "  * Exactly one event per life story carries this classification\n"
            "  * father: Full name of the father, omit when undocumented\n"
            "  * mother: Full name of the mother, with maiden name when documented, omit when undocumented\n"
            "  * Optional: birth_name (only when it differs from the name the person is known by), "
            "characterization (the household born into, 1-4 words)\n"
        ),
        "phase2_focus": [
            "DESCRIPTION: Focus on the circumstances — the household, the city, what the family did",
            "  * DO NOT repeat the parents' names or the birth name (classification has these)",
            "  * DO NOT annotate the parents' names (use INVOLVED_PEOPLE field instead)",
            "  * Good: 'The household was an intellectually active one, with regular gatherings of "
            "university colleagues.'",
            "  * Bad: 'He was born to Christian Bohr, a physiologist, and Ellen Adler Bohr...'",
            "LOCATIONS: Place of birth (city level)",
            "INVOLVED_PEOPLE: The parents (already in the classification, but also list here) and siblings",
            "ANNOTATIONS: Never annotate person names (including the parents)",
        ],
        "log_format": lambda cls: (
            "BIRTH ("
            + (
                " & ".join(name for name in (cls.father, cls.mother) if name)
                or "parents unknown"
            )
            + ")"
        ),
    },
    "death": {
        "name": "DEATH",
        "display_name": "DEATH",
        "description": "The subject's own death — the event that closes the story",
        "keywords": ["died", "death", "killed", "executed", "passed away"],
        "detection_rules": [
            "The event describes the SUBJECT dying (not the death of a parent, spouse, child, or anyone else)",
            "Usually the last event, dated on or near the subject's death date",
        ],
        "fields": {
            "cause": "Cause of death in 1-6 words, omitted when the sources do not give one",
            "characterization": "Optional: the circumstances, e.g. 'after long illness', 'sudden' (1-4 words)",
            "place_of_rest": "Optional: burial or resting place",
        },
        "phase1_guidance": (
            "- DEATH: The SUBJECT's own death — never the death of a parent, spouse, child, or anyone else\n"
            "  * Exactly one event per life story carries this classification\n"
            "  * cause: The cause of death as a noun phrase of 1-6 words ('heart failure', "
            "'cyanide poisoning', 'gunshot wound from a duel') — no pronouns, no 'complications "
            "related to'\n"
            "  * OMIT cause when the sources do not state one — never guess, and never infer it from old age\n"
            "  * When the cause is contested, give the documented one and say so in characterization "
            "('ruled a suicide', 'cause disputed')\n"
            "  * Optional: characterization (1-4 words), place_of_rest (burial or resting place)\n"
        ),
        "phase2_focus": [
            "DESCRIPTION: Focus on the final days, the setting, and who was there",
            "  * DO NOT repeat the cause of death or the resting place (classification has these)",
            "  * DO NOT add legacy analysis or career retrospectives — those belong in the conclusion",
            "  * Good: 'He spent his last afternoon at home in Carlsberg, resting after lunch.'",
            "  * Bad: 'Bohr died of heart failure in Copenhagen, closing a career that had reshaped physics.'",
            "LOCATIONS: Where the person died (city level)",
            "INVOLVED_PEOPLE: People present or closely involved at the end",
            "ANNOTATIONS: A medical term may be annotated; never annotate the person's own name",
        ],
        "log_format": lambda cls: f"DEATH ({cls.cause or 'cause undocumented'})",
    },
    "marriage_partnership": {
        "name": "MARRIAGE_PARTNERSHIP",
        "display_name": "MARRIAGE",
        "description": "Wedding, marriage ceremony, or start of documented partnership",
        "keywords": ["married", "marriage", "wed", "wedding", "spouse"],
        "detection_rules": [
            "Event title/description contains 'married', 'marriage', 'wed', 'wedding', 'spouse'",
        ],
        "fields": {
            "subtype": "marriage (legal/ceremonial) OR partnership (domestic/romantic)",
            "partner": "Full name of spouse/partner",
            "duration": "Optional: e.g., 'until death', '17 years'",
            "children": "Optional: integer count",
            "characterization": "Optional: character of the bond, e.g., 'devoted partnership', 'political alliance', 'strained' (1-4 words); not a purely professional label",
        },
        "phase1_guidance": (
            "- MARRIAGE_PARTNERSHIP: Event title/description contains 'married', 'marriage', 'wed', 'wedding', 'spouse'\n"
            "  * subtype: 'marriage' (legal/ceremonial) OR 'partnership' (domestic/romantic)\n"
            "  * partner: Full name of spouse/partner\n"
            "  * Optional: duration (e.g., 'until death', '17 years'), children (integer), characterization (1-4 words)\n"
            "  * characterization describes the bond itself (e.g., 'devoted partnership', 'political alliance', 'strained'),\n"
            "    never a purely professional label such as 'close collaboration' or 'work partnership'\n"
        ),
        "phase2_focus": [
            "INVOLVED_PEOPLE: Include the partner's name (already in classification, but also list here)",
            "LOCATIONS: Wedding venue city (keep to city level, e.g., 'London' not full venue name)",
            "DESCRIPTION: Focus on ceremony details, circumstances, social context",
            "  * DO NOT repeat partner name, duration, children count (classification has these)",
            "  * DO NOT annotate the partner's name (use INVOLVED_PEOPLE field instead)",
            "  * Example: 'The ceremony took place at a small chapel, attended by close family.'",
            "ANNOTATIONS: Never annotate person names (including partner)",
        ],
        "log_format": lambda cls: f"MARRIAGE ({cls.partner})",
    },
    "migration": {
        "name": "MIGRATION",
        "display_name": "MIGRATION",
        "description": "Permanent or significant relocation (emigration, immigration, exile, refugee movement)",
        "keywords": [
            "emigrated",
            "immigrated",
            "fled",
            "moved to",
            "settled in",
            "exile",
            "refuge",
            "relocated",
        ],
        "detection_rules": [
            "Permanent or significant relocation to different country/region",
            "Words like: 'emigrated', 'immigrated', 'fled', 'moved to', 'settled in', 'exile', 'refuge', 'relocated'",
            "Includes: emigration, immigration, exile, refugee movement, major relocations",
            "NOT temporary: conferences, visits, tours, business trips, brief study abroad",
        ],
        "fields": {
            "from_location": "Origin country/region",
            "to_location": "Destination country/region",
            "characterization": "Optional: e.g., 'political exile', 'career opportunity', 'refugee flight' (1-4 words)",
        },
        "phase1_guidance": (
            "- MIGRATION: Permanent or significant relocation to different country/region\n"
            "  * Words like: 'emigrated', 'immigrated', 'fled', 'moved to', 'settled in', 'exile', 'refuge', 'relocated'\n"
            "  * Includes: emigration, immigration, exile, refugee movement, major relocations\n"
            "  * NOT temporary: conferences, visits, tours, business trips, brief study abroad\n"
            "  * from_location: Origin country/region\n"
            "  * to_location: Destination country/region\n"
            "  * Optional: characterization (e.g., 'political exile', 'career opportunity', 'refugee flight')\n"
        ),
        "phase2_focus": [
            "LOCATIONS: Provide TWO locations (departure and arrival cities)",
            "  * First location: Origin city/region (mark as primary=false)",
            "  * Second location: Destination city/region (mark as primary=true)",
            "  * Use city-level names (e.g., 'Berlin, Germany' → 'New York, USA')",
            "  * name_historic: City name at time of migration",
            "  * name_modern: Modern name for geocoding",
            "DESCRIPTION: Focus on reasons, journey details, immediate aftermath",
            "  * DO NOT repeat from/to locations or characterization (classification has these)",
            "  * DO NOT annotate destination country (classification provides location context)",
            "  * Example: 'Fleeing political persecution, the family traveled by ship, arriving with few possessions.'",
            "INVOLVED_PEOPLE: People who traveled together or helped with migration",
        ],
        "log_format": lambda cls: f"MIGRATION ({cls.from_location} → {cls.to_location})",
    },
    "invention": {
        "name": "INVENTION",
        "display_name": "INVENTION",
        "description": "Creation of novel device, machine, algorithm, or technique",
        "keywords": ["invented", "patented", "built", "designed", "created"],
        "detection_rules": [
            "Creating/building/patenting tangible invention, device, machine, algorithm",
            "Words like: 'invented', 'patented', 'built', 'designed', 'created' + technical artifact",
            "MUST be novel creation with clear technical output (not just ideas/theories)",
        ],
        "fields": {
            "title": "Name of invention",
            "description": "What it is and how it works (1 sentence, 15-25 words)",
            "impact": "Optional: Historical/practical impact (1 sentence, 12-20 words)",
        },
        "phase1_guidance": (
            "- INVENTION: Creating/building/patenting tangible invention, device, machine, algorithm\n"
            "  * Words like: 'invented', 'patented', 'built', 'designed', 'created' + technical artifact\n"
            "  * MUST be novel creation with clear technical output (not just ideas/theories)\n"
            "  * title: Name of invention\n"
            "  * description: What it is and how it works (1 sentence, 15-25 words)\n"
            "  * Optional: impact (1 sentence, 12-20 words)\n"
        ),
        "phase2_focus": [
            "DESCRIPTION: Focus ONLY on narrative context (where, when, why, with whom)",
            "  * DO NOT repeat technical specifications or features (classification has these)",
            "  * DO NOT annotate the invention name (classification provides full technical details)",
            "  * DO NOT use technical adjectives from classification (e.g., 'mechanical', 'binary', 'relay-based')",
            "  * Good: 'In his parents' Berlin apartment, Zuse built the Z1 using scavenged materials over two years.'",
            "  * Bad: 'Zuse built the Z1, a mechanical binary calculating machine using 20,000 parts...'",
            "  * The classification provides ALL technical details - description is pure narrative context",
            "LOCATIONS: Where invention was created/built (workshop, laboratory, city)",
            "INVOLVED_PEOPLE: Collaborators, assistants, financial sponsors, advisors",
            "ANNOTATIONS: Absolutely DO NOT annotate the invention itself",
            "  * ❌ FORBIDDEN: Annotating 'Z1', 'Z3', 'S1 and S2', etc.",
            "  * The classification already explains what the invention is",
        ],
        "log_format": lambda cls: f"INVENTION ({cls.title})",
    },
    "publication": {
        "name": "PUBLICATION",
        "display_name": "PUBLICATION",
        "description": "Publishing books, papers, articles, manuscripts, theses, or essays",
        "keywords": [
            "published",
            "wrote",
            "authored",
            "paper",
            "book",
            "article",
            "thesis",
            "manuscript",
        ],
        "detection_rules": [
            "Publication of written work (book, paper, article, manuscript, thesis, essay)",
            "Words like: 'published', 'wrote', 'authored', 'released', 'paper', 'book', 'article'",
            "MUST be actual publication event (not just writing/working on it)",
        ],
        "fields": {
            "title": "Title of the work",
            "publication_type": "book, paper, article, manuscript, thesis, or essay",
            "publisher": "Optional: Publisher or journal name (e.g., 'Nature', 'Cambridge University Press')",
            "significance": "Optional: e.g., 'seminal work', 'controversial', 'bestseller' (1-4 words)",
            "impact": "Optional: What happened BECAUSE OF the work — reception, influence, consequences (1-2 sentences); NEVER what the work depicts or contains; omit when no impact is documented",
        },
        "phase1_guidance": (
            "- PUBLICATION: Publishing books, papers, articles, manuscripts, theses, or essays\n"
            "  * Words like: 'published', 'wrote', 'authored', 'released', 'paper', 'book', 'article'\n"
            "  * MUST be actual publication event (not just writing/working on it)\n"
            "  * title: Title of the work\n"
            "  * publication_type: 'book', 'paper', 'article', 'manuscript', 'thesis', or 'essay'\n"
            "  * Optional: publisher (e.g., 'Nature', 'Cambridge University Press'), significance (1-4 words)\n"
            "  * Optional: impact (1-2 sentences) — what happened BECAUSE OF the work: reception, influence, consequences, what changed\n"
            "    - It is shown to readers under the label 'Impact', so it must claim an effect, NEVER summarize what the work depicts or contains\n"
            "    - GOOD: 'The novella became one of the most analyzed works of twentieth-century fiction and shaped the modern sense of the Kafkaesque.'\n"
            "    - BAD (content, not impact): 'The novella presented a family crisis through Gregor Samsa's sudden and grotesque transformation.'\n"
            "    - No documented impact -> omit the field rather than paraphrase the plot\n"
        ),
        "phase2_focus": [
            "DESCRIPTION: Focus on publication context, reception, circumstances",
            "  * DO NOT repeat title, publication type, or publisher (classification has these)",
            "  * DO NOT annotate the work's title (classification provides this)",
            "  * DO NOT retell the work's content in detail — a sentence on what it is about is enough; the classification's impact field is reserved for reception and influence, never content",
            "  * Good: 'The paper was presented at a mathematics symposium and initially met with skepticism.'",
            "  * Bad: 'Turing published \"On Computable Numbers\", a groundbreaking paper on theoretical computation...'",
            "  * The classification provides publication details - description is narrative context only",
            "LOCATIONS: Where published, presented, or written (city level)",
            "INVOLVED_PEOPLE: Co-authors, editors, collaborators, reviewers",
            "ANNOTATIONS: DO NOT annotate the publication title (it's in classification)",
            "  * Focus on technical terms or concepts mentioned in the description",
        ],
        "log_format": lambda cls: f"PUBLICATION ({cls.title})",
    },
}
