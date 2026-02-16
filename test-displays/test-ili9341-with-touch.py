#!/usr/bin/env python3
"""
ILI9341 Display + Touch Interface Test
Raspberry Pi 4  –  SPI + XPT2046 touch
Compatible with adafruit-circuitpython-rgb-display (modern API)

Install:
    sudo pip3 install --break-system-packages \
        adafruit-circuitpython-rgb-display \
        pillow spidev RPi.GPIO

Enable SPI first:
    sudo raspi-config  →  Interface Options  →  SPI  →  Enable
"""

import time
import sys

# ── Graceful import checks ────────────────────────────────────────────────────
def require(pkg, install):
    import importlib
    try:
        return importlib.import_module(pkg)
    except ImportError:
        print(f"[ERROR] Missing '{pkg}'.  Run:  sudo pip3 install {install}")
        sys.exit(1)

require("board",                       "adafruit-blinka")
require("busio",                       "adafruit-blinka")
require("digitalio",                   "adafruit-blinka")
require("adafruit_rgb_display.ili9341","adafruit-circuitpython-rgb-display")
require("PIL",                         "pillow")

import board, busio, digitalio
import adafruit_rgb_display.ili9341 as ili9341
from PIL import Image, ImageDraw, ImageFont


# ── PIN CONFIGURATION  (BCM numbering) ───────────────────────────────────────
#  Display (ILI9341)
DISP_CS_PIN  = board.CE0    # GPIO  8  – Display Chip Select
DISP_DC_PIN  = board.D25    # GPIO 24  – Data / Command
DISP_RST_PIN = board.D24    # GPIO 25  – Reset
DISP_BL_PIN  = 18           # GPIO 18  – Backlight (BCM int for RPi.GPIO PWM)

#  Touch (XPT2046)
#  T_CD on your board = T_CS (chip select)
TOUCH_CS_BCM  = 7           # GPIO  7  – CE1  (T_CD / T_CS)
TOUCH_IRQ_BCM = 17          # GPIO 17  – T_IRQ
#  T_CLK → GPIO 11  (shared SPI clock  – board.SCK)
#  T_DIN → GPIO 10  (shared SPI MOSI   – board.MOSI)
#  T_DO  → GPIO  9  (shared SPI MISO   – board.MISO)

SCREEN_W = 240
SCREEN_H = 320
ROTATION = 0                # 0 / 90 / 180 / 270


# ── DISPLAY INIT ─────────────────────────────────────────────────────────────
def init_display():
    print("[DISPLAY] Initializing SPI bus...")
    spi = busio.SPI(clock=board.SCK, MOSI=board.MOSI, MISO=board.MISO)

    cs  = digitalio.DigitalInOut(DISP_CS_PIN)
    dc  = digitalio.DigitalInOut(DISP_DC_PIN)
    rst = digitalio.DigitalInOut(DISP_RST_PIN)

    print("[DISPLAY] Creating ILI9341 driver (adafruit_rgb_display)...")
    disp = ili9341.ILI9341(
        spi,
        cs=cs,
        dc=dc,
        rst=rst,
        width=SCREEN_W,
        height=SCREEN_H,
        rotation=ROTATION,
        baudrate=40_000_000,
    )
    print("[DISPLAY] OK – ILI9341 ready.")
    return disp


# ── TOUCH INIT ───────────────────────────────────────────────────────────────
def init_touch():
    try:
        import spidev
        import RPi.GPIO as GPIO
        GPIO.setwarnings(False)
        GPIO.setmode(GPIO.BCM)

        # CE1 (GPIO 7) manually controlled – keeps it HIGH (inactive) at start
        GPIO.setup(TOUCH_CS_BCM,  GPIO.OUT, initial=GPIO.HIGH)
        GPIO.setup(TOUCH_IRQ_BCM, GPIO.IN,  pull_up_down=GPIO.PUD_UP)

        # Open SPI bus 0 with no automatic CS (we drive CE1 manually above)
        t = spidev.SpiDev()
        t.open(0, 0)                  # bus 0 — CE0 pin owned by spidev but
        t.no_cs = True                # we disable auto-CS so GPIO 7 is manual
        t.max_speed_hz = 1_000_000
        t.mode = 0b00
        print("[TOUCH]   OK – XPT2046 SPI touch ready (CE1=GPIO7 manual).")
        return t, GPIO
    except Exception as e:
        print(f"[TOUCH]   SKIP – {e}")
        return None, None



