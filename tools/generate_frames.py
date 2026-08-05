#!/usr/bin/env python3
"""
generate_frames.py — build the waving-robot animation.

Outputs two artifacts, both committed to the repo:
  * frames.json           the baked animation the runtime plays (stdlib-only
                          player reads this; no Pillow needed at runtime)
  * preview/robot-wave.gif a 16x-scaled preview of the animation

Run this only when changing the character or the wave. Needs Pillow:
    pip install Pillow
    python tools/generate_frames.py

Character is derived from robot-v2.bmp (32x8): a box-bot with an antenna,
two amber eyes, both legs, a static left claw-arm, and a right arm that
waves. Drawn light-on-black so it reads as a glowing robot on the LEDs.
"""
import json
import os

W, H = 32, 8

# ─── palette ────────────────────────────────────────────────────────────────
BODY       = "#EBEBF5"      # near-white robot (hand included)
EYE_OPEN   = "#FF9500"      # amber
EYE_DIM    = "#784600"      # eased blink step
EYE_CLOSED = None           # eyes off (blink)

# ─── static body: everything except the RIGHT arm, which animates ───────────
static = set()
static |= {(15, 0)}                              # antenna
static |= {(x, 1) for x in range(11, 20)}        # head top
static |= {(11, 2), (20, 2)}                     # head walls
static |= {(11, 3), (20, 3)}                     # row-3 walls
static |= {(11, 5), (20, 5)}                     # body walls
static |= {(x, 6) for x in range(11, 20)}        # body bottom
static |= {(13, 7), (17, 7)}                     # legs
static |= {(6, 3), (7, 3),                       # left claw: top prong
           (8, 4), (9, 4), (10, 4),              # left arm
           (7, 5), (8, 5)}                       # left claw: bottom prong

eyes = [(13, 3), (17, 3)]

# ─── right-arm poses (the wave), each with a two-prong claw at the tip ───────
arm_out = {(24, 3), (25, 3),                     # top prong (mirrors left claw)
           (21, 4), (22, 4), (23, 4),            # arm
           (23, 5), (24, 5)}                     # bottom prong
arm_mid = {(21, 4), (22, 3), (23, 2),            # arm rising + wrist
           (22, 1), (24, 1)}                     # claw prongs (gap at 23,1)
arm_upA = {(21, 3), (22, 2), (23, 1),            # arm up + wrist
           (22, 0), (24, 0)}                     # claw prongs, rocked left
arm_upB = {(21, 3), (22, 2), (24, 1),            # arm up + wrist (shifted right)
           (23, 0), (25, 0)}                     # claw prongs, rocked right

wave = [arm_out, arm_mid, arm_upA, arm_upB, arm_upA, arm_upB, arm_mid, arm_out]

# Two wave cycles per loop with ONE slow, eased blink — gentle, not frantic.
sequence = []                                    # (arm pixels, eye colour)
for cyc in range(2):
    for i, arm in enumerate(wave):
        eye = EYE_OPEN
        if cyc == 1:
            if i == 5:   eye = EYE_DIM
            elif i == 6: eye = EYE_CLOSED
            elif i == 7: eye = EYE_DIM
        sequence.append((arm, eye))


def frame_pixels(entry):
    """Return a frame as a list of [x, y, '#RRGGBB'] lit pixels."""
    arm, eye = entry
    px = {}
    for (x, y) in static:
        px[(x, y)] = BODY
    for (x, y) in arm:
        px[(x, y)] = BODY
    if eye is not None:
        for (x, y) in eyes:
            px[(x, y)] = eye
    return [[x, y, c] for (x, y), c in sorted(px.items())]


def main():
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    frames = [frame_pixels(e) for e in sequence]

    meta = {
        "width": W,
        "height": H,
        "frame_ms": 150,          # per-frame dwell; ~2.4 s per loop
        "frames": frames,
    }
    with open(os.path.join(here, "frames.json"), "w") as f:
        json.dump(meta, f, indent=1)
    print(f"wrote frames.json ({len(frames)} frames)")

    # Preview GIF (optional — only if Pillow is available).
    try:
        from PIL import Image
    except ImportError:
        print("Pillow not installed — skipped preview GIF")
        return

    imgs = []
    for fr in frames:
        img = Image.new("RGB", (W, H), (0, 0, 0))
        p = img.load()
        for x, y, c in fr:
            p[x, y] = tuple(int(c[i:i + 2], 16) for i in (1, 3, 5))
        imgs.append(img)

    scale = 16
    big = [im.resize((W * scale, H * scale), Image.NEAREST) for im in imgs]
    out = os.path.join(here, "preview", "robot-wave.gif")
    big[0].save(out, save_all=True, append_images=big[1:],
                duration=meta["frame_ms"], loop=0, disposal=2)
    print(f"wrote {os.path.relpath(out, here)}")


if __name__ == "__main__":
    main()
