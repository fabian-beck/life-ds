#!/usr/bin/env python3
"""Normalize ego-network relationship types onto the closed vocabulary.

Deterministic, no API key, idempotent. Three layers of change, applied to the
English reference files and mirrored by connection index into every
translated copy (the merge guarantees identical order):

1. **Per-entry retags** (`PER_ENTRY`): connections whose token alone cannot
   decide the target — the bare-token legacy files (`rival`, `family`,
   `colleague`, …) and the perpetrator class of issue #119, where the same
   token covers both a genuine rivalry and one-sided persecution. Entries
   here may also type a collective as an organization or group, move an
   explanatory parenthetical out of `person_name` into the translatable
   `qualifier` field, or rename the entry (German values are spelled out,
   since names in translated files are localized).
2. **Token aliases** (`TYPE_ALIASES` in `utils/relationship_vocabulary.py`)
   for everything else, including the meta-story network files.
3. **Category-summary re-keys** (`SUMMARY_REKEYS`) where a sweep moves every
   entry of a category, so its summary follows.

Translated copies whose extraction payload changes (a qualifier is new text)
get their `translation.source_fingerprint` restamped — but only when it
matched the English source before the sweep, so a translation that was
already stale stays visibly stale.
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from translate_person import compute_fingerprint, extract_ego_network_translatables
from utils.relationship_vocabulary import normalize_relationship_type

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
PEOPLE_DIR = DATA_DIR / "people"
META_STORIES_DIR = DATA_DIR / "meta_stories"

# (person_id, English person_name) -> overrides. `type` is the canonical
# relationship type; `entity` types a collective; `name`/`name_de` rename the
# entry; `qualifier`/`qualifier_de` carry the explanatory descriptor that
# used to live in a parenthetical of `person_name`.
PER_ENTRY: Dict[Tuple[str, str], Dict[str, str]] = {
    # --- issue #119: regime perpetrators lose their neutral tags ---
    ("hans_fallada", "Joseph Goebbels"): {"type": "political/censor"},
    ("hans_fallada", "Alfred Rosenberg"): {"type": "political/banned_by"},
    ("albert_einstein", "Adolf Hitler"): {"type": "political/persecutor"},
    ("david_hilbert", "Bernhard Rust"): {"type": "political/persecutor"},
    ("erich_k_stner", "Joseph Goebbels"): {"type": "political/censor"},
    ("erich_k_stner", "Gestapo (secret police, as institutional actor)"): {
        "type": "political/persecutor",
        "entity": "organization",
        "name": "Gestapo",
        "name_de": "Gestapo",
        "qualifier": "secret police",
        "qualifier_de": "Geheimpolizei",
    },
    ("erich_k_stner", "Reichsverband deutscher Schriftsteller officials"): {
        "type": "political/banned_by",
        "entity": "group",
    },
    ("erich_k_stner", "Konrad Adenauer"): {"type": "political/opponent"},
    ("e_t_a_hoffmann", "Karl Albert von Kamptz"): {"type": "political/persecutor"},
    # --- E. T. A. Hoffmann: bare legacy tokens ---
    ("e_t_a_hoffmann", "Christoph Ludwig Hoffmann"): {"type": "family/father"},
    ("e_t_a_hoffmann", "Lovisa Albertina Doerffer"): {"type": "family/mother"},
    ("e_t_a_hoffmann", "Johanna Sophie Doerffer"): {"type": "family/aunt"},
    ("e_t_a_hoffmann", "Charlotte Wilhelmine Doerffer"): {"type": "family/aunt"},
    ("e_t_a_hoffmann", "Otto Wilhelm Doerffer"): {"type": "family/uncle"},
    ("e_t_a_hoffmann", "Johann Ludwig Doerffer"): {"type": "family/uncle"},
    (
        "e_t_a_hoffmann",
        "Mischa (Maria/Marianna Thekla Michalina Rorer, née Trzcińska)",
    ): {"type": "family/spouse"},
    ("e_t_a_hoffmann", "Immanuel Kant"): {"type": "academic/teacher"},
    ("e_t_a_hoffmann", "Dora Hatt"): {"type": "social/muse"},
    ("e_t_a_hoffmann", "Julia Marc"): {"type": "social/muse"},
    ("e_t_a_hoffmann", "Novalis"): {"type": "intellectual/influence"},
    ("e_t_a_hoffmann", "Ludwig Tieck"): {"type": "intellectual/influence"},
    ("e_t_a_hoffmann", "Achim von Arnim"): {"type": "intellectual/influence"},
    ("e_t_a_hoffmann", "Clemens Brentano"): {"type": "intellectual/influence"},
    ("e_t_a_hoffmann", "Jean Paul"): {"type": "intellectual/influence"},
    ("e_t_a_hoffmann", "Wolfgang Amadeus Mozart"): {"type": "intellectual/inspiration"},
    ("e_t_a_hoffmann", "Ludwig van Beethoven"): {"type": "professional/subject"},
    ("e_t_a_hoffmann", "Joseph Seconda"): {"type": "professional/employer"},
    ("e_t_a_hoffmann", "King Frederick William III of Prussia"): {
        "type": "political/superior"
    },
    ("e_t_a_hoffmann", 'Friedrich Ludwig Jahn ("Turnvater" Jahn)'): {
        "type": "political/subject"
    },
    # --- Erich Kästner: bare legacy tokens ---
    ("erich_k_stner", "Ida Amalia Kästner (née Augustin)"): {"type": "family/mother"},
    ("erich_k_stner", "Emil Richard Kästner"): {"type": "family/father"},
    ("erich_k_stner", "Franz Augustin"): {"type": "family/uncle"},
    ("erich_k_stner", "Thomas Kästner"): {"type": "family/child"},
    ("erich_k_stner", "Emil Zimmermann"): {"type": "professional/physician"},
    ("erich_k_stner", "Neue Leipziger Zeitung editorial staff"): {
        "type": "professional/colleague",
        "entity": "group",
    },
    ("erich_k_stner", "Erich Ohser"): {"type": "artistic/illustrator"},
    (
        "erich_k_stner",
        "Editors of Berliner Tageblatt, Vossische Zeitung, and Die Weltbühne",
    ): {"type": "professional/editor", "entity": "group"},
    ("erich_k_stner", "Walter Trier"): {"type": "artistic/illustrator"},
    ("erich_k_stner", "Edith Jacobsohn (publisher)"): {
        "type": "professional/publisher",
        "name": "Edith Jacobsohn",
        "name_de": "Edith Jacobsohn",
    },
    ("erich_k_stner", "Edmund Nick"): {"type": "artistic/collaborator"},
    ("erich_k_stner", "Gerhard Lamprecht"): {"type": "artistic/collaborator"},
    ("erich_k_stner", "UFA (Universum Film AG) leadership"): {
        "type": "professional/employer",
        "entity": "group",
    },
    ("erich_k_stner", "Schaubude cabaret ensemble"): {
        "type": "artistic/collaborator",
        "entity": "group",
    },
    ("erich_k_stner", "Neue Zeitung editorial staff"): {
        "type": "professional/colleague",
        "entity": "group",
    },
    ("erich_k_stner", "Curt Linda"): {"type": "artistic/collaborator"},
    ("erich_k_stner", "Founders of Internationale Jugendbibliothek"): {
        "type": "professional/co_founder",
        "entity": "group",
    },
    ("erich_k_stner", "Die kleine Freiheit cabaret ensemble"): {
        "type": "artistic/collaborator",
        "entity": "group",
    },
    ("erich_k_stner", "PEN Center of West Germany members"): {
        "type": "professional/colleague",
        "entity": "group",
    },
    (
        "erich_k_stner",
        "International Board on Books for Young People (IBBY) founders",
    ): {"type": "professional/co_founder", "entity": "group"},
    # --- Franz Kafka: bare legacy tokens, organizations as connections ---
    ("franz_kafka", "Hermann Kafka"): {"type": "family/father"},
    ("franz_kafka", "Julie Kafka (née Löwy)"): {"type": "family/mother"},
    ("franz_kafka", 'Gabriele "Elli" Kafka'): {"type": "family/sister"},
    ("franz_kafka", 'Valerie "Valli" Kafka'): {"type": "family/sister"},
    ("franz_kafka", 'Ottilie "Ottla" Kafka'): {"type": "family/sister"},
    ("franz_kafka", "Jakob Kafka"): {"type": "family/grandparent"},
    ("franz_kafka", "Jakob Löwy"): {"type": "family/grandparent"},
    ("franz_kafka", "Karl Hermann"): {"type": "professional/business_partner"},
    ("franz_kafka", "Felice Bauer"): {"type": "social/romantic_partner"},
    ("franz_kafka", 'Margarethe "Grete" Bloch'): {"type": "social/romantic_partner"},
    ("franz_kafka", "Julie Wohryzek"): {"type": "social/fiancée"},
    (
        "franz_kafka",
        "Lese- und Redehalle der Deutschen Studenten (student club peers)",
    ): {
        "type": "social/association",
        "entity": "organization",
        "name": "Lese- und Redehalle der Deutschen Studenten",
        "name_de": "Lese- und Redehalle der Deutschen Studenten",
        "qualifier": "student club",
        "qualifier_de": "Studentenverein",
    },
    ("franz_kafka", "Assicurazioni Generali (managers and co-workers)"): {
        "type": "professional/employer",
        "entity": "organization",
        "name": "Assicurazioni Generali",
        "name_de": "Assicurazioni Generali",
        "qualifier": "insurance company",
        "qualifier_de": "Versicherungsgesellschaft",
    },
    (
        "franz_kafka",
        "Workers' Accident Insurance Institute for the Kingdom of Bohemia "
        "(supervisors and colleagues)",
    ): {
        "type": "professional/employer",
        "entity": "organization",
        "name": "Workers' Accident Insurance Institute for the Kingdom of Bohemia",
        "name_de": "Arbeiter-Unfall-Versicherungs-Anstalt für das Königreich Böhmen",
        "qualifier": "insurance institute",
        "qualifier_de": "Versicherungsanstalt",
    },
    (
        "franz_kafka",
        "Unnamed Yiddish theatre troupe (via director and actors, "
        "including Yitzchak Löwy)",
    ): {
        "type": "artistic/influence",
        "entity": "group",
        "name": "Yiddish theatre troupe",
        "name_de": "Jiddische Theatertruppe",
        "qualifier": "travelling ensemble around Yitzchak Löwy",
        "qualifier_de": "Wandertruppe um Jizchak Löwy",
    },
    # --- Grace Hopper: bare legacy tokens ---
    ("grace_hopper", "Walter Fletcher Murray"): {"type": "family/father"},
    ("grace_hopper", "Mary Campbell Van Horne"): {"type": "family/mother"},
    ("grace_hopper", "Alexander Wilson Russell"): {"type": "family/extended_family"},
    ("grace_hopper", "Vincent Foster Hopper"): {"type": "family/spouse"},
    ("grace_hopper", "Øystein Ore"): {"type": "academic/advisor"},
    ("grace_hopper", "Howard H. Aiken"): {"type": "professional/superior"},
    ("grace_hopper", "Harvard Mark II programming team"): {
        "type": "professional/collaborator",
        "entity": "group",
    },
    ("grace_hopper", "J. Presper Eckert"): {"type": "professional/employer"},
    ("grace_hopper", "John Mauchly"): {"type": "professional/employer"},
    ("grace_hopper", "Members of the CODASYL COBOL Committee"): {
        "type": "professional/collaborator",
        "entity": "group",
    },
    ("grace_hopper", "Jean E. Sammet"): {"type": "professional/colleague"},
    ("grace_hopper", "Employees in Hopper’s Navy Programming Languages Group"): {
        "type": "academic/student",
        "entity": "group",
    },
    ("grace_hopper", "Elmo R. Zumwalt Jr."): {"type": "professional/superior"},
    ("grace_hopper", "Philip Crane"): {"type": "professional/patron"},
    ("grace_hopper", "Ronald Reagan"): {"type": "professional/patron"},
    ("grace_hopper", "Barack Obama"): {"type": "professional/patron"},
    ("grace_hopper", "Rita Yavinsky"): {"type": "professional/employer"},
    (
        "grace_hopper",
        "Young engineers and computer professionals at Digital Equipment Corporation",
    ): {"type": "academic/student", "entity": "group"},
    (
        "grace_hopper",
        "Digital Equipment Corporation (DEC) industry committees and forums peers",
    ): {"type": "professional/peer", "entity": "group"},
    # --- Hedy Lamarr: bare legacy tokens ---
    ("hedy_lamarr", 'Gertrud "Trude" Kiesler (née Lichtwitz)'): {
        "type": "family/mother"
    },
    ("hedy_lamarr", "Emil Kiesler"): {"type": "family/father"},
    ("hedy_lamarr", "Friedrich (Fritz) Mandl"): {"type": "family/spouse"},
    ("hedy_lamarr", "Benito Mussolini"): {"type": "social/acquaintance"},
    ("hedy_lamarr", "Adolf Hitler"): {"type": "social/acquaintance"},
    ("hedy_lamarr", "Louis B. Mayer"): {"type": "professional/employer"},
    ("hedy_lamarr", "Barbara La Marr"): {"type": "artistic/inspiration"},
    ("hedy_lamarr", "Walter Wanger"): {"type": "artistic/collaborator"},
    ("hedy_lamarr", "Charles Boyer"): {"type": "artistic/collaborator"},
    ("hedy_lamarr", "George Antheil"): {"type": "innovation/co_inventor"},
    ("hedy_lamarr", "Clark Gable"): {"type": "artistic/collaborator"},
    ("hedy_lamarr", "Spencer Tracy"): {"type": "artistic/collaborator"},
    ("hedy_lamarr", "Judy Garland"): {"type": "artistic/collaborator"},
    ("hedy_lamarr", "Lana Turner"): {"type": "artistic/collaborator"},
    ("hedy_lamarr", "Cecil B. DeMille"): {"type": "artistic/collaborator"},
    ("hedy_lamarr", "Victor Mature"): {"type": "artistic/collaborator"},
    ("hedy_lamarr", "Jack Chertok"): {"type": "business/business_partner"},
    ("hedy_lamarr", "Eddie Rhodes"): {"type": "professional/collaborator"},
    ("hedy_lamarr", "Charles F. Kettering"): {"type": "professional/advisor"},
    ("hedy_lamarr", "Howard Sharpe"): {"type": "professional/chronicler"},
    ("hedy_lamarr", "Richard Rhodes"): {"type": "professional/biographer"},
    # --- targeted fixes elsewhere ---
    ("alan_turing", "King George VI"): {"type": "professional/patron"},
    ("georg_wilhelm_friedrich_hegel", "Napoleon Bonaparte"): {
        "type": "social/inspiration"
    },
    ("friedensreich_hundertwasser", "Ferry Radax"): {"type": "artistic/chronicler"},
    (
        "cunigunde_of_luxembourg",
        "Kaufungen Abbey community (represented by its clergy and nuns)",
    ): {
        "entity": "group",
        "name": "Kaufungen Abbey community",
        "name_de": "Klostergemeinschaft Kaufungen",
        "qualifier": "its clergy and nuns",
        "qualifier_de": "ihr Klerus und ihre Nonnen",
    },
    ("umberto_eco", "Harvard University (Charles Eliot Norton Professorship)"): {
        "entity": "organization",
        "name": "Harvard University",
        "name_de": "Harvard University",
        "qualifier": "Charles Eliot Norton Professorship",
        "qualifier_de": "Charles-Eliot-Norton-Professur",
    },
    ("umberto_eco", "St Anne’s College, Oxford"): {"entity": "organization"},
    ("zaha_hadid", "Philip Johnson and Mark Wigley (curatorial team)"): {
        "entity": "group",
        "name": "Philip Johnson and Mark Wigley",
        "name_de": "Philip Johnson und Mark Wigley",
        "qualifier": "curatorial team",
        "qualifier_de": "Kuratorenteam",
    },
    (
        "joseph_weizenbaum",
        "Massachusetts Institute of Technology (MIT) colleagues (collective)",
    ): {
        "entity": "group",
        "name": "Massachusetts Institute of Technology (MIT) colleagues",
        "name_de": "Kollegen am Massachusetts Institute of Technology (MIT)",
    },
    ("joseph_weizenbaum", "ELIZA users and early interactive‑computing community"): {
        "entity": "group"
    },
    (
        "joseph_weizenbaum",
        "Computer Professionals for Social Responsibility leadership and members",
    ): {"entity": "group"},
    ("joseph_weizenbaum", "University of Bremen computer science faculty"): {
        "entity": "group"
    },
    (
        "joseph_weizenbaum",
        "Institute of Electronic Business (Berlin) scientific council",
    ): {"entity": "group"},
    (
        "joseph_weizenbaum",
        "Weizenbaum‑Institut für die vernetzte Gesellschaft researchers",
    ): {"entity": "group"},
    (
        "edsger_w_dijkstra",
        "International Federation for Information Processing Working Group 2.1 members",
    ): {"entity": "group"},
    (
        "edsger_w_dijkstra",
        "Technische Hogeschool Eindhoven (Eindhoven University of Technology) colleagues",
    ): {"entity": "group"},
    ("edsger_w_dijkstra", "Tuesday Afternoon Club colleagues"): {"entity": "group"},
    ("edsger_w_dijkstra", "Burroughs Corporation research staff"): {"entity": "group"},
    ("edsger_w_dijkstra", "Students at the University of Texas at Austin"): {
        "entity": "group"
    },
    ("edsger_w_dijkstra", "University of Texas at Austin Computer Science faculty"): {
        "entity": "group"
    },
}

# Category summaries whose whole category moved with the sweep.
SUMMARY_REKEYS: Dict[Tuple[str, str], str] = {
    ("hans_fallada", "other"): "political",
    ("antoni_gaud", "other"): "religious",
}


def _reorder_connection(conn: Dict[str, Any]) -> Dict[str, Any]:
    """Keep the new fields next to the name so the files stay readable."""
    ordered: Dict[str, Any] = {}
    for key in ("person_name", "entity_kind", "qualifier"):
        if key in conn:
            ordered[key] = conn[key]
    for key, value in conn.items():
        if key not in ordered:
            ordered[key] = value
    return ordered


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(path: Path, data: Any) -> None:
    path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


def normalize_person(person_dir: Path, dry_run: bool) -> Tuple[int, List[str]]:
    """Normalize one person's English network and its translated copies."""
    person_id = person_dir.name
    en_path = person_dir / "ego_network.json"
    if not en_path.exists():
        return 0, []
    english = load_json(en_path)
    connections = english.get("connections") or []

    # The fingerprint the translated copies were stamped against, before any
    # change — the restamp at the end only follows a match against this.
    fingerprint_before = compute_fingerprint(extract_ego_network_translatables(english))

    changes = 0
    unknown: List[str] = []
    # index -> overrides, resolved from the English names so the translated
    # copies (localized names, identical order) can be edited by position.
    per_index: Dict[int, Dict[str, str]] = {}
    used_keys = set()
    # A rule for a renamed entry also matches its own target name, so a
    # re-run recognizes work already done instead of reporting a miss.
    renamed = {
        (pid, override["name"]): override
        for (pid, _), override in PER_ENTRY.items()
        if pid == person_id and override.get("name")
    }
    for index, conn in enumerate(connections):
        key = (person_id, conn.get("person_name", ""))
        override = PER_ENTRY.get(key) or renamed.get(key)
        if override:
            per_index[index] = override
            used_keys.add(key)

    documents: List[Tuple[Path, Dict[str, Any], bool]] = [(en_path, english, True)]
    for translated_path in sorted(person_dir.glob("*/ego_network.json")):
        if translated_path.parent.name == "_cache":
            continue
        documents.append((translated_path, load_json(translated_path), False))

    for path, document, is_english in documents:
        doc_changed = False
        doc_connections = document.get("connections") or []
        if len(doc_connections) != len(connections):
            print(
                f"  ! {path}: {len(doc_connections)} connections, "
                f"English has {len(connections)} — skipped"
            )
            continue
        for index, conn in enumerate(doc_connections):
            override = per_index.get(index, {})
            target_type = override.get("type")
            if target_type is None:
                target_type, known = normalize_relationship_type(
                    conn.get("relationship_type", "")
                )
                if not known:
                    if is_english:
                        unknown.append(
                            f"{person_id}: {conn.get('person_name')} — "
                            f"{conn.get('relationship_type')}"
                        )
                    target_type = None
            if target_type and target_type != conn.get("relationship_type"):
                conn["relationship_type"] = target_type
                doc_changed = True
            entity = override.get("entity")
            if entity and conn.get("entity_kind") != entity:
                conn["entity_kind"] = entity
                doc_changed = True
            name_key = "name" if is_english else "name_de"
            if override.get(name_key) and conn.get("person_name") != override[name_key]:
                conn["person_name"] = override[name_key]
                doc_changed = True
            qualifier_key = "qualifier" if is_english else "qualifier_de"
            if (
                override.get(qualifier_key)
                and conn.get("qualifier") != override[qualifier_key]
            ):
                conn["qualifier"] = override[qualifier_key]
                doc_changed = True
            reordered = _reorder_connection(conn)
            if list(reordered.keys()) != list(conn.keys()):
                doc_connections[index] = reordered
                doc_changed = True
        for summary in document.get("category_summaries") or []:
            rekey = SUMMARY_REKEYS.get((person_id, summary.get("relationship_type")))
            if rekey and summary.get("relationship_type") != rekey:
                summary["relationship_type"] = rekey
                doc_changed = True
        if doc_changed:
            changes += 1
            if not dry_run:
                if not is_english:
                    _restamp_fingerprint(document, english, fingerprint_before)
                save_json(path, document)
            print(f"  {'would update' if dry_run else 'updated'} {path}")

    for key, override in PER_ENTRY.items():
        if key[0] != person_id or key in used_keys:
            continue
        if override.get("name") and (person_id, override["name"]) in used_keys:
            continue
        print(f"  ! per-entry rule matched nothing: {key[1]!r}")
    return changes, unknown


