#!/usr/bin/env python3
"""
and-desk  –  test_st7735.py
────────────────────────────────────────────────────────────────────────────────
Standalone test suite for the ST7735 (160×128 landscape) display.
Runs independently — does not require the ILI9341 to be connected.

Tests:
  A  –  Solid colour fills
  B  –  RGB gradient
  C  –  Shapes (rect, ellipse, line)
  D  –  Text rendering at multiple sizes
  E  –  Landscape boundary check (pixel corners)
  F  –  Checkerboard pattern (pixel accuracy)
  G  –  Scrolling banner
  H  –  and-desk status widget (ui.py render_st_status live preview)
  I  –  MADCTL orientation check (labelled arrows)

Run:
    python3 test_st7735.py
    python3 test_st7735.py --quick     # skips slow tests (scroll, gradient)
"""

import sys
import time
import threading
import RPi.GPIO as GPIO
import spidev
from PIL import Image, ImageDraw, ImageFont

# ── Args ──────────────────────────────────────────────────────────────────────
QUICK = "--quick" in sys.argv

# ── Pin config (BCM) ──────────────────────────────────────────────────────────
ST_CS  = 5
ST_DC  = 23
ST_RST = 4

# ── ST7735 dimensions ─────────────────────────────────────────────────────────
W, H = 160, 128

# ── SPI — standalone instance (not shared with ILI9341 during this test) ─────
_spi = spidev.SpiDev()
_spi.open(0, 0)
_spi.no_cs        = True
_spi.mode         = 0b00
_spi.max_speed_hz = 15_000_000

_lock = threading.Lock()

# ── GPIO ──────────────────────────────────────────────────────────────────────
GPIO.setwarnings(False)
GPIO.setmode(GPIO.BCM)
for pin in [ST_CS, ST_DC, ST_RST]:
    GPIO.setup(pin, GPIO.OUT, initial=GPIO.HIGH)


# ═══════════════════════════════════════════════════════════════════════════════
# LOW-LEVEL SPI
# ═══════════════════════════════════════════════════════════════════════════════

def _write(dc_mode, data):
    with _lock:
        GPIO.output(ST_DC, GPIO.HIGH if dc_mode else GPIO.LOW)
        GPIO.output(ST_CS, GPIO.LOW)
        for i in range(0, len(data), 4096):
            _spi.writebytes2(data[i:i + 4096])
        GPIO.output(ST_CS, GPIO.HIGH)

def _cmd(cmd, data=None):
    _write(False, [cmd])
    if data:
        _write(True, data)


# ═══════════════════════════════════════════════════════════════════════════════
# ST7735 INIT  (landscape 160×128, MADCTL 0x68)
# ═══════════════════════════════════════════════════════════════════════════════

def init_display():
    GPIO.output(ST_RST, GPIO.LOW);  time.sleep(0.1)
    GPIO.output(ST_RST, GPIO.HIGH); time.sleep(0.15)

    _cmd(0x01);              time.sleep(0.15)   # SW reset
    _cmd(0x11);              time.sleep(0.5)    # sleep out
    _cmd(0xB1, [0x01, 0x2C, 0x2D])             # frame rate normal
    _cmd(0xB4, [0x07])                          # display inversion off
    _cmd(0xC0, [0xA2, 0x02, 0x84])             # power control 1
    _cmd(0xC1, [0xC5])                          # power control 2
    _cmd(0xC2, [0x0A, 0x00])                    # power control 3
    _cmd(0xC5, [0x8A, 0x2A])                    # VCOM control
    _cmd(0x3A, [0x05])                          # pixel format RGB565
    _cmd(0x36, [0x68])                          # MADCTL: MV+MX+BGR → landscape
    _cmd(0xE0, [0x02, 0x1C, 0x07, 0x12, 0x37, 0x32, 0x29, 0x2D,
                0x29, 0x25, 0x2B, 0x39, 0x00, 0x01, 0x03, 0x10])
    _cmd(0xE1, [0x03, 0x1D, 0x07, 0x06, 0x2E, 0x2C, 0x29, 0x2D,
                0x2E, 0x2E, 0x37, 0x3F, 0x00, 0x00, 0x02, 0x10])
    _cmd(0x13);              time.sleep(0.01)   # normal display on
    _cmd(0x29);              time.sleep(0.1)    # display on
    print("[ST7735] init OK  –  landscape 160×128")


