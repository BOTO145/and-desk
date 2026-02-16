#!/usr/bin/env python3
"""
and-desk  –  main.py
────────────────────────────────────────────────────────────────────────────────
Wires ui.py (renderer) to the physical ILI9341 + ST7735 displays.
Uses the raw spidev driver from display_driver.py (no adafruit/busio).

Run:
    python3 main.py

Dependencies (already in display_driver.py):
    sudo pip3 install --break-system-packages pillow spidev RPi.GPIO
"""

import time
import threading
import sys

# ── Import the spidev driver ──────────────────────────────────────────────────
# display_driver.py must be in the same directory.
try:
    from display_driver import (
        ILI9341, ST7735,
        read_touch,
        ILI_BL,
        GPIO,
    )
    import RPi.GPIO as GPIO
    HARDWARE = True
except ImportError:
    # Running on PC for layout testing — stub out hardware
    HARDWARE = False
    print("[main] No hardware detected — running in headless preview mode.")

from ui import (
    render_dashboard, render_apps, render_brief,
    render_emails, render_sysmon, render_focus,
    render_st_status,
    hit_test,
    DASHBOARD_PIE_REGION, BACK_REGION,
    APPS_TILES,
    SCREEN_DASHBOARD, SCREEN_APPS, SCREEN_BRIEF,
    SCREEN_EMAILS, SCREEN_SYSMON, SCREEN_FOCUS,
)

import time as _time


# ════════════════════════════════════════════════════════════════════════════════
# STATE
# ════════════════════════════════════════════════════════════════════════════════

class AppState:
    def __init__(self):
        self.screen      = SCREEN_DASHBOARD   # current ILI9341 screen
        self.apps_rects  = []                  # hit rects returned by render_apps
        self.last_touch  = None                # (x, y) of last touch event
        self.touch_lock  = False               # debounce flag

        # Data buckets — filled by server polling thread
        self.time_str    = ""
        self.date_str    = ""
        self.username    = "tork"

        self.activities  = []
        self.weather     = {}
        self.events      = []
        self.reminders   = []
        self.emails      = []
        self.unread      = 0
        self.email_summary = ""

        self.deck_stats  = {}
        self.server_stats= {}
        self.temp_info   = {}
        self.clean_done  = False

        self.focus_session_mins = 25
        self.focus_elapsed_mins = 0
        self.focus_active       = False
        self.focus_app          = ""
        self.focus_message      = ""

        self.deck_online   = True
        self.server_online = True

    def tick_time(self):
        self.time_str = _time.strftime("%H:%M")
        self.date_str = _time.strftime("%a, %d %b %Y")


state = AppState()


# ════════════════════════════════════════════════════════════════════════════════
# RENDER HELPERS
# ════════════════════════════════════════════════════════════════════════════════

def build_ili_frame():
    """Return the correct Image for the current screen."""
    s = state.screen

    if s == SCREEN_DASHBOARD:
        return render_dashboard({
            "time_str":   state.time_str,
            "date_str":   state.date_str,
            "username":   state.username,
            "activities": state.activities,
        })

    if s == SCREEN_APPS:
        img, rects = render_apps({})
        state.apps_rects = rects
        return img

    if s == SCREEN_BRIEF:
        return render_brief({
            "time_str":  state.time_str,
            "date_str":  state.date_str,
            "weather":   state.weather,
            "events":    state.events,
            "reminders": state.reminders,
        })

    if s == SCREEN_EMAILS:
        return render_emails({
            "time_str":    state.time_str,
            "summary":     state.email_summary,
            "emails":      state.emails,
            "unread_count":state.unread,
        })

    if s == SCREEN_SYSMON:
        return render_sysmon({
            "time_str":   state.time_str,
            "deck":       state.deck_stats   or None,
            "server":     state.server_stats or None,
            "temp_files": state.temp_info,
            "clean_done": state.clean_done,
        })

    if s == SCREEN_FOCUS:
        return render_focus({
            "time_str":     state.time_str,
            "session_mins": state.focus_session_mins,
            "elapsed_mins": state.focus_elapsed_mins,
            "app_name":     state.focus_app,
            "active":       state.focus_active,
            "message":      state.focus_message,
        })

    return render_dashboard({
        "time_str": state.time_str,
        "username": state.username,
    })


def build_st_frame():
    return render_st_status({
        "deck":          state.deck_stats   or {},
        "server":        state.server_stats or {},
        "weather":       state.weather,
        "deck_online":   state.deck_online,
        "server_online": state.server_online,
    })


# ════════════════════════════════════════════════════════════════════════════════
# TOUCH ROUTING
# ════════════════════════════════════════════════════════════════════════════════

DEBOUNCE_MS = 300   # ignore touches within 300ms of last one