def _restamp_fingerprint(
    document: Dict[str, Any],
    english_after: Dict[str, Any],
    fingerprint_before: str,
) -> None:
    """Follow the English payload with the stored fingerprint, when it was
    current before the sweep. A stale translation stays visibly stale."""
    block = document.get("translation")
    if not isinstance(block, dict):
        return
    if block.get("source_fingerprint") != fingerprint_before:
        return
    block["source_fingerprint"] = compute_fingerprint(
        extract_ego_network_translatables(english_after)
    )


def normalize_meta_story(path: Path, dry_run: bool) -> Tuple[int, List[str]]:
    """Alias-normalize the relationship types in one meta story's network."""
    document = load_json(path)
    network = document.get("social_network") or {}
    links = network.get("links") or []
    changed = False
    unknown: List[str] = []

    def _normalize(holder: Dict[str, Any]) -> None:
        nonlocal changed
        value = holder.get("relationship_type")
        if not value:
            return
        target, known = normalize_relationship_type(value)
        if not known:
            unknown.append(f"{path.name}: {value}")
            return
        if target != value:
            holder["relationship_type"] = target
            changed = True

    for link in links:
        _normalize(link)
        for endpoint in (link.get("endpoints") or {}).values():
            if isinstance(endpoint, dict):
                _normalize(endpoint)

    if changed and not dry_run:
        save_json(path, document)
    if changed:
        print(f"  {'would update' if dry_run else 'updated'} {path}")
    return (1 if changed else 0), unknown


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Normalize relationship types onto the closed vocabulary."
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Report changes without writing."
    )
    args = parser.parse_args(argv)

    total = 0
    unknown: List[str] = []
    for person_dir in sorted(PEOPLE_DIR.iterdir()):
        if person_dir.is_dir():
            changed, missing = normalize_person(person_dir, args.dry_run)
            total += changed
            unknown.extend(missing)
    for path in sorted(META_STORIES_DIR.rglob("*.json")):
        changed, missing = normalize_meta_story(path, args.dry_run)
        total += changed
        unknown.extend(missing)

    print(f"\n{total} file(s) {'would be' if args.dry_run else ''} updated.")
    if unknown:
        print("Types outside the vocabulary (extend it or add a per-entry rule):")
        for entry in unknown:
            print(f"  {entry}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
