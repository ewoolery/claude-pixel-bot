# Cheat sheet — pixel robot

Everything points at the device (`192.168.7.144`) and the installed script at
`~/.claude/pixel-bot/pixel_bot.py`. Set your own IP if it differs.

## Robot

**👋 Make it wave** (stays waving until cleared)
```bash
AWTRIX_IP=192.168.7.144 python3 ~/.claude/pixel-bot/pixel_bot.py attention
```

**🛑 Stop it / back to the clock**
```bash
AWTRIX_IP=192.168.7.144 python3 ~/.claude/pixel-bot/pixel_bot.py clear
```

**✅ Test** (pings the device, then waves ~4s and auto-clears)
```bash
AWTRIX_IP=192.168.7.144 python3 ~/.claude/pixel-bot/pixel_bot.py test
```

**📡 Is the device reachable?** (battery, firmware version, current app)
```bash
curl -s http://192.168.7.144/api/stats
```

**🧹 Panic button** — kill any stuck/stray wave loops, then clear
```bash
pkill -f 'pixel_bot.py (play|armed|tool-armed)'; AWTRIX_IP=192.168.7.144 python3 ~/.claude/pixel-bot/pixel_bot.py clear
```

## Shorter: add an alias (once)

Add to `~/.zshrc`:
```bash
echo 'export AWTRIX_IP=192.168.7.144' >> ~/.zshrc
echo 'alias pixelbot="python3 ~/.claude/pixel-bot/pixel_bot.py"' >> ~/.zshrc
```

Then, in a new terminal:
```bash
pixelbot test        # ping + short wave
pixelbot attention   # wave
pixelbot clear        # stop
```

## Calendar tile

**Refresh the next-meeting tile by hand**
```bash
AWTRIX_IP=192.168.7.144 python3 ~/.pixel-bot/calendar_tile.py update
```

**Remove the tile**
```bash
AWTRIX_IP=192.168.7.144 python3 ~/.pixel-bot/calendar_tile.py clear
```

## Control panel (web UI)

**Run the panel** (serves the UI + proxies the device API), then open http://localhost:8080
```bash
AWTRIX_IP=192.168.7.144 python3 ~/.claude/pixel-bot/panel/awtrix_panel.py
```
Toggle pages (Time/Date/Temp/Humidity/Battery), set dwell/scroll/transition/brightness,
watch the live screen mirror, wave the robot, send a message. Stop with `pkill -f awtrix_panel.py`.

For 24/7 it runs on a Pi via `deploy/awtrix-panel.service` (see the Control panel section in the README).

## Simulator (no hardware)

**Run the browser stand-in**, then open http://localhost:7777
```bash
python3 ~/.claude/pixel-bot/tools/mock_awtrix.py
```

Drive it by pointing the commands above at `localhost:7777` instead of the device
IP, e.g. `AWTRIX_IP=localhost:7777 python3 ~/.claude/pixel-bot/pixel_bot.py attention`.
Stop the simulator with `pkill -f mock_awtrix.py`.

## Hooks (auto-behavior)

- Config lives in `~/.claude/settings.json`; the wrapper is `~/.claude/hooks/pixel-bot.sh`.
- Diagnostic log (if `PIXEL_BOT_LOG` is set on the hook commands):
  ```bash
  tail -f ~/.claude/pixel-bot-hook.log
  ```
