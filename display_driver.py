#!/usr/bin/env python3
"""
and-desk  –  display_driver.py
────────────────────────────────────────────────────────────────────────────────
ILI9341 (320×240 LANDSCAPE) + ST7735 (160×128 LANDSCAPE) + XPT2046 touch
Raspberry Pi 4  –  shared SPI bus, raw spidev, no adafruit/busio.

Changes from the original test driver:
  ILI9341  MADCTL 0x40 → 0x68  (adds MV bit: swaps axes → landscape 320×240)
  ILI9341  W,H   240,320 → 320,240
  ILI9341  _window  unchanged (just sends pixel coords, orientation is HW)
  ST7735   MADCTL 0x00 → 0x68  (same MV+MX+BGR trick → landscape 160×128)
  ST7735   W,H   128,160 → 160,128
  Touch    SCREEN_W/H  remapped to landscape 320×240
  Touch    CAL values  swapped to match landscape orientation

Wiring (unchanged):
  Shared SPI  →  SCK=GPIO11  MOSI=GPIO10  MISO=GPIO9
  ILI9341     →  CS=GPIO8    DC=GPIO25   RST=GPIO24  BL=GPIO18
  ST7735      →  CS=GPIO5    DC=GPIO23   RST=GPIO4
  XPT2046     →  CS=GPIO7    IRQ=GPIO17

Install:
    sudo pip3 install --break-system-packages pillow spidev RPi.GPIO
Enable SPI:
    sudo raspi-config → Interface Options → SPI → Enable
"""

import time, sys, threading
import RPi.GPIO as GPIO
import spidev
from PIL import Image, ImageDraw, ImageFont

# ── PIN CONFIG (BCM) ──────────────────────────────────────────────────────────
ILI_CS  = 8;  ILI_DC  = 25; ILI_RST = 24; ILI_BL  = 18
ST_CS   = 5;  ST_DC   = 23; ST_RST  = 4
T_CS    = 7;  T_IRQ   = 17

# ── Screen dimensions  ────────────────────────────────────────────────────────
# Both displays are now LANDSCAPE — matches ui.py exactly
SCREEN_W, SCREEN_H = 320, 240   # ILI9341 landscape
ST_W,     ST_H     = 160, 128   # ST7735  landscape

# ── SPI bus ───────────────────────────────────────────────────────────────────
_spi = spidev.SpiDev()
_spi.open(0, 0)
_spi.no_cs        = True
_spi.mode         = 0b00
_spi.max_speed_hz = 40_000_000

_lock = threading.Lock()

# ── GPIO init ─────────────────────────────────────────────────────────────────
GPIO.setwarnings(False)
GPIO.setmode(GPIO.BCM)
for pin in [ILI_CS, ILI_DC, ILI_RST, ILI_BL,
            ST_CS,  ST_DC,  ST_RST,
            T_CS]:
    GPIO.setup(pin, GPIO.OUT, initial=GPIO.HIGH)
GPIO.setup(T_IRQ, GPIO.IN, pull_up_down=GPIO.PUD_UP)


# ── Low-level SPI helpers ─────────────────────────────────────────────────────
def _write_bytes(cs_pin, dc_pin, dc_mode, data, speed):
    with _lock:
        _spi.max_speed_hz = speed
        GPIO.output(dc_pin, GPIO.HIGH if dc_mode else GPIO.LOW)
        GPIO.output(cs_pin, GPIO.LOW)
        for i in range(0, len(data), 4096):
            _spi.writebytes2(data[i:i+4096])
        GPIO.output(cs_pin, GPIO.HIGH)

def _cmd(cs, dc, cmd, speed):
    _write_bytes(cs, dc, False, [cmd], speed)

def _dat(cs, dc, data, speed):
    _write_bytes(cs, dc, True, data, speed)

def _cmd_dat(cs, dc, cmd, data, speed):
    _cmd(cs, dc, cmd, speed)
    if data:
        _dat(cs, dc, data, speed)


