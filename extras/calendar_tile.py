#!/usr/bin/env python3
"""
calendar_tile.py — show your next meeting on a Ulanzi TC001 (AWTRIX 3), and
pop a wave-style alert just before it starts.

Reads the Mac's Calendar via `icalBuddy` (which sees whatever accounts are in
System Settings > Internet Accounts — including Google). Stdlib only + the
icalBuddy CLI (`brew install ical-buddy`).

Commands:
    calendar_tile.py update   read calendar, refresh the tile, alert if imminent
    calendar_tile.py demo      push a fake "10:30 Standup" tile (no calendar needed)
    calendar_tile.py clear     remove the tile

Run `update` on a schedule (every minute) via launchd. See extras/README.

Config via environment:
    AWTRIX_IP              device IP                        (required)
    CAL_WARN_MINUTES       minutes-before to fire the alert (default 2)
    CAL_APP_NAME           AWTRIX custom-app slot name      (default "calendar")
    CAL_TIMEOUT            per-request timeout, seconds     (default 2)
    CAL_STATE             alert-dedupe state file          (default /tmp/pixel-cal.state)

NOTE: icalBuddy needs macOS Calendar access. Run `icalBuddy calendars` once in
an interactive Terminal and click Allow. A background/launchd runner needs the
same grant — see extras/README for the TCC notes.
"""
import json
import os
import re
import subprocess
import sys
import urllib.request
from datetime import datetime

IP        = os.environ.get("AWTRIX_IP", "192.168.1.50")
WARN_MIN  = float(os.environ.get("CAL_WARN_MINUTES", "2"))
APP_NAME  = os.environ.get("CAL_APP_NAME", "calendar")
TIMEOUT   = float(os.environ.get("CAL_TIMEOUT", "2"))
STATE     = os.environ.get("CAL_STATE", "/tmp/pixel-cal.state")
WINDOW    = int(os.environ.get("CAL_WINDOW_DAYS", "7"))   # how many days ahead to look for the next event
BASE      = "http://%s/api" % IP

ICALBUDDY = "/opt/homebrew/bin/icalBuddy"
if not os.path.exists(ICALBUDDY):
    ICALBUDDY = "icalBuddy"   # fall back to PATH

# Property separator we ask icalBuddy to use, so output is easy to split.
SEP = "@@"


# ─── AWTRIX HTTP ──────────────────────────────────────────────────────────────
def post(endpoint, payload=None):
    url = "%s/%s" % (BASE, endpoint)
    data = json.dumps(payload).encode() if payload is not None else b""
    req = urllib.request.Request(url, data=data, method="POST",
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT):
            return True
    except Exception:
        return False


# ─── calendar ─────────────────────────────────────────────────────────────────
def _run_icalbuddy():
    """Return icalBuddy's raw lines for today's remaining events, or None on error."""
    cmd = [
        ICALBUDDY,
        "-n",                 # only events from now on
        "-nc",                # no calendar names
        "-nrd",               # no relative dates ("today"/"tomorrow")
        "-b", "",             # no bullet
        "-ps", "|%s|" % SEP,  # property separator
        "-iep", "datetime,title",
        "-po", "datetime,title",
        "-df", "%Y-%m-%d",
        "-tf", "%H:%M",
        "eventsToday+%d" % WINDOW,   # now through WINDOW days ahead → next upcoming, any day
    ]
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
    except Exception:
        return None
    if out.returncode != 0 or "No calendars" in (out.stderr + out.stdout):
        return None
    return out.stdout


def _pick_next(raw, now=None):
    """From icalBuddy output text, return (start_datetime, title) for the soonest
    upcoming *timed* event (all-day events are skipped), or None."""
    now = now or datetime.now()
    best = None
    for line in raw.splitlines():
        line = line.strip()
        if SEP not in line:
            continue
        dt_part, title = (p.strip() for p in line.split(SEP, 1))
        # dt_part looks like "2026-08-05 10:30 - 11:00" (or just a date for all-day).
        date_m = re.search(r"\d{4}-\d{2}-\d{2}", dt_part)
        time_m = re.search(r"\b(\d{1,2}):(\d{2})\b", dt_part)
        if not (date_m and time_m):
            continue   # all-day / undated → no start time to count down to
        try:
            start = datetime.strptime(
                "%s %s" % (date_m.group(0), time_m.group(0)), "%Y-%m-%d %H:%M")
        except ValueError:
            continue
        if start < now:
            continue
        if best is None or start < best[0]:
            best = (start, title or "(busy)")
    return best


