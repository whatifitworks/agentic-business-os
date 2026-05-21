#!/usr/bin/env bash
# Agentic Business OS scheduler.
#
# Designed to be invoked every 30 minutes by launchd. On every tick:
#   1. Read .agents/schedules.yaml plus .agents/last-run.json.
#   2. Run any async task whose schedule has fired since its last run.
#   3. After running, scan logs/ for any brief still flagged
#      `status: pending` and send a reminder notification if so.
#
# YAML parsing, timezone math, and frontmatter reads are delegated to
# .agents/scheduler_helper.py via `uv run`. The helper resolves PEP 723
# inline dependencies (PyYAML) on first invocation.
#
# Run manually:   bash .agents/scheduler.sh
# Install cron:   bash .agents/install-launchd.sh

set -euo pipefail

# launchd runs with a minimal PATH. Ensure tools that the scheduler,
# MCP servers, and helper scripts need are reachable.
export PATH="$HOME/google-cloud-sdk/bin:$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:$PATH"

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCHEDULES="$PROJECT_ROOT/.agents/schedules.yaml"
LAST_RUN="$PROJECT_ROOT/.agents/last-run.json"
HELPER="$PROJECT_ROOT/.agents/scheduler_helper.py"
OPS_STATE="$PROJECT_ROOT/system/tools/ops_state.py"
STATE_DB="$PROJECT_ROOT/system/state/ops.db"
LOGS_DIR="$PROJECT_ROOT/logs"
SCHED_LOG_DIR="$LOGS_DIR/scheduler"
TASK_LOCKS_DIR="$PROJECT_ROOT/.agents/task-locks"

mkdir -p "$SCHED_LOG_DIR"
mkdir -p "$TASK_LOCKS_DIR"
SCHED_LOG="$SCHED_LOG_DIR/$(date +%Y-%m-%d).log"

