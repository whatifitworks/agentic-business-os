#!/usr/bin/env bash
# Install (or reinstall) the Agentic Business OS scheduler as a macOS launchd
# user agent. The job runs `.agents/scheduler.sh` every 30 minutes.
#
# Run from anywhere:
#   bash /absolute/path/to/.agents/install-launchd.sh
#
# Uninstall:
#   launchctl unload ~/Library/LaunchAgents/app.project.ops.scheduler.plist
#   rm ~/Library/LaunchAgents/app.project.ops.scheduler.plist

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCRIPT="$PROJECT_ROOT/.agents/scheduler.sh"
LABEL="app.project.ops.scheduler"
PLIST_DIR="$HOME/Library/LaunchAgents"
PLIST="$PLIST_DIR/${LABEL}.plist"
LOG_DIR="$PROJECT_ROOT/logs/scheduler"

if [[ ! -f "$SCRIPT" ]]; then
  echo "ERROR: scheduler.sh not found at $SCRIPT"
  exit 1
fi
if [[ ! -x "$SCRIPT" ]]; then
  echo "Making $SCRIPT executable..."
  chmod +x "$SCRIPT"
fi

mkdir -p "$LOG_DIR" "$PLIST_DIR"

# Discover the absolute path of common tools so the launchd job (which has
# a minimal PATH) can find them. Falls back to homebrew defaults.
HOMEBREW_BIN="/opt/homebrew/bin"
USER_BIN="$HOME/.local/bin"
JQ_PATH="$(command -v jq || true)"
UV_PATH="$(command -v uv || true)"
CLAUDE_PATH="$(command -v claude || true)"
CODEX_PATH="$(command -v codex || true)"

cat <<EOF
About to install the Agentic Business OS scheduler launchd agent.

  Label:        $LABEL
  Plist:        $PLIST
  Script:       $SCRIPT
  Working dir:  $PROJECT_ROOT
  Interval:     1800 seconds (30 minutes)
  stdout:       $LOG_DIR/launchd-stdout.log
  stderr:       $LOG_DIR/launchd-stderr.log

Discovered tool paths (used to build the agent's PATH):
  jq:     ${JQ_PATH:-NOT FOUND}
  uv:     ${UV_PATH:-NOT FOUND}
  claude: ${CLAUDE_PATH:-NOT FOUND}
  codex:  ${CODEX_PATH:-NOT FOUND}

If a job with this label already exists, it will be unloaded and replaced.

EOF

if [[ -z "$JQ_PATH" || -z "$UV_PATH" || -z "$CLAUDE_PATH" ]]; then
  echo "WARNING: one of jq / uv / claude is missing on PATH right now."
  echo "         The scheduler will fail to run until those are installed."
  echo
fi

read -r -p "Proceed with install? [y/N] " ans
case "$ans" in
  y|Y|yes|YES) ;;
  *) echo "Aborted."; exit 0 ;;
esac

# Build a PATH that covers homebrew, system bin, and the user's local bin -
# the same dirs the discovered tools live in. launchd does not source
# .zshrc / .bash_profile so we have to be explicit.
LAUNCHD_PATH="${HOMEBREW_BIN}:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:${USER_BIN}"

cat >"$PLIST" <<PLIST_EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>${LABEL}</string>

  <key>ProgramArguments</key>
  <array>
    <string>/bin/bash</string>
    <string>${SCRIPT}</string>
  </array>

  <key>WorkingDirectory</key>
  <string>${PROJECT_ROOT}</string>

  <key>EnvironmentVariables</key>
  <dict>
    <key>PATH</key>
    <string>${LAUNCHD_PATH}</string>
    <key>HOME</key>
    <string>${HOME}</string>
  </dict>

  <key>StartInterval</key>
  <integer>1800</integer>

  <key>RunAtLoad</key>
  <false/>

  <key>StandardOutPath</key>
  <string>${LOG_DIR}/launchd-stdout.log</string>

  <key>StandardErrorPath</key>
  <string>${LOG_DIR}/launchd-stderr.log</string>

  <key>ProcessType</key>
  <string>Background</string>
</dict>
</plist>
PLIST_EOF

# launchctl unload is the legacy command but still works in macOS 14/15;
# bootstrap/bootout would be the modern API but require domain targets
# (gui/<uid>) and don't accept the same plist path conventions.
if launchctl list 2>/dev/null | awk '{print $3}' | grep -qx "$LABEL"; then
  echo "Existing job '$LABEL' found - unloading first..."
  launchctl unload "$PLIST" 2>/dev/null || true
fi

echo "Loading $PLIST ..."
launchctl load "$PLIST"

echo
echo "Done. $LABEL is now loaded."
echo
echo "Useful commands:"
echo "  Check status:   launchctl list | grep $LABEL"
echo "  Trigger now:    launchctl start $LABEL"
echo "  Tail logs:      tail -F \"$LOG_DIR/launchd-stdout.log\" \"$LOG_DIR/launchd-stderr.log\""
echo "  Uninstall:      launchctl unload \"$PLIST\" && rm \"$PLIST\""