# ═══════════════════════════════════════════════════════════════════════════════
# FRAME PUSH
# ═══════════════════════════════════════════════════════════════════════════════

def show(img):
    """Convert a Pillow RGB image to RGB565 and push to the display."""
    if img.size != (W, H):
        img = img.resize((W, H))
    if img.mode != 'RGB':
        img = img.convert('RGB')

    # Set window — full screen
    _cmd(0x2A, [0x00, 0x00, 0x00, W - 1])
    _cmd(0x2B, [0x00, 0x00, 0x00, H - 1])
    _cmd(0x2C)

    raw = img.tobytes()
    buf = bytearray(W * H * 2)
    for i in range(W * H):
        r, g, b = raw[i * 3], raw[i * 3 + 1], raw[i * 3 + 2]
        c = ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)
        buf[i * 2]     = c >> 8
        buf[i * 2 + 1] = c & 0xFF
    _write(True, buf)


# ═══════════════════════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════════════════════

def canvas(bg=(0, 0, 0)):
    return Image.new("RGB", (W, H), bg)

def fnt(size=11, bold=False):
    name = "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"
    try:
        return ImageFont.truetype(
            f"/usr/share/fonts/truetype/dejavu/{name}", size)
    except Exception:
        return ImageFont.load_default()

def pause(long=1.5, short=0.8):
    time.sleep(short if QUICK else long)

PASS = "PASS"
FAIL = "FAIL"
results = []

def run(label, fn):
    print(f"  [{label}] running...", end=" ", flush=True)
    try:
        fn()
        results.append((label, PASS))
        print("PASS")
    except Exception as e:
        results.append((label, FAIL))
        print(f"FAIL  →  {e}")


# ═══════════════════════════════════════════════════════════════════════════════
# TEST A  –  SOLID COLOUR FILLS
# ═══════════════════════════════════════════════════════════════════════════════

def test_colour_fills():
    colours = [
        ("RED",     (255,   0,   0)),
        ("GREEN",   (  0, 255,   0)),
        ("BLUE",    (  0,   0, 255)),
        ("CYAN",    (  0, 220, 255)),
        ("MAGENTA", (220,   0, 200)),
        ("YELLOW",  (240, 200,   0)),
        ("WHITE",   (255, 255, 255)),
        ("BLACK",   (  0,   0,   0)),
    ]
    for name, rgb in colours:
        img = canvas(rgb)
        draw = ImageDraw.Draw(img)
        draw.text((4, 4), name, font=fnt(12, bold=True),
                  fill=(0, 0, 0) if rgb == (255, 255, 255) else (255, 255, 255))
        show(img)
        pause(0.6, 0.4)


# ═══════════════════════════════════════════════════════════════════════════════
# TEST B  –  RGB GRADIENT
# ═══════════════════════════════════════════════════════════════════════════════

def test_gradient():
    img = canvas()
    px  = img.load()
    for y in range(H):
        for x in range(W):
            px[x, y] = (
                int(x / W * 255),
                int(y / H * 255),
                128,
            )
    show(img)
    pause(2.0, 1.0)


# ═══════════════════════════════════════════════════════════════════════════════
# TEST C  –  SHAPES
# ═══════════════════════════════════════════════════════════════════════════════

