#!/usr/bin/env python3
"""
pixel_bot.py — stream a waving-robot animation to a Ulanzi TC001 running
AWTRIX 3, so the display waves when Claude Code needs attention.

Stdlib only — no third-party packages, no venv. The animation is read from
frames.json (baked by tools/generate_frames.py).

Commands:
    pixel_bot.py attention   start the wave immediately (spawns a detached loop)
    pixel_bot.py arm         start an idle countdown; wave only if not cancelled
    pixel_bot.py clear       stop wave/countdown, hand the screen back to the clock
    pixel_bot.py test        check reachability, then wave for a few seconds
    pixel_bot.py play        internal: the foreground frame-push loop
    pixel_bot.py armed       internal: idle countdown then wave

Two ways to wire it up (both use events that fire reliably, unlike Notification):

  A) Approval detector (v1.2 — waves only when Claude needs your input):
       PreToolUse       -> tool-arm     (a tool started)
       PostToolUse      -> tool-cancel  (it finished → wasn't blocked)
       UserPromptSubmit -> clear
       Stop             -> clear
     A tool that doesn't finish within PIXEL_BOT_TOOL_DELAY is assumed blocked on
     your approval, so the robot waves. Plain end-of-turn messages never wave.

  B) Idle notifier (simpler; waves after any quiet spell):
       Stop             -> arm
       UserPromptSubmit -> clear
     Waves if you don't reply within PIXEL_BOT_IDLE_DELAY seconds.

Config via environment (all optional except the IP):
    AWTRIX_IP            device IP on your LAN            (required in practice)
    PIXEL_BOT_TIMEOUT    per-request timeout, seconds     (default 2)
    PIXEL_BOT_PIDFILE    player pidfile path              (default /tmp/claude-pixel-bot.pid)
    PIXEL_BOT_IDLE_DELAY seconds idle before an armed (idle) wave fires (default 30)
    PIXEL_BOT_TOOL_DELAY seconds a tool may run before we assume it's blocked (default 5)
    PIXEL_BOT_FRAMES     path to frames.json              (default: alongside this file)

The full-width robot is host-driven: AWTRIX plays animated GIFs only in an
8x8 icon slot, so a 32x8 character has to be streamed frame by frame. This
is a LAN HTTP loop — sub-second, cheap, self-healing (if the player dies the
notification's duration lapses and the clock returns on its own).

NOTE ON HOOK EXIT CODES: the hook wrapper (hooks/pixel-bot.sh) always exits 0.
On Claude Code's Stop event, exit code 2 tells Claude *not* to stop and to
continue the conversation — an unreachable display must never be able to
trap a session. This script never influences that; the wrapper guarantees it.
"""
import json
import os
import signal
import subprocess
import sys
import time
import urllib.request

IP       = os.environ.get("AWTRIX_IP", "192.168.1.50")
TIMEOUT  = float(os.environ.get("PIXEL_BOT_TIMEOUT", "2"))
PIDFILE  = os.environ.get("PIXEL_BOT_PIDFILE", "/tmp/claude-pixel-bot.pid")
TIMER_PIDFILE = PIDFILE + ".armed"                               # idle-countdown process
TOOL_PIDFILE  = PIDFILE + ".tool"                                # tool-blocked-countdown process
IDLE_DELAY = float(os.environ.get("PIXEL_BOT_IDLE_DELAY", "30"))  # seconds before an armed idle wave fires
TOOL_DELAY = float(os.environ.get("PIXEL_BOT_TOOL_DELAY", "5"))   # seconds a tool may run before we assume it's blocked on approval
FRAMES   = os.environ.get(
    "PIXEL_BOT_FRAMES",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "frames.json"),
)
BASE = "http://%s/api" % IP


# ─── HTTP ────────────────────────────────────────────────────────────────────
def post(endpoint, payload=None):
    """POST JSON to an AWTRIX endpoint. Best-effort: never raises."""
    url = "%s/%s" % (BASE, endpoint)
    data = json.dumps(payload).encode() if payload is not None else b""
    req = urllib.request.Request(
        url, data=data, method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT):
            return True
    except Exception:
        return False


def get(endpoint):
    try:
        with urllib.request.urlopen("%s/%s" % (BASE, endpoint), timeout=TIMEOUT) as r:
            return r.read().decode("utf-8", "replace")
    except Exception:
        return None


# ─── frames ──────────────────────────────────────────────────────────────────
def load_frames():
    with open(FRAMES) as f:
        meta = json.load(f)
    draw_frames = [
        [{"dp": [x, y, c]} for x, y, c in frame]
        for frame in meta["frames"]
    ]
    return draw_frames, meta.get("frame_ms", 150) / 1000.0


def frame_payload(draw, wakeup):
    # No hold: if the player stops pushing, the notification's duration lapses
    # and the clock returns on its own. duration comfortably exceeds the
    # inter-frame gap so the animation never flickers back to the clock.
    return {
        "draw": draw,
        "duration": 2,
        "noScroll": True,
        "stack": False,
        "wakeup": wakeup,
    }


# ─── pidfile helpers ─────────────────────────────────────────────────────────
def read_pid(path=PIDFILE):
    try:
        with open(path) as f:
            return int(f.read().strip())
    except Exception:
        return None


