"""The rubric that decides which events carry a structured block, and what goes in it.

One entry per kind of event that is more than prose—a birth, a death, a
marriage, a migration, an invention, a publication. Each entry is read three
times: the proposal builds its detection guidelines out of the entries, the research
builds the research focus that tells a call not to repeat what the
classification already holds, and the run log formats what was found. Keeping
the three in one table is what stops a kind from being detected under one
description and researched under another. The birth and the death carry a
fourth reader: their `description_guidance` states the goal the prose of the two
boundary events serves, and the review holds the shipped description to it.

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
# - proposal prompts (detection guidelines)
# - research prompts (class-specific research guidance)
# - Logging (formatted output)
#
# CONFIGURATION KEYS:
# - name: UPPERCASE name for prompts
# - display_name: Name for logs/UI
# - description: Brief description of classification
# - keywords: Detection keywords (documentation only)
# - detection_rules: When to apply this classification
# - fields: {field_name: description} of what classification contains
# - proposal_guidance: Multi-line detection guidelines for AI
# - research_focus: List of research focus areas (emphasize what NOT to repeat)
# - log_format: lambda cls: str for formatting log output

# What the prose of the two boundary events is for. A birth and a death are the
# only events whose own fact the slide states without help from the prose: the
# card names the parents and the household on the one, the cause and the
# resting place on the other. Their guidance was therefore written as an
# inventory of what such a description may contain and what it may not, and the
# inventory is what failed. Steve Jobs's birth card named Jandali and Schieble
# as the parents while the chips beside it named Paul and Clara Jobs as the
# adoptive ones, and the description, forbidden to carry a parent at all and
# asked for the standing conditions of the early home, spent its three
# sentences on Jandali's doctorate and on the Schieble family's objection to
# him without once saying that the child was given up. Every rule had been
# followed and the slide could not be read.
#
# What stands here now is a goal: what the reader is to come away with. Which
# fact a birth or a death turns on differs in every life, and no list written in
# advance names it, so the shape of the telling is left to the call that has the
# article in front of it. The proposal writes the skeleton toward the goal, the
# research rewrites a skeleton that missed it, and the review reads the shipped
# description against it, so the goal is stated once here and read from the
# table like everything else about the kind.
BIRTH_DESCRIPTION_GUIDANCE = (
    "DESCRIPTION GOAL: the reader comes away knowing what this life began "
    "from. Tell the beginning this life actually had, in whatever shape the case "
    "needs, within 2-4 sentences: the household and what it lived on, the parents "
    "and whoever actually raised the child, the siblings already there, the faith, "
    "the language, the money, and whatever about this birth decided what came "
    "after, such as an adoption arranged around it, a father already dead, a war, "
    "or a flight\n"
    "  * The card beside the prose holds names and labels and nothing else. It "
    "cannot say how two facts stand to each other, so where the relation is the "
    "point, the prose says it and names whoever it must name to say it: that the "
    "couple who raised the child adopted him days after the birth, that the mother "
    "died in it, that the man the card names never saw the child\n"
    "  * The shape to avoid is the sentence that says the card again and stops: "
    "'Alan Turing is born in Maida Vale, London' under a card naming both parents "
    "leaves the reader with what they can already see\n"
    "  * Stay in the opening of the life: what was already true of the household, "
    "what happened around the birth, and what the birth set in motion. A move, a "
    "school, or a parent's death years later belongs to the event that carries it\n"
    "  * GOOD: 'The father served as a magistrate in the Indian Civil Service and was "
    "home on leave. The parents spent most of each year in India and left both sons "
    "in England in the care of a retired army couple.'"
)

DEATH_DESCRIPTION_GUIDANCE = (
    "DESCRIPTION GOAL: the reader comes away knowing how this life ended. "
    "Tell the road to the death and the conditions of the end, in whatever shape "
    "the case needs, within 2-4 sentences: the illness and its course, the years of "
    "decline, a prosecution, a duel, an accident, how the person was living by then, "
    "and who was there\n"
    "  * The card holds the cause in a few words and the resting place as a name. "
    "Where either needs a sentence to be understood, the prose carries it: what the "
    "conviction had cost him, who found him, why an inquest ruled as it did\n"
    "  * The shape to avoid is the sentence that says the card again and stops: "
    "'Turing dies from cyanide poisoning. An inquest rules his death a suicide.' "
    "under a card holding both facts leaves the reader with what they can already "
    "see\n"
    "  * The death is the last moment of the story. The funeral, the reaction, and "
    "the retrospect of the career belong to the conclusion\n"
    "  * GOOD: 'A 1952 conviction for gross indecency had cost him his security "
    "clearance, and the court had ordered a year of hormone treatment. He lived alone "
    "in Wilmslow. His housekeeper found him dead in bed.'"
)

# The research is told in its base prompt to rewrite a description that falls short
# of the contract. A boundary skeleton is written before the article is in front
# of the call, so its class block says how far the rewrite reaches: as far as the
# goal needs, and no further where the skeleton already gets there.
BOUNDARY_REWRITE_NOTE = (
    "  * The skeleton was proposed before this article was in front of you. Where it "
    "reaches the goal above, keep its facts and fill in what it left out; where it "
    "only says what the slide already shows, replace it and write the goal from the "
    "article, within 2-4 sentences"
)


def _as_bullet(guidance: str) -> str:
    """A guidance block as one bullet of the proposal prompt, its examples nested under it."""
    return "  * " + guidance.replace("\n", "\n  ")


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
        "proposal_guidance": (
            "- BIRTH: The SUBJECT's own birth — never the birth of a child, sibling, or anyone else\n"
            "  * Exactly one event per life story carries this classification\n"
            "  * father: Full name of the father, omit when undocumented\n"
            "  * mother: Full name of the mother, with maiden name when documented, omit when undocumented\n"
            "  * The two fields name the parents the sources give for the birth itself. Where "
            "others raised the child (adopted, fostered, given to relatives, orphaned), those "
            "people belong in the description and among the event's involved people, and the "
            "description says how the two stand to each other\n"
            "  * Optional: birth_name (only when it differs from the name the person is known by), "
            "characterization (the household born into, 1-4 words)\n"
            + _as_bullet(BIRTH_DESCRIPTION_GUIDANCE)
            + "\n"
        ),
        "description_guidance": BIRTH_DESCRIPTION_GUIDANCE,
        "research_focus": [
            BIRTH_DESCRIPTION_GUIDANCE,
            "  * The card carries the parents' names and the slide the city, so a sentence whose "
            "whole content is those names adds nothing: 'He was born to Christian Bohr, a "
            "physiologist, and Ellen Adler Bohr' tells the reader what the card tells them. Name a "
            "parent wherever the sentence needs the name to say what the card cannot say: what they "
            "did, that they gave the child up, that they took him in, that one of them was already dead",
            BOUNDARY_REWRITE_NOTE,
            "LOCATIONS: Place of birth (city level)",
            "INVOLVED_PEOPLE: Whoever the beginning of this life turns on: siblings, the couple "
            "who raised the child, a guardian. The parents in the classification are not listed again",
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
        "proposal_guidance": (
            "- DEATH: The SUBJECT's own death — never the death of a parent, spouse, child, or anyone else\n"
            "  * Exactly one event per life story carries this classification\n"
            "  * cause: The cause of death as a noun phrase of 1-6 words ('heart failure', "
            "'cyanide poisoning', 'gunshot wound from a duel') — no pronouns, no 'complications "
            "related to'\n"
            "  * OMIT cause when the sources do not state one — never guess, and never infer it from old age\n"
            "  * When the cause is contested, give the documented one and say so in characterization "
            "('ruled a suicide', 'cause disputed')\n"
            "  * Optional: characterization (1-4 words), place_of_rest (burial or resting place)\n"
            + _as_bullet(DEATH_DESCRIPTION_GUIDANCE)
            + "\n"
        ),
        "description_guidance": DEATH_DESCRIPTION_GUIDANCE,
        "research_focus": [
            DEATH_DESCRIPTION_GUIDANCE,
            "  * The card states the cause in a few words and names the resting place, so the prose "
            "says what those few words leave out rather than spelling them again",
            BOUNDARY_REWRITE_NOTE,
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
        "proposal_guidance": (
            "- MARRIAGE_PARTNERSHIP: Event title/description contains 'married', 'marriage', 'wed', 'wedding', 'spouse'\n"
            "  * subtype: 'marriage' (legal/ceremonial) OR 'partnership' (domestic/romantic)\n"
            "  * partner: Full name of spouse/partner\n"
            "  * Optional: duration (e.g., 'until death', '17 years'), children (integer), characterization (1-4 words)\n"
            "  * characterization describes the bond itself (e.g., 'devoted partnership', 'political alliance', 'strained'),\n"
            "    never a purely professional label such as 'close collaboration' or 'work partnership'\n"
        ),
        "research_focus": [
            "INVOLVED_PEOPLE: Include the partner's name (already in classification, but also list here)",
            "LOCATIONS: Wedding venue city (keep to city level, e.g., 'London' not full venue name)",
            "DESCRIPTION: Name the partner in the sentence and say who they were, what they did, "
            "how the two had met, and where the marriage took place; the prose is read without the card",
            "  * The card holds the duration and the number of children; the prose does not restate them",
            "  * DO NOT annotate the partner's name (use INVOLVED_PEOPLE field instead)",
            "  * GOOD: 'In 1930 she married Vincent Foster Hopper, who taught English at New York "
            "University. She had just finished her master's degree in mathematics at Yale.'",
            "  * BAD (leans on the card): 'In 1930, she married a New York University professor.'",
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
        "proposal_guidance": (
            "- MIGRATION: Permanent or significant relocation to different country/region\n"
            "  * Words like: 'emigrated', 'immigrated', 'fled', 'moved to', 'settled in', 'exile', 'refuge', 'relocated'\n"
            "  * Includes: emigration, immigration, exile, refugee movement, major relocations\n"
            "  * NOT temporary: conferences, visits, tours, business trips, brief study abroad\n"
            "  * from_location: Origin country/region\n"
            "  * to_location: Destination country/region\n"
            "  * Optional: characterization (e.g., 'political exile', 'career opportunity', 'refugee flight')\n"
        ),
        "research_focus": [
            "LOCATIONS: Provide TWO locations (departure and arrival cities)",
            "  * First location: Origin city/region (mark as primary=false)",
            "  * Second location: Destination city/region (mark as primary=true)",
            "  * Use city-level names (e.g., 'Berlin, Germany' → 'New York, USA')",
            "  * name_historic: City name at time of migration",
            "  * name_modern: Modern name for geocoding",
            "DESCRIPTION: Name where the person left and where they arrived, and say why they went, "
            "how they traveled, and who went with them; the prose is read without the card",
            "  * The card holds the characterization of the move; the prose does not restate it",
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
        "proposal_guidance": (
            "- INVENTION: Creating/building/patenting tangible invention, device, machine, algorithm\n"
            "  * Words like: 'invented', 'patented', 'built', 'designed', 'created' + technical artifact\n"
            "  * MUST be novel creation with clear technical output (not just ideas/theories)\n"
            "  * title: Name of invention\n"
            "  * description: What it is and how it works (1 sentence, 15-25 words)\n"
            "  * Optional: impact (1 sentence, 12-20 words)\n"
        ),
        "research_focus": [
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
        "proposal_guidance": (
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
        "research_focus": [
            "DESCRIPTION: Name the work in the sentence and say what it is about, how it came to be "
            "written, and how it was received at the time; the prose is read without the card",
            "  * The card holds the publication type and the publisher; the prose does not restate them",
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


def boundary_description_prompt() -> str:
    """The birth and death description definitions as one block for the review.

    The proposal and the research read them through the table; the review reads the whole
    dataset at once and needs both definitions in one place, named by kind.
    """
    return "\n".join(
        f"{config['name']} {config['description_guidance']}"
        for config in EVENT_CLASS_CONFIG.values()
        if config.get("description_guidance")
    )