def test_shapes():
    img  = canvas((8, 9, 14))
    draw = ImageDraw.Draw(img)

    # Filled rectangles
    draw.rectangle([4,   4,  74,  40], fill=(255, 60,  60))
    draw.rectangle([80,  4, 156,  40], fill=( 60, 60, 255))

    # Outlined rectangle
    draw.rectangle([4,  48, 156,  80], outline=(0, 220, 255), width=2)

    # Ellipse
    draw.ellipse([10, 88, 90, 124], outline=(0, 210, 120), width=2)

    # Diagonal line
    draw.line([(100, 88), (155, 124)], fill=(240, 190, 0), width=2)

    # Labels
    draw.text((8,  12), "rect",    font=fnt(10, True), fill=(255, 255, 255))
    draw.text((84, 12), "rect",    font=fnt(10, True), fill=(255, 255, 255))
    draw.text((8,  55), "outline", font=fnt(9),        fill=(0, 220, 255))
    draw.text((8,  93), "ellipse", font=fnt(9),        fill=(0, 210, 120))
    draw.text((102,93), "line",    font=fnt(9),        fill=(240, 190, 0))

    show(img)
    pause(2.5, 1.5)


# ═══════════════════════════════════════════════════════════════════════════════
# TEST D  –  TEXT RENDERING
# ═══════════════════════════════════════════════════════════════════════════════

def test_text():
    img  = canvas((8, 9, 14))
    draw = ImageDraw.Draw(img)

    draw.text(( 4,  4), "Size 8 regular",  font=fnt(8),       fill=(150, 155, 165))
    draw.text(( 4, 16), "Size 9 regular",  font=fnt(9),       fill=(180, 185, 195))
    draw.text(( 4, 29), "Size 10 regular", font=fnt(10),      fill=(200, 205, 215))
    draw.text(( 4, 43), "Size 11 BOLD",    font=fnt(11, True),fill=(210, 215, 225))
    draw.text(( 4, 60), "Size 13 BOLD",    font=fnt(13, True),fill=(0, 210, 240))
    draw.text(( 4, 80), "20 BOLD",         font=fnt(20, True),fill=(255, 130, 40))
    draw.text(( 4,106), "ST7735  160x128", font=fnt(9),       fill=(85, 95, 115))

    show(img)
    pause(3.0, 2.0)


# ═══════════════════════════════════════════════════════════════════════════════
# TEST E  –  BOUNDARY CHECK (corner pixels)
# ═══════════════════════════════════════════════════════════════════════════════

def test_boundary():
    """
    Draws a 1px border around the full perimeter and marks each corner
    with a 4×4 coloured square. If any corner is cut off, the display
    window or offset is misconfigured.
    """
    img  = canvas((8, 9, 14))
    draw = ImageDraw.Draw(img)

    # Full perimeter
    draw.rectangle([0, 0, W - 1, H - 1], outline=(0, 220, 255), width=1)

    # Corner squares  (4×4)
    draw.rectangle([0,     0,      4,     4    ], fill=(255,  80,  80))  # TL red
    draw.rectangle([W - 5, 0,      W - 1, 4    ], fill=(255, 200,   0))  # TR yellow
    draw.rectangle([0,     H - 5,  4,     H - 1], fill=(  0, 210, 120))  # BL green
    draw.rectangle([W - 5, H - 5,  W - 1, H - 1], fill=(  0, 180, 255)) # BR cyan

    # Labels
    draw.text(( 7,  2), "TL",       font=fnt(9),       fill=(255,  80,  80))
    draw.text((W-28, 2), "TR",      font=fnt(9),       fill=(255, 200,   0))
    draw.text(( 7, H-12), "BL",     font=fnt(9),       fill=(  0, 210, 120))
    draw.text((W-28, H-12), "BR",   font=fnt(9),       fill=(  0, 180, 255))

    # Centre crosshair
    cx, cy = W // 2, H // 2
    draw.line([(cx - 8, cy), (cx + 8, cy)], fill=(100, 110, 130), width=1)
    draw.line([(cx, cy - 8), (cx, cy + 8)], fill=(100, 110, 130), width=1)
    draw.text((cx + 4, cy + 2), "centre", font=fnt(8), fill=(85, 95, 115))

    show(img)
    pause(3.0, 2.0)