# ═══════════════════════════════════════════════════════════════════════════════
# ILI9341  –  LANDSCAPE 320×240
# ═══════════════════════════════════════════════════════════════════════════════
class ILI9341:
    W, H = 320, 240          # landscape dimensions
    SPD  = 40_000_000

    def _c(self, cmd, data=None): _cmd_dat(ILI_CS, ILI_DC, cmd, data, self.SPD)

    def __init__(self):
        GPIO.output(ILI_RST, GPIO.LOW);  time.sleep(0.1)
        GPIO.output(ILI_RST, GPIO.HIGH); time.sleep(0.1)

        c = self._c
        c(0x01);              time.sleep(0.15)   # SW reset
        c(0x11);              time.sleep(0.12)   # sleep out
        c(0xCF, [0x00, 0x83, 0x30])
        c(0xED, [0x64, 0x03, 0x12, 0x81])
        c(0xE8, [0x85, 0x01, 0x79])
        c(0xCB, [0x39, 0x2C, 0x00, 0x34, 0x02])
        c(0xF7, [0x20])
        c(0xEA, [0x00, 0x00])
        c(0xC0, [0x26])                          # power control 1
        c(0xC1, [0x11])                          # power control 2
        c(0xC5, [0x35, 0x3E])                    # VCOM 1
        c(0xC7, [0xBE])                          # VCOM 2
        # ── MADCTL landscape ──────────────────────────────────────────────────
        # 0xE8 = MY + MV + MX + BGR
        #   MV  (0x20) swap axes  → landscape 320x240
        #   MX  (0x40) mirror col
        #   MY  (0x80) mirror row → fixes upside-down image
        #   BGR (0x08) B/R swap   → correct colours on BGR panel
        # Still wrong? Try: mirrored=0xA8  upside-down=0x68  colours=0xE0
        c(0x36, [0xE8])
        c(0x3A, [0x55])                          # pixel format 16-bit RGB565
        c(0xB1, [0x00, 0x1B])                    # frame rate
        c(0xF2, [0x08])                          # 3-gamma off
        c(0x26, [0x01])                          # gamma curve
        c(0xE0, [0x1F, 0x1A, 0x18, 0x0A, 0x0F, 0x06, 0x45, 0x87,
                 0x32, 0x0A, 0x07, 0x02, 0x07, 0x05, 0x00])
        c(0xE1, [0x00, 0x25, 0x27, 0x05, 0x10, 0x09, 0x3A, 0x78,
                 0x4D, 0x05, 0x18, 0x0D, 0x38, 0x3A, 0x1F])
        c(0x29);              time.sleep(0.05)   # display on
        print("[ILI9341] OK – landscape 320×240")

    def _window(self, x0, y0, x1, y1):
        self._c(0x2A, [x0 >> 8, x0 & 0xFF, x1 >> 8, x1 & 0xFF])
        self._c(0x2B, [y0 >> 8, y0 & 0xFF, y1 >> 8, y1 & 0xFF])
        self._c(0x2C)

    def image(self, img):
        if img.size != (self.W, self.H):
            img = img.resize((self.W, self.H))
        if img.mode != 'RGB':
            img = img.convert('RGB')
        raw = img.tobytes()
        buf = bytearray(self.W * self.H * 2)
        for i in range(self.W * self.H):
            r, g, b = raw[i*3], raw[i*3+1], raw[i*3+2]
            c = ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)
            buf[i*2]     = c >> 8
            buf[i*2 + 1] = c & 0xFF
        self._window(0, 0, self.W - 1, self.H - 1)
        _dat(ILI_CS, ILI_DC, buf, self.SPD)


# ═══════════════════════════════════════════════════════════════════════════════
# ST7735  –  LANDSCAPE 160×128
# ═══════════════════════════════════════════════════════════════════════════════
class ST7735:
    W, H = 160, 128          # landscape dimensions
    SPD  = 15_000_000

    def _c(self, cmd, data=None): _cmd_dat(ST_CS, ST_DC, cmd, data, self.SPD)

    def __init__(self):
        GPIO.output(ST_RST, GPIO.LOW);  time.sleep(0.1)
        GPIO.output(ST_RST, GPIO.HIGH); time.sleep(0.1)

        c = self._c
        c(0x01);              time.sleep(0.15)
        c(0x11);              time.sleep(0.5)
        c(0xB1, [0x01, 0x2C, 0x2D])
        c(0xB4, [0x07])
        c(0xC0, [0xA2, 0x02, 0x84])
        c(0xC1, [0xC5])
        c(0xC2, [0x0A, 0x00])
        c(0xC5, [0x8A, 0x2A])
        c(0x3A, [0x05])                          # RGB565
        # ── MADCTL landscape ──────────────────────────────────────────────────
        # 0x68 = MV+MX+BGR → landscape 160×128, colours correct
        # If mirrored/flipped try: 0x28, 0xA8, 0xC8
        c(0x36, [0x68])
        c(0xE0, [0x02, 0x1C, 0x07, 0x12, 0x37, 0x32, 0x29, 0x2D,
                 0x29, 0x25, 0x2B, 0x39, 0x00, 0x01, 0x03, 0x10])
        c(0xE1, [0x03, 0x1D, 0x07, 0x06, 0x2E, 0x2C, 0x29, 0x2D,
                 0x2E, 0x2E, 0x37, 0x3F, 0x00, 0x00, 0x02, 0x10])
        c(0x13);              time.sleep(0.01)
        c(0x29);              time.sleep(0.1)
        print("[ST7735]  OK – landscape 160×128")

    def _window(self, x0, y0, x1, y1):
        self._c(0x2A, [0x00, x0, 0x00, x1])
        self._c(0x2B, [0x00, y0, 0x00, y1])
        self._c(0x2C)

    def image(self, img):
        if img.size != (self.W, self.H):
            img = img.resize((self.W, self.H))
        if img.mode != 'RGB':
            img = img.convert('RGB')
        raw = img.tobytes()
        buf = bytearray(self.W * self.H * 2)
        for i in range(self.W * self.H):
            r, g, b = raw[i*3], raw[i*3+1], raw[i*3+2]
            c = ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)
            buf[i*2]     = c >> 8
            buf[i*2 + 1] = c & 0xFF
        self._window(0, 0, self.W - 1, self.H - 1)
        _dat(ST_CS, ST_DC, buf, self.SPD)