# Read the configured timezone from schedules.yaml so all bash-side
# timestamps (filenames, frontmatter, last-run) match what the Python
# helper uses for due-time math. Falls back to Europe/Berlin.
read_tz_from_yaml() {
  if [[ ! -f "$SCHEDULES" ]]; then
    echo "Europe/Berlin"
    return
  fi
  local v
  v="$(awk '
    /^timezone:[[:space:]]*/ {
      sub(/^timezone:[[:space:]]*/, "")
      gsub(/["'"'"']/, "")
      sub(/[[:space:]]+#.*$/, "")
      print
      exit
    }
  ' "$SCHEDULES")"
  if [[ -z "$v" ]]; then
    echo "Europe/Berlin"
  else
    echo "$v"
  fi
}
SCHED_TZ="$(read_tz_from_yaml)"

# Wrap `date` to consistently use the configured timezone and produce
# an ISO-8601 string that python's `datetime.fromisoformat` can read on
# both macOS BSD date and GNU date.
sched_date_iso() {
  TZ="$SCHED_TZ" date -Iseconds 2>/dev/null \
    || TZ="$SCHED_TZ" date +%Y-%m-%dT%H:%M:%S%z
}

sched_date_compact() {
  TZ="$SCHED_TZ" date +%Y-%m-%d-%H:%M
}

# ---------- helpers -----------------------------------------------------------

log() {
  local ts
  ts="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  printf '[%s] %s\n' "$ts" "$*" >>"$SCHED_LOG"
}

notify() {
  local title="$1" message="$2"
  if command -v osascript >/dev/null 2>&1; then
    osascript \
      -e "display notification \"${message//\"/\\\"}\" with title \"${title//\"/\\\"}\"" \
      >/dev/null 2>&1 || true
  fi
}

acquire_task_lock() {
  local task_name="$1"
  local lock_dir="$TASK_LOCKS_DIR/$task_name.lock"
  local pid_file="$lock_dir/pid"
  local started_file="$lock_dir/started_at"

  if mkdir "$lock_dir" 2>/dev/null; then
    printf '%s\n' "$$" >"$pid_file"
    sched_date_iso >"$started_file"
    return 0
  fi

  local existing_pid=""
  if [[ -f "$pid_file" ]]; then
    existing_pid="$(<"$pid_file")"
  fi

  if [[ -n "$existing_pid" ]] && kill -0 "$existing_pid" 2>/dev/null; then
    log "task '$task_name' already in flight (pid $existing_pid), skipping"
    return 1
  fi

  log "task '$task_name' has a stale lock, clearing $lock_dir"
  rm -rf "$lock_dir"

  if mkdir "$lock_dir" 2>/dev/null; then
    printf '%s\n' "$$" >"$pid_file"
    sched_date_iso >"$started_file"
    return 0
  fi

  log "task '$task_name' lock recovery failed for $lock_dir, skipping"
  return 1
}

write_task_lock_pid() {
  local task_name="$1"
  local pid="$2"
  local lock_dir="$TASK_LOCKS_DIR/$task_name.lock"
  local pid_file="$lock_dir/pid"
  printf '%s\n' "$pid" >"$pid_file"
}

release_task_lock() {
  local task_name="$1"
  local lock_dir="$TASK_LOCKS_DIR/$task_name.lock"
  rm -rf "$lock_dir"
}

require_tool() {
  local name="$1"
  if ! command -v "$name" >/dev/null 2>&1; then
    log "FATAL: required tool '$name' not on PATH"
    exit 1
  fi
}

frontmatter_value() {
  local file="$1"
  local key="$2"
  awk -v key="$key" '
    NR == 1 && $0 == "---" { in_fm = 1; next }
    in_fm && $0 == "---" { exit }
    in_fm && $0 ~ ("^" key ":[[:space:]]*") {
      sub("^" key ":[[:space:]]*", "")
      print
      exit
    }
  ' "$file"
}

# ---------- task execution ----------------------------------------------------

run_task() {
  local task_json="$1"

  local name skill log_dir runner model notify_flag notify_policy remind_flag prompt
  name="$(jq -r '.name' <<<"$task_json")"
  skill="$(jq -r '.skill' <<<"$task_json")"
  log_dir="$(jq -r '.log_dir' <<<"$task_json")"
  runner="$(jq -r '.runner' <<<"$task_json")"
  model="$(jq -r '.model' <<<"$task_json")"
  notify_flag="$(jq -r '.notify' <<<"$task_json")"
  notify_policy="$(jq -r '.notify_policy // "always"' <<<"$task_json")"
  remind_flag="$(jq -r '.remind_until_reviewed' <<<"$task_json")"
  prompt="$(jq -r '.prompt' <<<"$task_json")"

  if ! acquire_task_lock "$name"; then
    return 0
  fi

  local ts log_file runner_log
  ts="$(sched_date_compact)"
  mkdir -p "$LOGS_DIR/$log_dir"
  log_file="$LOGS_DIR/$log_dir/${ts}-brief.md"
  runner_log="$LOGS_DIR/$log_dir/${ts}-runner.log"

  # Render the log file path into the prompt template.
  prompt="${prompt//\{\{LOG_FILE\}\}/$log_file}"

  # Pre-create the brief file with a stub frontmatter so:
  #   (a) /review-support and `pending-reviews` see it even if the
  #       runner crashes mid-run, and
  #   (b) the runner has a clear file path to overwrite via Write.
  local status="informational"
  if [[ "$remind_flag" == "true" ]]; then
    status="pending"
  fi
  cat >"$log_file" <<EOF
---
status: $status
task: $name
generated_at: $(sched_date_iso)
runner: $runner
model: $model
stub: true
---

(Stub written by scheduler.sh. The runner is expected to overwrite this
file with the real brief. If you are reading this, the runner exited
without writing - check $runner_log for details.)
EOF

  log "RUN start name=$name runner=$runner model=$model log=$log_file"

  local rc=0
  local outcome="success"
  local runner_pid=""
  case "$runner" in
    claude)
      (
        cd "$PROJECT_ROOT"
        claude -p "$prompt" \
               --model "$model" \
               --permission-mode bypassPermissions \
               --output-format text
      ) >"$runner_log" 2>&1 &
      runner_pid=$!
      ;;
    codex)
      (
        cd "$PROJECT_ROOT"
        codex exec \
              --cd "$PROJECT_ROOT" \
              --model "$model" \
              --dangerously-bypass-approvals-and-sandbox \
              "$prompt"
      ) >"$runner_log" 2>&1 &
      runner_pid=$!
      ;;
    command)
      local task_command
      task_command="$(jq -r '.command' <<<"$task_json")"
      task_command="${task_command//\{\{LOG_FILE\}\}/$log_file}"
      (
        cd "$PROJECT_ROOT"
        bash -lc "$task_command"
      ) >"$runner_log" 2>&1 &
      runner_pid=$!
      ;;
    *)
      log "ERROR unknown runner '$runner' for task '$name'"
      rc=1
      ;;
  esac

  if [[ -n "$runner_pid" ]]; then
    write_task_lock_pid "$name" "$runner_pid"
    wait "$runner_pid" || rc=$?
  fi

  log "RUN done  name=$name rc=$rc"

  if [[ $rc -eq 0 ]] && grep -q '^stub: true$' "$log_file"; then
    log "RUN verify failed name=$name stub_not_overwritten log=$log_file"
    printf '\n[post-run verification] Stub brief was not overwritten.\n' >>"$runner_log"
    rc=1
  fi

  if [[ $rc -eq 0 ]]; then
    local verify_report_html_required verify_report_html_allow_null verify_report_html_require_file
    verify_report_html_required="$(jq -r '.verify.report_html.required // false' <<<"$task_json")"
    verify_report_html_allow_null="$(jq -r '.verify.report_html.allow_null // false' <<<"$task_json")"
    verify_report_html_require_file="$(jq -r '.verify.report_html.require_existing_file_when_present // true' <<<"$task_json")"

    if [[ "$verify_report_html_required" == "true" ]]; then
      local report_html=""
      report_html="$(frontmatter_value "$log_file" "report_html")"

      if [[ -z "$report_html" ]]; then
        log "RUN verify failed name=$name missing_report_html log=$log_file"
        printf '\n[post-run verification] report_html frontmatter is missing.\n' >>"$runner_log"
        rc=1
      elif [[ "$report_html" == "null" ]]; then
        if [[ "$verify_report_html_allow_null" == "true" ]]; then
          outcome="blocked"
          log "RUN blocked name=$name report_html=null log=$log_file"
        else
          log "RUN verify failed name=$name null_report_html_not_allowed log=$log_file"
          printf '\n[post-run verification] report_html was null but this task requires a file.\n' >>"$runner_log"
          rc=1
        fi
      elif [[ "$verify_report_html_require_file" == "true" && ! -f "$report_html" ]]; then
        log "RUN verify failed name=$name missing_report_file report_html=$report_html log=$log_file"
        printf '\n[post-run verification] report_html file is missing: %s\n' "$report_html" >>"$runner_log"
        rc=1
      fi
    fi
  fi

  local final_status=""
  if [[ $rc -eq 0 ]]; then
    final_status="$(frontmatter_value "$log_file" "status")"
    if [[ "$final_status" == "blocked" ]]; then
      outcome="blocked"
      log "RUN blocked name=$name status=blocked log=$log_file"
    elif [[ "$final_status" == "failed" ]]; then
      outcome="failed"
      log "RUN marked failed name=$name status=failed log=$log_file"
    fi
  fi

  if [[ $rc -ne 0 ]]; then
    outcome="failed"
    final_status="$(frontmatter_value "$log_file" "status" 2>/dev/null || true)"
  fi

  local recorded_at
  recorded_at="$(sched_date_iso)"

  uv run "$HELPER" record-run \
    --last-run "$LAST_RUN" \
    --task "$name" \
    --time "$recorded_at" \
    --exit "$rc" \
    --outcome "$outcome" >>"$SCHED_LOG" 2>&1 || log "WARN: record-run failed for $name"

  if [[ -f "$OPS_STATE" ]]; then
    python3 "$OPS_STATE" --db "$STATE_DB" record-run \
      --task "$name" \
      --ran-at "$recorded_at" \
      --exit "$rc" \
      --outcome "$outcome" \
      --status "$final_status" \
      --runner "$runner" \
      --model "$model" \
      --brief-path "$log_file" \
      --runner-log-path "$runner_log" >>"$SCHED_LOG" 2>&1 || log "WARN: ops_state record-run failed for $name"
  fi

  local should_notify="false"
  if [[ "$notify_flag" == "true" ]]; then
    if [[ "$notify_policy" == "always" ]]; then
      should_notify="true"
    elif [[ "$notify_policy" == "on_problem" && ( $rc -ne 0 || "$outcome" == "blocked" || "$outcome" == "failed" ) ]]; then
      should_notify="true"
    fi
  fi

  if [[ "$should_notify" == "true" ]]; then
    if [[ $rc -eq 0 ]]; then
      # Try to enrich the notification with whatever the runner wrote
      # into the brief frontmatter (e.g. needs_reply_count).
      local fm needs_reply notify_title notify_body
      fm="$(uv run "$HELPER" frontmatter --file "$log_file" 2>/dev/null || echo '{}')"
      needs_reply="$(jq -r '.needs_reply_count // empty' <<<"$fm")"

      notify_title="Agentic Business OS - $name"
      if [[ "$outcome" == "blocked" ]]; then
        notify_title="Agentic Business OS - $name BLOCKED"
        notify_body="see $(basename "$log_file")"
      elif [[ "$outcome" == "failed" ]]; then
        notify_title="Agentic Business OS - $name FAILED"
        notify_body="status=failed - see $(basename "$log_file")"
      elif [[ -n "$needs_reply" && "$needs_reply" != "null" ]]; then
        notify_body="$needs_reply tickets need replies - run /review-support"
      else
        notify_body="finished - $(basename "$log_file")"
      fi
      notify "$notify_title" "$notify_body"
    else
      notify "Agentic Business OS - $name FAILED" "rc=$rc - see $runner_log"
    fi
  fi

  release_task_lock "$name"
}

