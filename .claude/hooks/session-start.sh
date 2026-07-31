#!/usr/bin/env bash
# Prepare a Claude Code on the web container for this repository.
#
# The container starts with the repository cloned and nothing installed, so
# `npm run validate`, `python -m pytest`, `npm run type-check:py` and the
# generation scripts all fail on a cold session until this has run. Developer
# machines are left alone: they manage their own `.venv`, as described in
# docs/agent/data-generation-and-localization.md.
set -euo pipefail

if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

cd "${CLAUDE_PROJECT_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"

echo "Installing npm dependencies ..."
npm install --no-audit --no-fund

# The container is itself the isolated environment, so the packages go into the
# interpreter that `python`—and the `black`, `flake8` and `mypy` the npm
# scripts call by bare name—already resolve to, rather than into a repository
# `.venv` that nothing in the session would activate.
echo "Installing Python dependencies ..."
python -m pip install --quiet --disable-pip-version-check \
  --root-user-action=ignore -r requirements.txt -r requirements-dev.txt

# The image also carries black, flake8, mypy and pytest as standalone tools,
# each in its own environment and earlier on PATH. Those cannot see the
# packages just installed, and `mypy scripts/` then fails on the pydantic
# plugin pyproject.toml configures. Put the interpreter's own scripts first.
if [ -n "${CLAUDE_ENV_FILE:-}" ]; then
  bindir=$(python -c "import sysconfig; print(sysconfig.get_path('scripts'))")
  if [ -n "$bindir" ] && ! grep -qs -F "$bindir:" "$CLAUDE_ENV_FILE"; then
    echo "export PATH=\"$bindir:\$PATH\"" >>"$CLAUDE_ENV_FILE"
  fi
fi

# Playwright refuses to launch any browser build but the revision its client
# was released with. The image ships a different revision and browser
# downloads are blocked from the container, so point the revision the client
# asks for at the build that is actually present. Nothing to do once the two
# agree.
link_expected_browser_revision() {
  local dir="${PLAYWRIGHT_BROWSERS_PATH:-}"
  if [ -z "$dir" ] || [ ! -d "$dir" ]; then
    return 0
  fi

  local want
  want=$(node -e "
    const path = require('path');
    const root = path.dirname(require.resolve('playwright-core/package.json'));
    const browsers = require(path.join(root, 'browsers.json')).browsers;
    const chromium = browsers.find((browser) => browser.name === 'chromium');
    process.stdout.write(chromium ? chromium.revision : '');
  " 2>/dev/null) || return 0
  if [ -z "$want" ]; then
    return 0
  fi

  local have
  if [ ! -e "$dir/chromium-$want/chrome-linux/chrome" ]; then
    have=$(ls -d "$dir"/chromium-[0-9]*/chrome-linux 2>/dev/null | sort -V | tail -1) || true
    if [ -n "${have:-}" ]; then
      mkdir -p "$dir/chromium-$want"
      ln -sfn "$have" "$dir/chromium-$want/chrome-linux"
      touch "$dir/chromium-$want/INSTALLATION_COMPLETE"
      echo "Linked chromium-$want to $have."
    fi
  fi

  # Older builds keep the headless shell in `chrome-linux/headless_shell`;
  # newer ones use `chrome-headless-shell-linux64/chrome-headless-shell`.
  local shell_dir="$dir/chromium_headless_shell-$want/chrome-headless-shell-linux64"
  if [ ! -e "$shell_dir/chrome-headless-shell" ]; then
    have=$(ls "$dir"/chromium_headless_shell-[0-9]*/chrome-headless-shell-linux64/chrome-headless-shell \
              "$dir"/chromium_headless_shell-[0-9]*/chrome-linux/headless_shell 2>/dev/null |
      sort -V | tail -1) || true
    if [ -n "${have:-}" ]; then
      mkdir -p "$shell_dir"
      ln -sfn "$have" "$shell_dir/chrome-headless-shell"
      touch "$dir/chromium_headless_shell-$want/INSTALLATION_COMPLETE"
      echo "Linked chromium_headless_shell-$want to $have."
    fi
  fi
}

link_expected_browser_revision

echo "Session ready."
