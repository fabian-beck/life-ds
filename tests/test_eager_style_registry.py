"""The person style registry must stay off the eager entry chunk.

`data/person_styles.json` is the one thing on the critical path whose size is a
function of how many lives the project has — roughly 2 kB per person, and it
only grows. A single static import anywhere in the eagerly reached graph pulls
all of it back into the chunk every visitor downloads before anything renders,
and nothing about the source says so: the file looks the same either way.

A build-output assertion would be the direct test, but a build takes minutes
and this failure has one cause, so the source is what is guarded.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
APP = SRC_DIR / "App.svelte"
REGISTRY = "person_styles.json"

# `import x from "…/person_styles.json"` — the static form. The dynamic form,
# `await import("…/person_styles.json")`, has the parenthesis instead.
STATIC_IMPORT = re.compile(
    r"^\s*import\s+[^;\n]*?from\s+[\"'][^\"']*" + re.escape(REGISTRY) + r"[\"']",
    re.MULTILINE,
)


def _sources() -> list[Path]:
    return sorted(
        path
        for suffix in ("*.svelte", "*.js")
        for path in SRC_DIR.rglob(suffix)
    )


class StyleRegistryStaysLazyTest(unittest.TestCase):
    def test_nothing_imports_the_registry_statically(self):
        offenders = [
            str(path.relative_to(REPO_ROOT))
            for path in _sources()
            if STATIC_IMPORT.search(path.read_text(encoding="utf-8"))
        ]

        self.assertEqual(
            [],
            offenders,
            f"{REGISTRY} must be loaded with await import() and passed down as a "
            f"prop; a static import puts all of it in the entry chunk",
        )

    def test_the_app_still_loads_it(self):
        """The guard above passes just as well if nothing loads the file at all."""
        source = APP.read_text(encoding="utf-8")

        self.assertRegex(source, r"await import\([\"'][^\"']*" + re.escape(REGISTRY))

    def test_the_components_that_use_it_take_it_as_a_prop(self):
        """Reached from App.svelte, so an import in any of them is the same leak."""
        for name in (
            "MetaStoryView",
            "MetaStoryTimeline",
            "MetaStoryNetwork",
            "MetaStoryMap",
        ):
            with self.subTest(component=name):
                source = (SRC_DIR / "components" / f"{name}.svelte").read_text(
                    encoding="utf-8"
                )
                self.assertIn("export let personStyles", source)


if __name__ == "__main__":
    unittest.main()