# ---------- reminder pass -----------------------------------------------------

reminder_pass() {
  local pending_json
  if [[ -f "$OPS_STATE" ]] && python3 "$OPS_STATE" --db "$STATE_DB" sync-briefs --logs-dir "$LOGS_DIR" --schedules "$SCHEDULES" --quiet 2>>"$SCHED_LOG"; then
    pending_json="$(python3 "$OPS_STATE" --db "$STATE_DB" pending-briefs --reminders-only 2>>"$SCHED_LOG" || echo '[]')"
  else
    log "WARN: ops_state pending sync failed; falling back to markdown scan"
    pending_json="$(uv run "$HELPER" pending --logs-dir "$LOGS_DIR" --schedules "$SCHEDULES" 2>>"$SCHED_LOG" || echo '[]')"
  fi
  local pending_count
  pending_count="$(jq 'length' <<<"$pending_json")"
  log "pending reviews: $pending_count"

  if [[ "$pending_count" -le 0 ]]; then
    return
  fi

  # Build a "support: 3 from 09:00, seo: 1 from 10:00" style summary.
  local summary
  summary="$(jq -r '
    group_by(.log_dir)
    | map({
        dir: .[0].log_dir,
        n: length,
        oldest: (map(.generated_at) | min)
      })
    | map("\(.dir): \(.n) from \(.oldest | sub("^.*T"; "") | sub(":[0-9]{2}([+-].*)?$"; ""))")
    | join(", ")
  ' <<<"$pending_json")"

  notify "Agentic Business OS review pending" "Still waiting: $summary"
  log "reminder sent: $summary"
}