# ── TOUCH CALIBRATION VALUES ─────────────────────────────────────────────────
# Raw ADC values (0-4095) at each screen edge. Run calibrate.py to find yours.
# Defaults below cover most common 2.4" ILI9341 panels but may be slightly off.
# ── XPT2046 CHANNEL COMMANDS ─────────────────────────────────────────────────
# Run touch_diag.py to find the correct commands for YOUR panel.
# Common values:
#   0x90 = X differential 12-bit   (most panels)
#   0xD0 = Y differential 12-bit   (most panels)
#   0xD0 = X on some panels        (swap if axes feel rotated)
#   0xB0 = Y on some panels
TOUCH_X_CMD = 0x90
TOUCH_Y_CMD = 0xD0

# IRQ polarity confirmed correct by touch_diag.py
TOUCH_IRQ_ACTIVE_HIGH = False

# ── TOUCH CALIBRATION VALUES ─────────────────────────────────────────────────
# Derived from actual corner taps on this panel:
#   TOP-LEFT     (20,  20)  raw=(3729,  409)
#   TOP-RIGHT    (220, 20)  raw=(3715, 3487)
#   BOTTOM-LEFT  (20,  300) raw=( 568,  420)
#   BOTTOM-RIGHT (220, 300) raw=( 515, 3448)
#
# 0x90 changes 3729→568 vertically   → it is the Y axis (DECREASING, so flip)
# 0xD0 changes  409→3487 horizontally → it is the X axis (INCREASING, no flip)
# Axes are physically swapped vs display → SWAP_XY = True
#
CAL_X_MIN   = 445    # 0xD0 raw at LEFT   edge
CAL_X_MAX   = 3492   # 0xD0 raw at RIGHT  edge
CAL_Y_MIN   = 606    # 0x90 raw at BOTTOM edge (after flip)
CAL_Y_MAX   = 3615   # 0x90 raw at TOP    edge (after flip)
CAL_FLIP_X  = False
CAL_FLIP_Y  = True
CAL_SWAP_XY = True


def _raw_touch(tspi, GPIO):
    """Read noise-averaged raw ADC from XPT2046 with manual CE1 control."""
    import RPi.GPIO as _GPIO
    def ch(cmd):
        vals = []
        for _ in range(8):
            _GPIO.output(TOUCH_CS_BCM, _GPIO.LOW)   # assert   CE1
            r = tspi.xfer2([cmd, 0x00, 0x00])
            _GPIO.output(TOUCH_CS_BCM, _GPIO.HIGH)  # deassert CE1
            vals.append(((r[1] << 8) | r[2]) >> 3)
        vals.sort()
        return sum(vals[2:6]) // 4                  # average of middle 4
    return ch(TOUCH_X_CMD), ch(TOUCH_Y_CMD)


def read_touch(tspi, GPIO):
    """
    Returns calibrated (px_x, px_y) mapped to screen pixels, or None.
    Applies: noise averaging, axis swap, linear cal mapping, flip, clamp.
    """
    irq = GPIO.input(TOUCH_IRQ_BCM)
    touching = irq if TOUCH_IRQ_ACTIVE_HIGH else not irq
    if not touching:
        return None

    rx, ry = _raw_touch(tspi, GPIO)

    if CAL_SWAP_XY:
        rx, ry = ry, rx

    x = int((rx - CAL_X_MIN) / max(1, CAL_X_MAX - CAL_X_MIN) * SCREEN_W)
    y = int((ry - CAL_Y_MIN) / max(1, CAL_Y_MAX - CAL_Y_MIN) * SCREEN_H)

    if CAL_FLIP_X:
        x = SCREEN_W - 1 - x
    if CAL_FLIP_Y:
        y = SCREEN_H - 1 - y

    return max(0, min(SCREEN_W - 1, x)), max(0, min(SCREEN_H - 1, y))


# ── HELPERS ──────────────────────────────────────────────────────────────────
def canvas():
    return Image.new("RGB", (SCREEN_W, SCREEN_H), 0)

def push(disp, img):
    disp.image(img)

def fnt(size=14, bold=False):
    name = "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"
    try:
        return ImageFont.truetype(
            f"/usr/share/fonts/truetype/dejavu/{name}", size)
    except Exception:
        return ImageFont.load_default()


