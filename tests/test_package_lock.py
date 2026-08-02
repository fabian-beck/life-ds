"""Every peer a locked package requires must itself be locked.

`npm ci` — what the Ubuntu runner and the session hook both use — installs the
lockfile exactly and refuses one that cannot satisfy a declared peer
dependency. `npm install` instead repairs the file quietly, and it records peer
bookkeeping per platform, so a lockfile refreshed on Windows has twice arrived
here missing an entry that Linux needs, and twice the runner was the thing that
noticed.

This checks the rule the runner applies, against the file as committed: for
every package that declares a peer dependency it does not mark optional, a
package of that name has to be resolvable from where it sits.
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOCKFILE = ROOT / "package-lock.json"


def _packages() -> dict:
    return json.loads(LOCKFILE.read_text(encoding="utf-8"))["packages"]


def _resolves(packages: dict, from_path: str, name: str) -> bool:
    """Whether `name` is reachable from `from_path`, the way Node resolves.

    A package sitting at ``node_modules/a/node_modules/b`` sees its own nested
    ``node_modules`` first, then its parents' in turn, up to the root — so the
    peer may be locked beside it or anywhere above it.
    """
    directory = from_path
    while True:
        prefix = f"{directory}/" if directory else ""
        if f"{prefix}node_modules/{name}" in packages:
            return True
        if not directory:
            return False
        directory = (
            directory.rsplit("/node_modules/", 1)[0]
            if "/node_modules/" in directory
            else ""
        )


class PackageLockPeerTests(unittest.TestCase):
    def test_every_required_peer_is_locked(self) -> None:
        packages = _packages()
        missing = []

        for path, entry in packages.items():
            peers = entry.get("peerDependencies") or {}
            optional_peers = {
                name
                for name, meta in (entry.get("peerDependenciesMeta") or {}).items()
                if isinstance(meta, dict) and meta.get("optional")
            }
            for name in peers:
                if name in optional_peers:
                    continue
                if not _resolves(packages, path, name):
                    missing.append(f"{path or '(root)'} needs peer {name}")

        self.assertEqual(
            missing,
            [],
            "npm ci will refuse this lockfile; regenerate it on Linux "
            "(npm install) and commit the result",
        )


if __name__ == "__main__":
    unittest.main()
