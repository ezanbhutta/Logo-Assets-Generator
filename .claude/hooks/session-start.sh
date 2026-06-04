#!/bin/bash
# SessionStart hook — installs the Logo Package Engine toolchain so tests and
# the app run immediately in Claude Code on the web sessions.
# Synchronous + idempotent. Web-only.
set -euo pipefail

# Only set up in remote (Claude Code on the web) sessions.
if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

cd "$CLAUDE_PROJECT_DIR"

# System binaries + Python venv (requirements.txt) + frontend npm deps.
# setup.sh is idempotent; re-runs are fast once the container is cached.
bash scripts/setup.sh 1>&2

# Make the venv tools (python, pytest, uvicorn) the session default.
{
  echo "export PATH=\"$CLAUDE_PROJECT_DIR/.venv/bin:\$PATH\""
  echo "export LOGO_WORK_ROOT=\"/tmp/logo_jobs\""
} >> "$CLAUDE_ENV_FILE"