# ── TEST 1 – Solid colour fills ───────────────────────────────────────────────
def test_color_fill(disp):
    print("\n[TEST 1] Solid colour fills")
    for name, rgb in [
        ("RED",   (255,   0,   0)),
        ("GREEN", (  0, 255,   0)),
        ("BLUE",  (  0,   0, 255)),
        ("WHITE", (255, 255, 255)),
        ("BLACK", (  0,   0,   0)),
    ]:
        print(f"         {name}")
        img = canvas()
        img.paste(rgb, [0, 0, SCREEN_W, SCREEN_H])
        push(disp, img)
        time.sleep(0.7)
    print("[TEST 1] PASSED")


# ── TEST 2 – RGB gradient ─────────────────────────────────────────────────────
def test_gradient(disp):
    print("\n[TEST 2] RGB gradient")
    img = canvas()
    px  = img.load()
    for y in range(SCREEN_H):
        for x in range(SCREEN_W):
            px[x, y] = (
                int(x / SCREEN_W  * 255),
                int(y / SCREEN_H  * 255),
                128,
            )
    push(disp, img)
    time.sleep(2)
    print("[TEST 2] PASSED")


# ── TEST 3 – Shapes & text ────────────────────────────────────────────────────
def test_shapes_text(disp):
    print("\n[TEST 3] Shapes and text")
    img  = canvas()
    draw = ImageDraw.Draw(img)
    draw.rectangle([0, 0, SCREEN_W, SCREEN_H], fill=(10, 10, 40))

    draw.rectangle([ 10, 10, 100, 60], fill=(200, 50, 50),  outline=(255,255,255))
    draw.rectangle([110, 10, 200, 60], fill=( 50,200, 50),  outline=(255,255,255))
    draw.rectangle([210, 10, 310, 60], fill=( 50, 50,200),  outline=(255,255,255))

    draw.ellipse([10, 80, 110, 180], outline=(255, 200, 0), width=3)

    for i in range(0, SCREEN_W, 20):
        draw.line([(i, 80), (i + 40, 230)], fill=(100, 200, 255), width=1)

    draw.text((10, 190), "ILI9341 Display Test",
              font=fnt(20, bold=True), fill=(255, 255, 100))
    draw.text((10, 215), "Raspberry Pi 4  –  SPI",
              font=fnt(14),           fill=(180, 180, 180))
    push(disp, img)
    time.sleep(3)
    print("[TEST 3] PASSED")