# ---------- main --------------------------------------------------------------

main() {
  if [[ ! -f "$SCHEDULES" ]]; then
    log "no schedules file at $SCHEDULES, nothing to do"
    exit 0
  fi
  require_tool jq
  require_tool uv

  log "tick start"

  local due_json
  due_json="$(uv run "$HELPER" due \
    --schedules "$SCHEDULES" \
    --last-run "$LAST_RUN" \
    --state-db "$STATE_DB" 2>>"$SCHED_LOG" || echo '[]')"

  local due_count
  due_count="$(jq 'length' <<<"$due_json")"
  log "due tasks: $due_count"

  local i=0
  while [[ $i -lt $due_count ]]; do
    local task_json
    task_json="$(jq -c ".[$i]" <<<"$due_json")"
    run_task "$task_json"
    i=$((i + 1))
  done

  if [[ -f "$OPS_STATE" ]]; then
    python3 "$OPS_STATE" --db "$STATE_DB" sync-recurring \
      --recurring "$PROJECT_ROOT/.agents/recurring.yaml" \
      --today "$(TZ="$SCHED_TZ" date +%F)" \
      --quiet 2>>"$SCHED_LOG" || log "WARN: ops_state sync-recurring failed"
  fi

  reminder_pass

  log "tick done"
}

main "$@"