# ═══════════════════════════════════════════════════════════════════════════════
# TOUCH  –  XPT2046  (calibrated for landscape 320×240)
# ═══════════════════════════════════════════════════════════════════════════════
TOUCH_X_CMD = 0x90
TOUCH_Y_CMD = 0xD0

# ── Calibration ───────────────────────────────────────────────────────────────
# These match the ORIGINAL portrait calibration values from the test driver.
# We remap them into landscape coords in read_touch() below.
# If touch is inaccurate run a calibration routine and update these 4 values.
CAL_X_MIN = 445;  CAL_X_MAX = 3492
CAL_Y_MIN = 606;  CAL_Y_MAX = 3615

# ── Orientation flags ─────────────────────────────────────────────────────────
# XPT2046 is physically wired to the panel — touch axes follow the raw panel,
# not the MADCTL rotation.  We correct here in software to match screen coords.
#
# MADCTL 0xE8 (MY+MV+MX+BGR) — current setting:
#   MY flips vertical scan  → FLIP_Y must be False  (MY already did it in HW)
#   MX flips horizontal     → FLIP_X must be True   (touch X still needs flip)
#   MV swaps axes           → SWAP_XY stays False   (landscape already handled)
#
# Quick-fix guide if taps still land in the wrong spot:
#   Tap top-left lands bottom-right  → toggle both FLIP_X and FLIP_Y
#   Tap top lands bottom only        → toggle FLIP_Y
#   Tap left lands right only        → toggle FLIP_X
#   X and Y axes feel swapped        → toggle SWAP_XY
CAL_SWAP_XY           = False
CAL_FLIP_X            = False
CAL_FLIP_Y            = False
TOUCH_IRQ_ACTIVE_HIGH = False


def _raw_touch():
    """Read XPT2046 raw ADC — 1 MHz, 8 samples, median-averaged."""
    def ch(cmd):
        vals = []
        with _lock:
            _spi.max_speed_hz = 1_000_000
            for _ in range(8):
                GPIO.output(T_CS, GPIO.LOW)
                r = _spi.xfer2([cmd, 0x00, 0x00])
                GPIO.output(T_CS, GPIO.HIGH)
                vals.append(((r[1] << 8) | r[2]) >> 3)
        vals.sort()
        return sum(vals[2:6]) // 4
    return ch(TOUCH_X_CMD), ch(TOUCH_Y_CMD)


def read_touch():
    """
    Returns (x, y) in landscape pixel coords (0–319, 0–239),
    or None if no touch detected.
    """
    irq = GPIO.input(T_IRQ)
    if not TOUCH_IRQ_ACTIVE_HIGH:
        if irq:
            return None     # IRQ is active-low; HIGH = no touch
    else:
        if not irq:
            return None

    rx, ry = _raw_touch()

    if CAL_SWAP_XY:
        rx, ry = ry, rx

    # Map raw ADC → landscape pixels
    x = int((rx - CAL_X_MIN) / max(1, CAL_X_MAX - CAL_X_MIN) * SCREEN_W)
    y = int((ry - CAL_Y_MIN) / max(1, CAL_Y_MAX - CAL_Y_MIN) * SCREEN_H)

    if CAL_FLIP_X: x = SCREEN_W - 1 - x
    if CAL_FLIP_Y: y = SCREEN_H - 1 - y

    return (max(0, min(SCREEN_W - 1, x)),
            max(0, min(SCREEN_H - 1, y)))


# ═══════════════════════════════════════════════════════════════════════════════
# ORIENTATION NOTES  (keep this block as reference)
# ═══════════════════════════════════════════════════════════════════════════════
"""
MADCTL byte quick-reference (ILI9341 & ST7735 share same bit layout):

  Bit  7  MY  – Mirror rows
  Bit  6  MX  – Mirror columns
  Bit  5  MV  – Swap row/col axes  ← landscape vs portrait
  Bit  3  BGR – Swap R/B channels  ← must match panel (these are BGR panels)

  0x00 = portrait  normal           (240×320)
  0x40 = portrait  MX-mirrored      (240×320) ← original test driver
  0x68 = landscape MV+MX+BGR        (320×240, image inverted)
  0x28 = landscape MV+BGR           (320×240, flipped vertically)
  0xA8 = landscape MV+MY+BGR        (320×240, flipped horizontally)
  0xE8 = landscape MV+MX+MY+BGR     (320×240) ← and-desk target (fixes inversion)

If display content appears:
  Upside-down  → flip MY bit (XOR with 0x80)
  Left-right   → flip MX bit (XOR with 0x40)
  Transposed   → flip MV bit (XOR with 0x20)
  Wrong colour → flip BGR bit (XOR with 0x08)
"""