# ── TEST 4 – Scrolling banner ─────────────────────────────────────────────────
def test_scroll(disp):
    print("\n[TEST 4] Scrolling banner (5 s)")
    msg = "  *** ILI9341 OK on Raspberry Pi 4 ***  SPI + XPT2046 Touch Test  "
    f   = fnt(24, bold=True)

    tmp = Image.new("RGB", (1, 1))
    bb  = ImageDraw.Draw(tmp).textbbox((0, 0), msg, font=f)
    tw  = bb[2] - bb[0]

    strip = Image.new("RGB", (tw + SCREEN_W, 40), (0, 0, 60))
    ImageDraw.Draw(strip).text((SCREEN_W, 4), msg, font=f, fill=(0, 220, 255))

    end, offset = time.time() + 5, 0
    while time.time() < end:
        frame = Image.new("RGB", (SCREEN_W, SCREEN_H), (0, 0, 30))
        frame.paste(strip.crop((offset, 0, offset + SCREEN_W, 40)),
                    (0, SCREEN_H // 2 - 20))
        push(disp, frame)
        offset = (offset + 4) % (tw + SCREEN_W)
        time.sleep(0.03)
    print("[TEST 4] PASSED")


# ── TEST 5 – Touch draw ───────────────────────────────────────────────────────
def test_touch_draw(disp, tspi, GPIO):
    if tspi is None:
        print("\n[TEST 5] SKIPPED – touch not available")
        return

    print("\n[TEST 5] Touch draw – draw on screen for 15 s")
    img  = canvas()
    draw = ImageDraw.Draw(img)
    draw.rectangle([0, 0, SCREEN_W, 22], fill=(30, 30, 30))
    draw.text((4, 4), "Touch to draw – 15 s",
              font=fnt(14), fill=(255, 255, 100))
    push(disp, img)

    end, prev, touches = time.time() + 15, None, 0
    while time.time() < end:
        pt = read_touch(tspi, GPIO)
        if pt:
            x, y = pt
            col = (int(255 * x / SCREEN_W), int(255 * y / SCREEN_H), 200)
            if prev:
                draw.line([prev, (x, y)], fill=col, width=3)
            else:
                draw.ellipse([x-3, y-3, x+3, y+3], fill=col)
            push(disp, img)
            prev = (x, y)
            touches += 1
        else:
            prev = None
        time.sleep(0.02)
    print(f"[TEST 5] PASSED – {touches} touch sample(s) detected")


# ── TEST 6 – Backlight PWM ────────────────────────────────────────────────────
def test_backlight(pwm):
    print("\n[TEST 6] Backlight PWM blink")
    if pwm is None:
        print("[TEST 6] SKIPPED – backlight PWM not available")
        return
    try:
        for v in [10, 100, 10, 100, 100]:  # dim → bright → dim → bright → full
            pwm.ChangeDutyCycle(v)
            time.sleep(0.35)
        pwm.ChangeDutyCycle(100)           # restore full brightness
        print("[TEST 6] PASSED")
    except Exception as e:
        print(f"[TEST 6] FAILED – {e}")


# ── SUMMARY SCREEN ────────────────────────────────────────────────────────────
def show_summary(disp, results):
    print("\n[SUMMARY] Showing results on screen...")
    img  = canvas()
    draw = ImageDraw.Draw(img)
    draw.rectangle([0, 0, SCREEN_W, SCREEN_H], fill=(10, 10, 30))
    draw.text((8, 6), "ILI9341 Test Results",
              font=fnt(18, bold=True), fill=(255, 220, 0))
    y = 34
    for name, status in results:
        col = (80, 255, 80)  if status == "PASS" else \
              (255, 80, 80)  if status == "FAIL" else \
              (180, 180, 80)
        draw.text(( 10, y), name,   font=fnt(13), fill=(200, 200, 200))
        draw.text((265, y), status, font=fnt(13), fill=col)
        y += 22
    draw.text((10, y + 8), "Done!", font=fnt(18, bold=True), fill=(100, 200, 255))
    push(disp, img)
    time.sleep(5)


# ── MAIN ──────────────────────────────────────────────────────────────────────
def main():
    print("=" * 50)
    print(" ILI9341 + Touch Test  –  Raspberry Pi 4")
    print("=" * 50)

    try:
        disp = init_display()
    except Exception as e:
        print(f"\n[FATAL] Display init failed: {e}")
        print("\nTroubleshooting:")
        print("  1. sudo pip3 install --break-system-packages adafruit-circuitpython-rgb-display")
        print("  2. sudo raspi-config  →  Interface Options  →  SPI  →  Enable")
        print("  3. Check your wiring – DC=GPIO24, CS=GPIO8, RST=GPIO25")
        sys.exit(1)

    # ── Turn backlight ON immediately so tests are visible ──────────────────
    backlight_pwm = None
    try:
        import RPi.GPIO as GPIO
        GPIO.setwarnings(False)
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(DISP_BL_PIN, GPIO.OUT)
        backlight_pwm = GPIO.PWM(DISP_BL_PIN, 500)
        backlight_pwm.start(100)          # 100% brightness
        print("[DISPLAY] Backlight ON.")
    except Exception as e:
        print(f"[DISPLAY] Backlight warning: {e}")

    tspi, GPIO_mod = init_touch()
    results = []

    def run(label, fn, *args):
        try:
            fn(*args)
            results.append((label, "PASS"))
        except Exception as e:
            print(f"[ERROR] {label}: {e}")
            results.append((label, "FAIL"))

    run("1. Colour Fill",   test_color_fill,   disp)
    run("2. Gradient",      test_gradient,     disp)
    run("3. Shapes+Text",   test_shapes_text,  disp)
    run("4. Scroll Banner", test_scroll,       disp)
    run("5. Touch Draw",    test_touch_draw,   disp, tspi, GPIO_mod)
    run("6. Backlight",     test_backlight,    backlight_pwm)

    show_summary(disp, results)

    if tspi:          tspi.close()
    if backlight_pwm: backlight_pwm.stop()
    if GPIO_mod:      GPIO_mod.cleanup()

    passed = sum(1 for _, s in results if s == "PASS")
    print(f"\n[DONE] {passed}/{len(results)} tests passed.")


if __name__ == "__main__":
    main()
