#!/usr/bin/env python3
"""
mock_awtrix.py — a browser stand-in for a Ulanzi TC001 running AWTRIX 3.

Implements just enough of the AWTRIX HTTP API for this project and renders a
32x8 LED matrix in the browser. `pixel_bot.py` drives it UNCHANGED — point
AWTRIX_IP at this server and everything works exactly as it will on hardware:

    # terminal 1
    python3 tools/mock_awtrix.py                       # serves http://localhost:7777

    # terminal 2
    AWTRIX_IP=localhost:7777 python3 pixel_bot.py test        # wave for ~4s
    AWTRIX_IP=localhost:7777 python3 pixel_bot.py attention   # start waving
    AWTRIX_IP=localhost:7777 python3 pixel_bot.py clear        # back to clock

You can also wire your real Claude Code hooks to it: set AWTRIX_IP=localhost:7777
in hooks/pixel-bot.sh and watch the browser react to actual notifications.

Stdlib only.
"""
import json
import os
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT = int(os.environ.get("MOCK_AWTRIX_PORT", "7777"))

# Shared display state. draw=None means idle -> show the clock.
STATE = {"draw": None, "updated": 0.0}

# ─── a tiny 3x5 pixel font so the idle "clock" looks like the real thing ─────
FONT = {
    "0": ["###", "# #", "# #", "# #", "###"],
    "1": [" # ", "## ", " # ", " # ", "###"],
    "2": ["###", "  #", "###", "#  ", "###"],
    "3": ["###", "  #", "###", "  #", "###"],
    "4": ["# #", "# #", "###", "  #", "  #"],
    "5": ["###", "#  ", "###", "  #", "###"],
    "6": ["###", "#  ", "###", "# #", "###"],
    "7": ["###", "  #", "  #", "  #", "  #"],
    "8": ["###", "# #", "###", "# #", "###"],
    "9": ["###", "# #", "###", "  #", "###"],
    ":": [" ", "#", " ", "#", " "],
}
CLOCK_COLOR = "#9FB4C7"


def clock_frame():
    """Render HH:MM as lit pixels, centred on the 32x8 matrix."""
    txt = time.strftime("%H:%M")
    glyphs = [FONT[c] for c in txt]
    total_w = sum(len(g[0]) for g in glyphs) + (len(glyphs) - 1)  # 1px gaps
    x0 = (32 - total_w) // 2
    y0 = (8 - 5) // 2
    pixels, x = [], x0
    for g in glyphs:
        w = len(g[0])
        for ry in range(5):
            for rx in range(w):
                if g[ry][rx] == "#":
                    pixels.append([x + rx, y0 + ry, CLOCK_COLOR])
        x += w + 1
    return pixels


def current_frame():
    if STATE["draw"]:
        # Notify frames arrive as AWTRIX draw commands ([{"dp":[x,y,c]}, ...]);
        # the page renderer wants bare [x, y, c] pixels, same as the clock.
        pixels = []
        for cmd in STATE["draw"]:
            if isinstance(cmd, dict) and "dp" in cmd:
                pixels.append(cmd["dp"])
            elif isinstance(cmd, (list, tuple)):
                pixels.append(list(cmd))
        return {"draw": pixels, "idle": False}
    return {"draw": clock_frame(), "idle": True}


PAGE = """<!doctype html><html><head><meta charset=utf-8>
<title>Ulanzi TC001 — simulator</title>
<style>
 :root{color-scheme:dark}
 body{margin:0;min-height:100vh;display:flex;flex-direction:column;
   align-items:center;justify-content:center;gap:18px;
   background:#0d0f12;font:14px/1.4 -apple-system,system-ui,sans-serif;color:#8b95a1}
 .device{background:#1b1e24;border:1px solid #2b2f37;border-radius:16px;
   padding:22px;box-shadow:0 12px 40px #0008, inset 0 1px 0 #ffffff08}
 canvas{display:block;background:#000;border-radius:6px;image-rendering:pixelated}
 .row{display:flex;gap:10px;align-items:center}
 .dot{width:8px;height:8px;border-radius:50%;background:#3a4150;transition:.2s}
 .dot.live{background:#37d67a;box-shadow:0 0 8px #37d67a}
 .label{letter-spacing:.14em;text-transform:uppercase;font-size:11px}
 code{background:#20242b;padding:2px 6px;border-radius:5px;color:#c7d0da}
</style></head><body>
 <div class=device><canvas id=m width=512 height=128></canvas></div>
 <div class=row><span class=dot id=beat></span>
   <span class=label id=status>connecting…</span></div>
 <div class=label>drive it: <code>AWTRIX_IP=localhost:__PORT__ python3 pixel_bot.py attention</code></div>
<script>
const W=32,H=8,S=16,cv=document.getElementById('m'),cx=cv.getContext('2d');
const beat=document.getElementById('beat'),status=document.getElementById('status');
function paint(frame,idle){
  cx.fillStyle='#000';cx.fillRect(0,0,cv.width,cv.height);
  // unlit LED grid
  for(let y=0;y<H;y++)for(let x=0;x<W;x++){
    cx.fillStyle='#0c0c0c';
    cx.beginPath();cx.arc(x*S+S/2,y*S+S/2,S*0.32,0,7);cx.fill();
  }
  for(const [x,y,c] of frame){
    cx.fillStyle=c;cx.shadowColor=c;cx.shadowBlur=8;
    cx.beginPath();cx.arc(x*S+S/2,y*S+S/2,S*0.40,0,7);cx.fill();cx.shadowBlur=0;
  }
  status.textContent = idle ? 'idle — clock' : 'NOTIFICATION — waving';
  status.style.color = idle ? '#8b95a1' : '#ffb454';
}
let on=false;
async function tick(){
  try{
    const r=await fetch('/state',{cache:'no-store'});
    const j=await r.json();
    paint(j.draw,j.idle);
    on=!on;beat.classList.toggle('live',on);
  }catch(e){ status.textContent='server offline'; }
}
setInterval(tick,80);tick();
</script></body></html>"""


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass  # quiet

    def _send(self, code, body, ctype="application/json"):
        data = body.encode() if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path == "/" or self.path.startswith("/index"):
            self._send(200, PAGE.replace("__PORT__", str(PORT)), "text/html; charset=utf-8")
        elif self.path == "/state":
            self._send(200, json.dumps(current_frame()))
        elif self.path.startswith("/api/stats"):
            self._send(200, json.dumps({
                "bat": 100, "bat_raw": 4200, "ram": 120000,
                "uptime": int(time.time()), "wifi_signal": -55, "type": 0,
            }))
        else:
            self._send(404, json.dumps({"error": "not found"}))

    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0) or 0)
        raw = self.rfile.read(n) if n else b""
        try:
            payload = json.loads(raw) if raw else {}
        except Exception:
            payload = {}

        if self.path.startswith("/api/notify/dismiss"):
            STATE["draw"] = None
        elif self.path.startswith("/api/notify"):
            STATE["draw"] = payload.get("draw") or None
            STATE["updated"] = time.time()
        # everything else (power, settings, indicators, custom, switch) is a no-op 200
        self._send(200, json.dumps({"success": True}))


def main():
    srv = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    print("mock AWTRIX at http://localhost:%d  (Ctrl-C to stop)" % PORT)
    print("drive it with:  AWTRIX_IP=localhost:%d python3 pixel_bot.py attention" % PORT)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        srv.shutdown()


if __name__ == "__main__":
    main()
