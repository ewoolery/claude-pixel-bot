#!/usr/bin/env bash
#
# pixel-bot.sh — Claude Code hook wrapper for the waving pixel robot.
#
# Install (or symlink) to: ~/.claude/hooks/pixel-bot.sh   (chmod +x)
# Usage:  pixel-bot.sh <attention|clear|test>
#
# This wrapper ALWAYS exits 0. On Claude Code's Stop event, exit code 2 tells
# Claude *not* to stop and to keep the conversation going — a display that is
# unplugged or unreachable must never be able to trap a session. Do not change
# the trailing `exit 0`.

set -uo pipefail   # deliberately NOT -e

# ─── config ──────────────────────────────────────────────────────────────────
# Point this at the checkout, then set AWTRIX_IP (here or in the environment).
BOT_DIR="${PIXEL_BOT_DIR:-$HOME/.claude/pixel-bot}"
export AWTRIX_IP="${AWTRIX_IP:-192.168.1.50}"      # <-- set your device IP
# ─────────────────────────────────────────────────────────────────────────────

PY="$(command -v python3 || command -v python || true)"
[[ -z "$PY" ]] && exit 0   # no interpreter — fail silent, never block a turn

# Read hook JSON from stdin (optional) so we can log it; never block.
hook_json=""
[[ -t 0 ]] || hook_json="$(timeout 1 cat 2>/dev/null || true)"

# Opt-in diagnostics: set PIXEL_BOT_LOG to a file to record every invocation
# (timestamp, arg, and the raw hook event JSON). Handy for verifying which
# Claude Code events actually reach the hook.
if [[ -n "${PIXEL_BOT_LOG:-}" ]]; then
  printf '%s  arg=%-9s  %s\n' \
    "$(date '+%Y-%m-%d %H:%M:%S')" "${1:-}" "$hook_json" \
    >>"$PIXEL_BOT_LOG" 2>/dev/null || true
fi

"$PY" "$BOT_DIR/pixel_bot.py" "${1:-}" >/dev/null 2>&1 || true

exit 0   # see header — do not remove
