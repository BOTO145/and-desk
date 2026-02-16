# and-desk<div align="center">

<br/>

```
 █████╗ ███╗   ██╗██████╗       ██████╗ ███████╗███████╗██╗  ██╗
██╔══██╗████╗  ██║██╔══██╗      ██╔══██╗██╔════╝██╔════╝██║ ██╔╝
███████║██╔██╗ ██║██║  ██║█████╗██║  ██║█████╗  ███████╗█████╔╝ 
██╔══██║██║╚██╗██║██║  ██║╚════╝██║  ██║██╔══╝  ╚════██║██╔═██╗ 
██║  ██║██║ ╚████║██████╔╝      ██████╔╝███████╗███████║██║  ██╗
╚═╝  ╚═╝╚═╝  ╚═══╝╚═════╝       ╚═════╝ ╚══════╝╚══════╝╚═╝  ╚═╝
```

**A Raspberry Pi–powered personal assistant desk device**  
*Minimal. Aesthetic. Always on.*

<br/>

![Python](https://img.shields.io/badge/Python-3.10+-3776AB?style=flat-square&logo=python&logoColor=white)
![Platform](https://img.shields.io/badge/Platform-Raspberry_Pi_4-C51A4A?style=flat-square&logo=raspberrypi&logoColor=white)
![Status](https://img.shields.io/badge/Status-Active_Development-f59e0b?style=flat-square)
![Displays](https://img.shields.io/badge/Displays-ILI9341_+_ST7735-0ea5e9?style=flat-square)

<br/>

</div>

---

## What is and-desk?

**and-desk** is a physical, always-on productivity assistant that sits on your desk and connects to your main PC. It runs on a Raspberry Pi 4 and drives two small SPI displays — a main dashboard and a persistent status widget — giving you live system stats, weather, calendar, emails, and focus sessions without ever touching your main monitor.

No browser tab. No alt-tab. Just glance down.

<br/>

## Hardware

| Component | Spec | Role |
|-----------|------|------|
| **Raspberry Pi 4** | 2GB+ RAM | Brain |
| **ILI9341** | 320×240 SPI TFT | Main display — dashboard & apps |
| **ST7735** | 160×128 SPI TFT | Status widget — always on |
| **XPT2046** | Resistive touch | Input on main display |

Both displays share a single SPI bus — no bus conflicts, no kernel-level adapters.

<br/>

## Wiring

```
Shared SPI   →   SCK = GPIO 11    MOSI = GPIO 10    MISO = GPIO 9

ILI9341      →   CS = GPIO 8      DC = GPIO 25      RST = GPIO 24     BL = GPIO 18
ST7735       →   CS = GPIO 5      DC = GPIO 23      RST = GPIO 4
XPT2046      →   CS = GPIO 7      IRQ = GPIO 17
```

<br/>

## Screens

### ILI9341 — Main Display (320×240)

The main display has six screens, navigated by touch.

```
┌─────────────────────────────────────┐
│  DASHBOARD                  16:20   │   Tap the disk chart → Apps grid
│  ┌──────┐  Reminder                 │
│  │ DISK │  Meeting in 15 min        │
│  │ PIE  │  Inbox  ·  3 new          │
│  │      │  System  ·  Online        │
│  └──────┘  Focus ready              │
│  tork                               │
└─────────────────────────────────────┘

┌─────────────────────────────────────┐
│  APPS                               │   Tap any tile → open that function
│  ┌──────────────┬──────────────┐    │
│  │  summarize   │    focus     │    │
│  │    mails     │    mode      │    │
│  ├──────────────┼──────────────┤    │
│  │    brief     │   system     │    │
│  │   my day     │    care      │    │
│  └──────────────┴──────────────┘    │
│  ← back                             │
└─────────────────────────────────────┘
```

| Screen | Function |
|--------|----------|
| **Dashboard** | Activity feed, disk usage pie, live time |
| **Brief My Day** | Weather, schedule, reminders |
| **Summarize Emails** | AI summary + unread message list |
| **System Care** | CPU/RAM/disk bars for deck + server, temp file cleaner |
| **Focus Mode** | Countdown timer, progress bar, closes all windows |
| **Apps Grid** | 4-tile launcher, opens from disk pie tap |

### ST7735 — Status Widget (160×128)

Always-on. Never changes screen. Refreshes every 5 seconds.

```
┌────────────────────────────────┐
│  DECK  ●    │   SERVER  ●     │
│  CPU  38°C  │   CPU  55°C     │
│  FAN  28%   │   GPU  12%      │
│  DISK 42/64G│   DISK 260/500G │
├─────────────────────────────── ┤
│  weather          ●            │
│  ~   24°/15° C                 │
└────────────────────────────────┘
```

<br/>

## Project Structure

```
and-desk/
│
├── display_driver.py   # Raw spidev driver — ILI9341, ST7735, XPT2046 touch
│                       # No adafruit. No busio. Pure GPIO + spidev.
│
├── ui.py               # All screen renderers (Pillow-based)
│                       # render_dashboard(), render_apps(), render_brief()
│                       # render_emails(), render_sysmon(), render_focus()
│                       # render_st_status()
│
├── main.py             # Main loop — touch routing, state machine, frame loop
│                       # 10fps on ILI9341, 5s refresh on ST7735
│
└── server/
    └── server.py       # Python server running on host PC
                        # Serves system stats, emails, calendar, weather
                        # Accepts commands from the Pi (focus mode, clean, etc.)
```

<br/>

## Architecture

```
  ┌─────────────────────────────┐         ┌──────────────────────────────┐
  │        Raspberry Pi 4       │         │           Host PC            │
  │                             │  Wi-Fi  │                              │
  │  main.py ──► ui.py          │◄───────►│  server.py                   │
  │      │                      │  TCP    │    ├── system stats (psutil) │
  │      ▼                      │         │    ├── email (IMAP)          │
  │  display_driver.py          │         │    ├── calendar              │
  │      ├── ILI9341 (320×240)  │         │    ├── weather API           │
  │      ├── ST7735  (160×128)  │         │    └── focus control         │
  │      └── XPT2046 (touch)    │         │         (close windows, etc.)│
  └─────────────────────────────┘         └──────────────────────────────┘
```

The Pi polls the server for data and sends commands back (start focus, clean temp files, etc.). The server runs silently in the background on the host PC.

<br/>

## Install

```bash
# On the Raspberry Pi
sudo raspi-config          # Interface Options → SPI → Enable

sudo pip3 install --break-system-packages pillow spidev RPi.GPIO

git clone https://github.com/yourusername/and-desk.git
cd and-desk

python3 main.py
```

Running on a PC (no hardware)? `main.py` detects the missing hardware and drops into **headless preview mode** — it renders all screens to `/tmp/and-desk-live/` as PNGs so you can develop the UI without the Pi.

<br/>

## Display Orientation

Both displays are configured for **landscape** mode via the MADCTL register.

| Register | Value | Meaning |
|----------|-------|---------|
| `0x36` ILI9341 | `0xE8` | `MY + MV + MX + BGR` → landscape 320×240 |
| `0x36` ST7735  | `0x68` | `MV + MX + BGR` → landscape 160×128 |

If your image appears flipped or mirrored:

```
Upside-down       → XOR with 0x80  (toggle MY)
Left-right mirror → XOR with 0x40  (toggle MX)
Axes swapped      → XOR with 0x20  (toggle MV)
Wrong colours     → XOR with 0x08  (toggle BGR)
```

<br/>

## Touch Calibration

Touch is handled by the XPT2046 over the shared SPI bus at 1MHz. If taps land in the wrong position:

```python
# display_driver.py — adjust these four flags
CAL_SWAP_XY = False   # swap X and Y axes
CAL_FLIP_X  = False   # mirror horizontally
CAL_FLIP_Y  = False   # mirror vertically

# If raw ADC values are off, update these
CAL_X_MIN = 445;  CAL_X_MAX = 3492
CAL_Y_MIN = 606;  CAL_Y_MAX = 3615
```

Quick diagnosis:

```
Taps inverted top↔bottom  → toggle CAL_FLIP_Y
Taps inverted left↔right  → toggle CAL_FLIP_X
X and Y axes feel swapped → toggle CAL_SWAP_XY
```

<br/>

## Design Language

- **Dark background** `#08090C` — easy on the eyes in a dim room
- **Neon accents** — each function has its own colour identity
- **Minimal chrome** — one top bar, one bottom hint, single-pixel dividers only
- **No decorative noise** — no corner brackets, no glow effects, no scan lines

| Colour | Hex | Used for |
|--------|-----|----------|
| Cyan | `#00D2F0` | Primary accent, dashboard |
| Orange | `#FF8228` | Mails, reminders |
| Blue | `#468CFF` | Focus mode, inbox |
| Green | `#00D278` | System care, online status |
| Magenta | `#DC3CC8` | Focus timer |
| Yellow | `#F0BE00` | Warnings |

<br/>

## Roadmap

- [x] Dual SPI display driver (no adafruit/busio)
- [x] Landscape orientation on both displays
- [x] Touch routing with debounce
- [x] Dashboard, Apps, Brief, Emails, Sysmon, Focus screens
- [x] ST7735 status widget (deck + server + weather)
- [ ] Server communication layer (TCP/JSON)
- [ ] Email fetching (IMAP)
- [ ] Calendar / Google Calendar integration
- [ ] Weather API integration
- [ ] Focus mode — window management on host PC
- [ ] Temp file cleaner commands
- [ ] Auto-start on boot (systemd service)
- [ ] Touch calibration utility

<br/>

## Contributing

This project is in active development. If you build one, open an issue and share your setup — hardware variations (different SPI TFT modules, Pi versions) are welcome.

<br/>
---

<div align="center">
<sub>Built with Pillow, spidev, RPi.GPIO — and a lot of squinting at tiny screens.</sub>
</div>