def handle_touch(x, y):
    """Route a validated touch coordinate to a screen transition or action."""
    s = state.screen

    if s == SCREEN_DASHBOARD:
        target = hit_test(x, y, DASHBOARD_PIE_REGION)
        if target:
            state.screen = target
            return True

    elif s == SCREEN_APPS:
        # Check app tiles
        target = hit_test(x, y, state.apps_rects)
        if target:
            state.screen = target
            return True
        # Back (top-right)
        back = hit_test(x, y, BACK_REGION)
        if back:
            state.screen = back
            return True

    else:
        # Any sub-screen: back tap
        back = hit_test(x, y, BACK_REGION)
        if back:
            # Focus mode: end session on back
            if s == SCREEN_FOCUS and state.focus_active:
                state.focus_active       = False
                state.focus_elapsed_mins = 0
                state.focus_message      = "Session ended."
            # Sysmon: reset clean flag
            if s == SCREEN_SYSMON:
                state.clean_done = False
            state.screen = back
            return True

        # Sysmon: tap anywhere in content to clean
        if s == SCREEN_SYSMON and not state.clean_done:
            state.clean_done = True
            return True

    return False


# ════════════════════════════════════════════════════════════════════════════════
# FOCUS TIMER TICK
# ════════════════════════════════════════════════════════════════════════════════

_focus_last_tick = 0.0

def tick_focus():
    global _focus_last_tick
    if not state.focus_active:
        return
    now = _time.time()
    if now - _focus_last_tick >= 60.0:   # tick every real minute
        _focus_last_tick = now
        state.focus_elapsed_mins += 1
        if state.focus_elapsed_mins >= state.focus_session_mins:
            state.focus_active  = False
            state.focus_message = "Session complete!"


# ════════════════════════════════════════════════════════════════════════════════
# MAIN LOOP
# ════════════════════════════════════════════════════════════════════════════════

ILI_REFRESH_HZ = 10   # ILI9341 target frame rate
ST_REFRESH_S   = 5    # ST7735 refreshes every N seconds (stats don't change fast)

def main():
    state.tick_time()

    if HARDWARE:
        # ── Init displays ─────────────────────────────────────────────────────
        print("[main] Initialising ILI9341...")
        disp = ILI9341()

        print("[main] Initialising ST7735...")
        st = ST7735()

        # Backlight on
        GPIO.setup(ILI_BL, GPIO.OUT)
        bl = GPIO.PWM(ILI_BL, 500)
        bl.start(100)
        print("[main] Backlight ON.")
        print("[main] Running. Tap the disk chart to open apps.\n")

        last_st_update = 0.0
        last_touch_ms  = 0.0
        frame_interval = 1.0 / ILI_REFRESH_HZ

        try:
            while True:
                loop_start = _time.time()

                # ── Time update ───────────────────────────────────────────────
                state.tick_time()
                tick_focus()

                # ── Touch read ────────────────────────────────────────────────
                pt = read_touch()
                if pt:
                    now_ms = _time.time() * 1000
                    if now_ms - last_touch_ms > DEBOUNCE_MS:
                        last_touch_ms = now_ms
                        x, y = pt
                        changed = handle_touch(x, y)
                        if changed:
                            print(f"[touch] ({x},{y}) → {state.screen}")

                # ── ILI9341 frame ─────────────────────────────────────────────
                disp.image(build_ili_frame())

                # ── ST7735 frame (slow refresh) ───────────────────────────────
                now = _time.time()
                if now - last_st_update >= ST_REFRESH_S:
                    st.image(build_st_frame())
                    last_st_update = now

                # ── Frame rate cap ────────────────────────────────────────────
                elapsed = _time.time() - loop_start
                sleep_t = max(0.0, frame_interval - elapsed)
                if sleep_t:
                    _time.sleep(sleep_t)

        except KeyboardInterrupt:
            print("\n[main] Stopped.")
        finally:
            bl.stop()
            from display_driver import _spi
            _spi.close()
            GPIO.cleanup()

    else:
        # ── Headless PC preview — save one frame per screen ───────────────────
        import os
        out = "/tmp/and-desk-live"
        os.makedirs(out, exist_ok=True)

        state.tick_time()
        state.deck_stats    = {"cpu":38,"ram":31,"disk_used":42,"disk_total":64,"fan":28}
        state.server_stats  = {"cpu":55,"gpu":12,"ram":74,"disk_used":260,"disk_total":500}
        state.weather       = {"temp_hi":24,"temp_lo":15,"icon":"~","online":True}
        state.email_summary = "Q4 review from boss, merged PR notification, team digest."
        state.unread        = 3
        state.temp_info     = {"count":127,"size_mb":340}
        state.focus_app     = "VS Code"
        state.focus_active  = True
        state.focus_session_mins = 25
        state.focus_elapsed_mins = 8

        for scr in [SCREEN_DASHBOARD, SCREEN_APPS, SCREEN_BRIEF,
                    SCREEN_EMAILS, SCREEN_SYSMON, SCREEN_FOCUS]:
            state.screen = scr
            img = build_ili_frame()
            img.save(f"{out}/{scr}.png")
            print(f"[preview] saved {out}/{scr}.png")

        st_img = build_st_frame()
        st_img.save(f"{out}/st_status.png")
        print(f"[preview] saved {out}/st_status.png")
        print("[main] Headless preview complete.")


if __name__ == "__main__":
    main()