def alive(pid):
    if not pid:
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def kill_pidfile(path):
    """SIGTERM the process a pidfile points to (if alive) and remove the file."""
    pid = read_pid(path)
    if alive(pid):
        try:
            os.kill(pid, signal.SIGTERM)
        except OSError:
            pass
        for _ in range(20):            # up to ~1s for it to exit
            if not alive(pid):
                break
            time.sleep(0.05)
    try:
        os.remove(path)
    except OSError:
        pass


def spawn_detached(arg, pidfile):
    """Launch this script with `arg` as a detached background process."""
    devnull = open(os.devnull, "wb")
    proc = subprocess.Popen(
        [sys.executable, os.path.abspath(__file__), arg],
        stdin=subprocess.DEVNULL, stdout=devnull, stderr=devnull,
        start_new_session=True,   # survive the hook process exiting
    )
    try:
        with open(pidfile, "w") as f:
            f.write(str(proc.pid))
    except Exception:
        pass


# ─── commands ────────────────────────────────────────────────────────────────
def _install_stop_flag():
    """Return a callable that reports whether SIGTERM/SIGINT has been received."""
    state = {"go": True}

    def _stop(_sig, _frm):
        state["go"] = False

    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    return lambda: state["go"]


def _wave_until(running):
    """Push frames until `running()` goes False, then leave the screen clean."""
    frames, dwell = load_frames()
    i = 0
    while running():
        post("notify", frame_payload(frames[i % len(frames)], wakeup=(i == 0)))
        i += 1
        time.sleep(dwell)
    post("notify/dismiss")


def _sleep_until(running, seconds):
    """Interruptible sleep; returns True if it slept the full time, False if stopped."""
    end = time.time() + seconds
    while running() and time.time() < end:
        time.sleep(0.25)
    return running()


def cmd_play():
    """Foreground loop: wave until SIGTERM/SIGINT."""
    _wave_until(_install_stop_flag())


def _countdown_then_wave(delay):
    """Wait `delay` seconds; if not killed first, wave. Killable at any stage."""
    running = _install_stop_flag()
    if _sleep_until(running, delay):   # survived the full delay → fire
        _wave_until(running)
    else:
        post("notify/dismiss")         # cancelled during countdown; nothing was shown


def cmd_armed():
    """Idle countdown then wave (Stop-based idle notifier)."""
    _countdown_then_wave(IDLE_DELAY)


def cmd_tool_armed():
    """Tool countdown then wave — fires if a tool doesn't finish within TOOL_DELAY,
    which in 'ask' mode means Claude is blocked waiting for your approval."""
    _countdown_then_wave(TOOL_DELAY)


def cmd_attention():
    """Start the wave immediately if not already running (idempotent)."""
    if alive(read_pid()):
        return
    spawn_detached("play", PIDFILE)


def cmd_arm():
    """(Re)start the idle countdown. Each call resets the timer to IDLE_DELAY."""
    kill_pidfile(TIMER_PIDFILE)              # restart the countdown on every turn end
    spawn_detached("armed", TIMER_PIDFILE)


def cmd_tool_arm():
    """(Re)start the tool countdown on PreToolUse. Reset each time a tool starts."""
    kill_pidfile(TOOL_PIDFILE)
    spawn_detached("tool-armed", TOOL_PIDFILE)


def cmd_tool_cancel():
    """PostToolUse: the tool finished, so it wasn't blocked — cancel its countdown
    and cut any wave it may have started."""
    kill_pidfile(TOOL_PIDFILE)
    post("notify/dismiss")


def cmd_clear():
    """Stop everything — any pending countdown and any active wave — to the clock."""
    kill_pidfile(TIMER_PIDFILE)   # cancel a pending idle countdown
    kill_pidfile(TOOL_PIDFILE)    # cancel a pending tool countdown
    kill_pidfile(PIDFILE)         # stop an active wave
    # Belt and suspenders: cut any lingering notification immediately.
    post("notify/dismiss")


def cmd_test():
    print("Pinging AWTRIX at %s ..." % IP)
    stats = get("stats")
    if stats is None:
        print("FAILED — no response from %s." % IP, file=sys.stderr)
        print("Check: device on the same LAN, AWTRIX flashed, AWTRIX_IP correct.",
              file=sys.stderr)
        return 1
    print("OK — reachable:", stats[:200])
    print("Waving for ~4s ...")
    frames, dwell = load_frames()
    end = time.time() + 4
    i = 0
    while time.time() < end:
        post("notify", frame_payload(frames[i % len(frames)], wakeup=(i == 0)))
        i += 1
        time.sleep(dwell)
    post("notify/dismiss")
    print("Done.")
    return 0


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "play":
        cmd_play()
    elif cmd == "armed":
        cmd_armed()
    elif cmd == "tool-armed":
        cmd_tool_armed()
    elif cmd == "attention":
        cmd_attention()
    elif cmd == "arm":
        cmd_arm()
    elif cmd == "tool-arm":
        cmd_tool_arm()
    elif cmd == "tool-cancel":
        cmd_tool_cancel()
    elif cmd in ("clear", "stop"):
        cmd_clear()
    elif cmd == "test":
        return cmd_test()
    else:
        print("usage: pixel_bot.py <attention|arm|tool-arm|tool-cancel|clear|test>",
              file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
