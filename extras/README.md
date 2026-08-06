# extras — more things to wire to the display

Small companion scripts that reuse the same AWTRIX HTTP pattern as the robot.

## `calendar_tile.py` — next-meeting tile

Shows your **next upcoming calendar event** as a tile in the clock's app
rotation, and fires a wave-style takeover + chime just before it starts.

- Reads the Mac's Calendar via **`icalBuddy`** (`brew install ical-buddy`), so it
  sees whatever accounts are in *System Settings → Internet Accounts* — including
  Google — with no OAuth.
- **Skips all-day events** (birthdays, holidays) and shows the soonest *timed*
  event, labelled by day: `10:30 Standup` (today), `Tmrw 05:30 …`, `Wed 9:00 …`.
- Colour warms with urgency: white → amber (<15 min) → red (<2 min).

```bash
AWTRIX_IP=192.168.7.144 python3 extras/calendar_tile.py update   # refresh the tile
AWTRIX_IP=192.168.7.144 python3 extras/calendar_tile.py demo     # push a fake tile
AWTRIX_IP=192.168.7.144 python3 extras/calendar_tile.py clear    # remove the tile
```

Config (env): `AWTRIX_IP` (required), `CAL_WARN_MINUTES` (2), `CAL_WINDOW_DAYS`
(7), `CAL_APP_NAME` (calendar). See the script header for the rest.

### Scheduling (every minute) via LaunchAgent

```bash
cp extras/com.ewoolery.pixel-bot.calendar.plist ~/Library/LaunchAgents/
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.ewoolery.pixel-bot.calendar.plist
# uninstall: launchctl bootout gui/$(id -u)/com.ewoolery.pixel-bot.calendar
```

Logs to `/tmp/pixel-cal.log` and `/tmp/pixel-cal.err`.

### ⚠️ The Calendar-permission (TCC) catch

macOS Calendar access is **per-app**. Granting it to your *Terminal* (by running
`icalBuddy calendars` once and clicking Allow) does **not** grant it to a
background **launchd** job — that's a different responsible process. So the
LaunchAgent may be denied even though it works in your Terminal.

- On the agent's first run while you're logged in, macOS *may* prompt for Calendar
  access — click **Allow**.
- If no prompt appears and the tile never shows real events, check
  `/tmp/pixel-cal.err`. The background job didn't get access.
- Reliable fallback when TCC won't cooperate: read events via the **Google
  Calendar API** (OAuth once) instead of icalBuddy — no TCC dependency. The tile
  and device code stay identical; only the event source changes.
