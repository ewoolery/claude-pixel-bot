# claude-pixel-bot — project context

A Ulanzi TC001 pixel clock (32×8, AWTRIX 3) turned into three things:

1. **Robot notifier** — an animated pixel robot waves when Claude Code needs
   your attention, then clears. Host-driven over the LAN HTTP API.
2. **Calendar tile** — shows your next timed calendar event in the app rotation.
3. **Web control panel** — a small LAN web app for the display's everyday
   settings, with tie-ins to the above.

Everything is **stdlib-only Python + the AWTRIX HTTP API** — no pip installs,
no MQTT, no cloud.

## Hardware / network (this deployment)

| Thing | Value |
| --- | --- |
| Display | Ulanzi TC001, AWTRIX 3 firmware v0.98 |
| Display IP | `192.168.7.144` (set a DHCP reservation!) |
| Panel host | Raspberry Pi `vestabridge` — `192.168.7.34`, user `ewoolery` |
| Panel URL | `http://vestabridge.local:8080` (systemd, auto-starts on boot) |

## Layout

| Path | What it is |
| --- | --- |
| `pixel_bot.py` | Robot notifier runtime. Streams the wave to `/api/notify`. Stdlib only. |
| `frames.json` | The baked 16-frame wave animation. |
| `hooks/pixel-bot.sh` | Claude Code hook wrapper. **Always exits 0** (see gotcha). |
| `settings-snippet.json` | The `hooks` block to merge into `~/.claude/settings.json`. |
| `tools/generate_frames.py` | Rebuilds `frames.json` + the preview GIF (needs Pillow). |
| `tools/mock_awtrix.py` | Browser simulator of the display (localhost:7777) for no-hardware dev. |
| `extras/calendar_tile.py` | Next-meeting tile via `icalBuddy`. See `extras/README.md`. |
| `panel/awtrix_panel.py` | Control-panel server + `/api/*` proxy; adds `POST /panel/wave`. |
| `panel/index.html` | Control-panel UI. |
| `deploy/awtrix-panel.service` | systemd unit for running the panel on a Pi. |
| `CHEATSHEET.md` | Terminal commands to test/stop everything. |

## The three components

### 1. Robot notifier (`pixel_bot.py` + hooks)
Full-width 32×8 robot can't be a device-side GIF (AWTRIX only animates 8×8
icons), so the animation is **host-driven**: a detached loop streams frames to
`/api/notify` at ~6 fps, self-healing if it dies. Wire-up is via Claude Code
hooks in `~/.claude/settings.json`. Two proven designs (the `Notification` hook
does **not** fire reliably, so neither uses it as the trigger):

- **Approval detector (current/default):** `PreToolUse`→`tool-arm`,
  `PostToolUse`→`tool-cancel`, `UserPromptSubmit`/`Stop`→`clear`. A tool blocked
  on your approval past `PIXEL_BOT_TOOL_DELAY` (5s) → wave. Never waves on a
  plain end-of-turn message. Needs default "ask" permission mode to see prompts.
- **Idle notifier (alt):** `Stop`→`arm`, `UserPromptSubmit`→`clear`. Waves after
  `PIXEL_BOT_IDLE_DELAY` of quiet.

Config via env: `AWTRIX_IP`, `PIXEL_BOT_TOOL_DELAY`, `PIXEL_BOT_IDLE_DELAY`,
`PIXEL_BOT_LOG` (diagnostics). Manual: `pixel_bot.py attention|clear|test`.

### 2. Calendar tile (`extras/calendar_tile.py`)
Reads the Mac's Calendar via `icalBuddy` (no OAuth), pushes the next timed event
as a custom app; warns before it starts. **Open issue:** a background/launchd
job is Calendar-TCC-blocked on macOS (works in an interactive Terminal). For
unattended refresh, pivot the data source to the Google Calendar API (the tile
and device code stay identical). See `extras/README.md`.

### 3. Control panel (`panel/`)
Serves the UI and proxies `/api/*` to the device (AWTRIX has no CORS headers, so
a browser can't call it cross-origin). Controls page toggles (Time/Date/Temp/
Humidity/Battery — native toggles need a device reboot), pacing (`ATIME` seconds
/`SSPEED`/`TSPEED`/`TEFF`), brightness/look, a live screen mirror (`/api/screen`),
and Actions: wave the robot, send a scrolling message, next/power, remove the
calendar tile. Runs 24/7 on the Pi via systemd; manage with
`sudo systemctl {status,restart} awtrix-panel` and `journalctl -u awtrix-panel -f`.

## Gotchas worth preserving

- **`hooks/pixel-bot.sh` always exits 0.** On Claude Code's `Stop` event, exit
  code 2 tells Claude *not* to stop — a failing curl to an unreachable display
  could otherwise trap a session. Never change the trailing `exit 0`.
- **The `Notification` hook doesn't fire** in practice (tested: idle + permission,
  before/after restart, with/without matcher) even when the OS notification shows.
  That's why the notifier is built on Pre/PostToolUse + Stop + UserPromptSubmit.
- **`ATIME` unit varies by firmware** (seconds here = `7`; some report `7000`).
  The panel detects the unit on load — don't hardcode.
- **Google Drive + launchd:** background/launchd jobs can't read files in
  CloudStorage ("Operation not permitted"). The panel runs from a local copy on
  the Pi; the calendar job would need the same treatment.
- **The Pi can't read the Mac's Calendar.** icalBuddy is macOS-only — a Pi-side
  calendar source must use the Google Calendar API.
- **Sandbox vs. the wave's kill.** The wave is a detached loop that `clear`
  stops by *signalling* it. Claude Code's Bash sandbox can block process
  signalling/enumeration (`pgrep: Cannot get process list`), so `clear` dismisses
  the notification but can't kill the loop → the wave wouldn't clear. Fixed by a
  hard `PIXEL_BOT_WAVE_MAX` cap (default 20s) so the loop self-terminates
  regardless. If the wave ever sticks: `pkill -f "pixel_bot.py (play|armed|tool-armed)"`.
