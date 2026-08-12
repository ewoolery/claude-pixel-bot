#!/usr/bin/env python3
"""
awtrix_panel.py — LAN control panel for a Ulanzi TC001 running AWTRIX 3.

Why this exists: a browser page can't call the display's HTTP API directly
from another origin (no CORS headers on AWTRIX, and mixed content if the
page itself is served over HTTPS). This serves the panel AND proxies
/api/* to the device, so everything is same-origin and both problems
disappear.

Stdlib only — nothing to pip install.

    AWTRIX_IP=192.168.1.50 python3 awtrix_panel.py

Then open http://<pi-hostname>:8080 from any device on the LAN.
"""

import json
import os
import sys
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

AWTRIX_IP = os.environ.get("AWTRIX_IP", "192.168.1.50")
PORT = int(os.environ.get("PORT", "8080"))
BIND = os.environ.get("BIND", "0.0.0.0")
TIMEOUT = float(os.environ.get("AWTRIX_TIMEOUT", "3"))

HERE = os.path.dirname(os.path.abspath(__file__))
INDEX = os.path.join(HERE, "index.html")
FRAMES = os.path.join(HERE, "frames.json")


# ── robot wave (tie-in) ──────────────────────────────────────────────────
def _device_post(endpoint, payload=None):
    """POST to the display directly (used by the wave loop). Never raises."""
    url = "http://{}/api/{}".format(AWTRIX_IP, endpoint)
    data = json.dumps(payload).encode() if payload is not None else b""
    req = urllib.request.Request(url, data=data, method="POST")
    if data:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT):
            return True
    except Exception:
        return False


def _play_wave(seconds=4.0):
    """Stream the waving-robot animation from frames.json for a few seconds,
    then hand the screen back — same host-driven approach as pixel_bot.py."""
    try:
        with open(FRAMES) as fh:
            meta = json.load(fh)
        frames = [[{"dp": [x, y, c]} for x, y, c in fr] for fr in meta["frames"]]
        dwell = meta.get("frame_ms", 150) / 1000.0
    except Exception:
        return
    end = time.time() + seconds
    i = 0
    while time.time() < end:
        _device_post("notify", {"draw": frames[i % len(frames)], "duration": 2,
                                "noScroll": True, "stack": False, "wakeup": i == 0})
        i += 1
        time.sleep(dwell)
    _device_post("notify/dismiss")


class Handler(BaseHTTPRequestHandler):
    server_version = "awtrix-panel/1.0"

    # ── helpers ──────────────────────────────────────────────────────────
    def _send(self, status, body, ctype="application/json"):
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        try:
            self.wfile.write(body)
        except BrokenPipeError:
            pass

    def _err(self, status, message):
        self._send(status, json.dumps({"error": message}))

    def _index(self):
        try:
            with open(INDEX, "rb") as fh:
                self._send(200, fh.read(), "text/html; charset=utf-8")
        except FileNotFoundError:
            self._err(500, "index.html is missing from the panel directory")

    def _proxy(self, method):
        """Forward /api/... to the display verbatim, including query string."""
        url = "http://{}{}".format(AWTRIX_IP, self.path)

        body = None
        if method == "POST":
            length = int(self.headers.get("Content-Length") or 0)
            body = self.rfile.read(length) if length else b""

        req = urllib.request.Request(url, data=body, method=method)
        if body:
            req.add_header("Content-Type", "application/json")

        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
                payload = resp.read()
                ctype = resp.headers.get("Content-Type") or "application/json"
                # AWTRIX answers many POSTs with an empty 200.
                if not payload:
                    payload = b'{"ok":true}'
                    ctype = "application/json"
                self._send(resp.status, payload, ctype)

        except urllib.error.HTTPError as exc:
            payload = exc.read() or json.dumps(
                {"error": "device returned {}".format(exc.code)}
            ).encode()
            self._send(exc.code, payload)

        except urllib.error.URLError as exc:
            self._err(502, "can't reach {} — {}".format(AWTRIX_IP, exc.reason))

        except Exception as exc:  # noqa: BLE001 - proxy must never crash
            self._err(502, "proxy error — {}".format(exc))

    # ── routes ───────────────────────────────────────────────────────────
    def do_GET(self):
        if self.path in ("/", "/index.html"):
            self._index()
        elif self.path == "/panel/config":
            self._send(200, json.dumps({"device": AWTRIX_IP}))
        elif self.path.startswith("/api/"):
            self._proxy("GET")
        else:
            self._err(404, "no such path")

    def do_POST(self):
        if self.path == "/panel/wave":
            threading.Thread(target=_play_wave, daemon=True).start()
            self._send(200, json.dumps({"ok": True, "wave": "started"}))
        elif self.path.startswith("/api/"):
            self._proxy("POST")
        else:
            self._err(404, "no such path")

    def log_message(self, fmt, *args):
        # One tidy line per request; drop the noisy default format.
        sys.stderr.write("  {} {}\n".format(self.command, self.path))


def main():
    if not os.path.exists(INDEX):
        sys.exit("index.html not found next to {} — keep them together.".format(
            os.path.basename(__file__)))

    print("AWTRIX control panel")
    print("  display : http://{}".format(AWTRIX_IP))
    print("  panel   : http://{}:{}".format(BIND, PORT))
    print("  (set AWTRIX_IP / PORT via environment)\n")

    try:
        ThreadingHTTPServer((BIND, PORT), Handler).serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")


if __name__ == "__main__":
    main()