def next_event(now=None):
    """Read the calendar and return the next timed event, or None. Returns None
    for BOTH 'no access' and 'no events' — use cmd_update for the distinction."""
    raw = _run_icalbuddy()
    if raw is None:
        return None
    return _pick_next(raw, now)


# ─── tile + alert ─────────────────────────────────────────────────────────────
def _day_prefix(start, now=None):
    """'' for today, 'Tmrw ' for tomorrow, weekday ('Wed ') within a week, else date."""
    now = now or datetime.now()
    delta = (start.date() - now.date()).days
    if delta <= 0:
        return ""
    if delta == 1:
        return "Tmrw "
    if delta < 7:
        return start.strftime("%a ")     # Mon, Tue, …
    return start.strftime("%b%-d ")      # Aug12


def _label(start, title, mins):
    title = re.sub(r"\s+", " ", title).strip()
    if len(title) > 18:
        title = title[:17] + "…"
    text = "%s%s %s" % (_day_prefix(start), start.strftime("%H:%M"), title)
    return text, start.strftime("%H:%M")


def show_tile(start, title, mins):
    """Persistent tile in the app rotation. Colour warms up as the meeting nears."""
    text, _ = _label(start, title, mins)
    color = "#EBEBF5"                       # normal
    if mins <= WARN_MIN:
        color = "#FF3B30"                   # imminent (red)
    elif mins <= 15:
        color = "#FF9500"                   # soon (amber)
    post("custom?name=%s" % APP_NAME, {
        "text": text,
        "color": color,
        "scrollSpeed": 90,
        "duration": 7,
    })


def clear_tile():
    post("custom?name=%s" % APP_NAME, {})   # empty body removes the app


def alert(start, title):
    """One-time takeover + chime just before the meeting."""
    text, _ = _label(start, title, 0)
    post("notify", {
        "text": text,
        "color": "#FF9500",
        "duration": 8,
        "stack": False,
        "wakeup": True,
        "rtttl": "cal:d=4,o=5,b=140:8e6,8g6,8e6,8c6",
    })


# ─── dedupe state (so we alert once per event) ──────────────────────────────────
def already_alerted(key):
    try:
        with open(STATE) as f:
            return f.read().strip() == key
    except Exception:
        return False


def mark_alerted(key):
    try:
        with open(STATE, "w") as f:
            f.write(key)
    except Exception:
        pass


# ─── commands ───────────────────────────────────────────────────────────────
def _log(msg):
    sys.stderr.write("calendar_tile: %s\n" % msg)


def cmd_update():
    raw = _run_icalbuddy()
    if raw is None:
        # No calendar access (or icalBuddy error). Leave the existing tile alone
        # rather than wiping it on a transient/permission failure.
        _log("no calendar access — leaving tile unchanged")
        return 0
    ev = _pick_next(raw)
    if not ev:
        _log("calendar OK, no upcoming timed event — clearing tile")
        clear_tile()
        return 0
    start, title = ev
    mins = (start - datetime.now()).total_seconds() / 60.0
    show_tile(start, title, mins)
    _log("next = %s %s (%.0f min)" % (start.strftime("%Y-%m-%d %H:%M"), title, mins))
    key = start.strftime("%Y%m%dT%H%M") + "|" + title
    if 0 <= mins <= WARN_MIN and not already_alerted(key):
        alert(start, title)
        mark_alerted(key)
    return 0


def cmd_demo():
    from datetime import timedelta
    start = datetime.now() + timedelta(minutes=12)
    show_tile(start, "Standup", 12)
    print("Pushed demo tile: %s Standup" % start.strftime("%H:%M"))
    return 0


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "update"
    if cmd == "update":
        return cmd_update()
    if cmd == "demo":
        return cmd_demo()
    if cmd == "clear":
        clear_tile()
        return 0
    print("usage: calendar_tile.py <update|demo|clear>", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main() or 0)
