#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
LABEL="com.project.ops.inbox-auto-ingest"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
OUT_LOG="$PROJECT_ROOT/logs/memory-ingest/launchd.out.log"
ERR_LOG="$PROJECT_ROOT/logs/memory-ingest/launchd.err.log"

if [[ "${1:-}" == "--uninstall" ]]; then
  launchctl bootout "gui/$UID" "$PLIST" 2>/dev/null || true
  rm -f "$PLIST"
  echo "Uninstalled $LABEL"
  exit 0
fi

mkdir -p "$(dirname "$PLIST")" "$PROJECT_ROOT/logs/memory-ingest"

cat >"$PLIST" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
 "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>$LABEL</string>

  <key>WorkingDirectory</key>
  <string>$PROJECT_ROOT</string>

  <key>ProgramArguments</key>
  <array>
    <string>/usr/bin/python3</string>
    <string>$PROJECT_ROOT/system/tools/inbox_auto_ingest.py</string>
    <string>--root</string>
    <string>$PROJECT_ROOT</string>
    <string>launch</string>
    <string>--runner</string>
    <string>codex</string>
  </array>

  <key>WatchPaths</key>
  <array>
    <string>$PROJECT_ROOT/inbox</string>
  </array>

  <key>RunAtLoad</key>
  <true/>

  <key>ThrottleInterval</key>
  <integer>30</integer>

  <key>EnvironmentVariables</key>
  <dict>
    <key>PATH</key>
    <string>/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin</string>
  </dict>

  <key>StandardOutPath</key>
  <string>$OUT_LOG</string>
  <key>StandardErrorPath</key>
  <string>$ERR_LOG</string>
</dict>
</plist>
PLIST

launchctl bootout "gui/$UID" "$PLIST" 2>/dev/null || true
launchctl bootstrap "gui/$UID" "$PLIST"
launchctl enable "gui/$UID/$LABEL"

echo "Installed $LABEL"
echo "Watching: $PROJECT_ROOT/inbox"
echo "Logs: $PROJECT_ROOT/logs/memory-ingest/"