# ═══════════════════════════════════════════════════════════════════════════════
# TEST F  –  CHECKERBOARD  (pixel accuracy)
# ═══════════════════════════════════════════════════════════════════════════════

def test_checkerboard():
    """
    8×8 pixel checkerboard — reveals sub-pixel bleed, row offset errors,
    or RGB565 colour channel bleed.
    """
    img = canvas()
    px  = img.load()
    A   = (0, 210, 240)    # cyan
    B   = (14, 16, 22)     # near-black
    SZ  = 8
    for y in range(H):
        for x in range(W):
            px[x, y] = A if ((x // SZ + y // SZ) % 2 == 0) else B

    draw = ImageDraw.Draw(img)
    draw.text((4, 4), "pixel check", font=fnt(9, True), fill=(255, 255, 255))

    show(img)
    pause(2.0, 1.0)


# ═══════════════════════════════════════════════════════════════════════════════
# TEST G  –  SCROLLING BANNER
# ═══════════════════════════════════════════════════════════════════════════════

def test_scroll():
    msg   = "  ST7735  160×128  landscape  OK  ·  and-desk  ·  "
    f     = fnt(14, bold=True)
    tmp   = Image.new("RGB", (1, 1))
    bb    = ImageDraw.Draw(tmp).textbbox((0, 0), msg, font=f)
    msg_w = bb[2] - bb[0]

    strip_w = msg_w + W
    strip   = Image.new("RGB", (strip_w, 20), (8, 9, 14))
    ImageDraw.Draw(strip).text((W, 2), msg, font=f, fill=(0, 210, 240))

    end    = time.time() + (4 if QUICK else 7)
    offset = 0
    bg     = (8, 9, 14)

    while time.time() < end:
        frame = canvas(bg)
        frame.paste(strip.crop((offset, 0, offset + W, 20)), (0, H // 2 - 10))

        # Static label
        draw = ImageDraw.Draw(frame)
        draw.text((4, 4), "scroll test", font=fnt(9), fill=(85, 95, 115))

        show(frame)
        offset = (offset + 3) % strip_w
        time.sleep(0.03)


# ═══════════════════════════════════════════════════════════════════════════════
# TEST H  –  LIVE STATUS WIDGET  (ui.py render_st_status)
# ═══════════════════════════════════════════════════════════════════════════════

def test_status_widget():
    """Render the real and-desk ST7735 status widget with sample data."""
    try:
        from ui import render_st_status
    except ImportError:
        raise RuntimeError("ui.py not found — place test_st7735.py in the same folder")

    sample = {
        "deck": {
            "cpu": 38, "fan": 28,
            "disk_used": 42, "disk_total": 64, "ram": 31,
        },
        "server": {
            "cpu": 55, "gpu": 12,
            "disk_used": 260, "disk_total": 500, "ram": 74,
        },
        "weather": {
            "icon": "~", "temp_hi": 24, "temp_lo": 15, "online": True,
        },
        "deck_online":   True,
        "server_online": True,
    }

    img = render_st_status(sample)
    show(img)
    pause(4.0, 3.0)


# ═══════════════════════════════════════════════════════════════════════════════
# TEST I  –  ORIENTATION CHECK
# ═══════════════════════════════════════════════════════════════════════════════

def test_orientation():
    """
    Draws labelled arrows at each edge so you can confirm the display
    is the right way up and not mirrored.
    Expected:  TOP label at physical top, LEFT label at physical left.
    If wrong → adjust MADCTL byte in display_driver.py / init_display().
    """
    img  = canvas((8, 9, 14))
    draw = ImageDraw.Draw(img)

    BF = fnt(10, bold=True)
    SF = fnt(9)
    C  = (0, 210, 240)

    # TOP arrow ↓
    draw.text((W // 2 - 14, 4),    "TOP",   font=BF, fill=C)
    draw.line([(W // 2, 18), (W // 2, 28)], fill=C, width=2)
    draw.polygon([(W//2 - 4, 24), (W//2 + 4, 24), (W//2, 30)], fill=C)

    # BOTTOM arrow ↑
    draw.text((W // 2 - 20, H - 16), "BOTTOM", font=BF, fill=(0, 210, 120))
    draw.line([(W // 2, H - 20), (W // 2, H - 30)], fill=(0, 210, 120), width=2)
    draw.polygon([(W//2 - 4, H-26), (W//2 + 4, H-26), (W//2, H-32)], fill=(0, 210, 120))

    # LEFT arrow →
    draw.text((3, H // 2 - 6), "L", font=BF, fill=(255, 130, 40))
    draw.line([(14, H // 2), (24, H // 2)], fill=(255, 130, 40), width=2)
    draw.polygon([(20, H//2 - 4), (20, H//2 + 4), (26, H//2)], fill=(255, 130, 40))

    # RIGHT arrow ←
    draw.text((W - 12, H // 2 - 6), "R", font=BF, fill=(220, 60, 200))
    draw.line([(W - 15, H // 2), (W - 25, H // 2)], fill=(220, 60, 200), width=2)
    draw.polygon([(W-21, H//2 - 4), (W-21, H//2 + 4), (W-27, H//2)], fill=(220, 60, 200))

    # Centre label
    draw.text((W // 2 - 30, H // 2 - 5),
              "MADCTL", font=SF, fill=(85, 95, 115))
    draw.text((W // 2 - 16, H // 2 + 4),
              "0x68",   font=BF, fill=(85, 95, 115))

    show(img)
    pause(4.0, 3.0)


# ═══════════════════════════════════════════════════════════════════════════════
# SUMMARY SCREEN
# ═══════════════════════════════════════════════════════════════════════════════

def show_summary():
    img  = canvas((8, 9, 14))
    draw = ImageDraw.Draw(img)

    passed = sum(1 for _, s in results if s == PASS)
    total  = len(results)

    # Header
    draw.text((4, 4), "ST7735  results", font=fnt(10, bold=True),
              fill=(0, 210, 240))
    draw.line([(0, 18), (W, 18)], fill=(26, 30, 40), width=1)

    # Score
    score_col = (0, 210, 120) if passed == total else (255, 130, 40)
    draw.text((4, 22), f"{passed}/{total} passed",
              font=fnt(11, bold=True), fill=score_col)

    # Per-test rows
    y = 38
    for label, status in results:
        col = (0, 210, 120) if status == PASS else (220, 60, 60)
        draw.text((4,   y), label,  font=fnt(9),          fill=(150, 155, 165))
        draw.text((120, y), status, font=fnt(9, bold=True), fill=col)
        y += 13

    show(img)
    time.sleep(5)


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    print("=" * 50)
    print("  ST7735  160×128  –  and-desk test suite")
    if QUICK:
        print("  mode: --quick")
    print("=" * 50)

    init_display()

    print()
    run("A  colour fills",   test_colour_fills)
    run("B  gradient",       test_gradient)
    run("C  shapes",         test_shapes)
    run("D  text",           test_text)
    run("E  boundary",       test_boundary)
    run("F  checkerboard",   test_checkerboard)
    run("G  scroll",         test_scroll)
    run("H  status widget",  test_status_widget)
    run("I  orientation",    test_orientation)

    print()
    show_summary()

    passed = sum(1 for _, s in results if s == PASS)
    total  = len(results)
    print(f"\n[done]  {passed}/{total} passed.\n")

    _spi.close()
    GPIO.cleanup()


if __name__ == "__main__":
    main()
