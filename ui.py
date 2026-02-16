#!/usr/bin/env python3
"""
and-desk  –  UI Renderer  (minimal edition)
────────────────────────────────────────────────────────────────────────────────
ILI9341 320×240 landscape  |  ST7735 160×128 landscape
Dark theme, neon accents, clean layout. No decorative noise.
"""

import math, time
from PIL import Image, ImageDraw, ImageFont

# ── Dimensions ────────────────────────────────────────────────────────────────
ILI_W, ILI_H = 320, 240
ST_W,  ST_H  = 160, 128

# ── Palette ───────────────────────────────────────────────────────────────────
BG      = (8,   9,  12)
SURFACE = (14,  16,  22)
LINE    = (26,  30,  40)
CYAN    = (0,  210, 240)
GREEN   = (0,  210, 120)
YELLOW  = (240, 190,  0)
ORANGE  = (255, 130,  40)
BLUE    = (70,  140, 255)
MAGENTA = (220,  60, 200)
RED     = (220,  60,  60)
WHITE   = (210, 215, 225)
MUTED   = ( 85,  95, 115)

APP_COLS = [ORANGE, BLUE, CYAN, GREEN]  # mails, focus, brief, sysmon

SCREEN_DASHBOARD = "dashboard"
SCREEN_APPS      = "apps"
SCREEN_BRIEF     = "brief"
SCREEN_EMAILS    = "emails"
SCREEN_SYSMON    = "sysmon"
SCREEN_FOCUS     = "focus"

# ── Fonts ─────────────────────────────────────────────────────────────────────
_fc = {}
def fnt(size=13, bold=False):
    k = (size, bold)
    if k not in _fc:
        name = "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"
        try:
            _fc[k] = ImageFont.truetype(
                f"/usr/share/fonts/truetype/dejavu/{name}", size)
        except Exception:
            _fc[k] = ImageFont.load_default()
    return _fc[k]

def tw(draw, text, font):
    bb = draw.textbbox((0, 0), text, font=font)
    return bb[2] - bb[0]

def th(draw, text, font):
    bb = draw.textbbox((0, 0), text, font=font)
    return bb[3] - bb[1]

def ili_canvas(): return Image.new("RGB", (ILI_W, ILI_H), BG)
def st_canvas():  return Image.new("RGB", (ST_W,  ST_H),  BG)


# ════════════════════════════════════════════════════════════════════════════════
# PRIMITIVES
# ════════════════════════════════════════════════════════════════════════════════

def hline(draw, x0, x1, y, color=LINE):
    draw.line([(x0, y), (x1, y)], fill=color, width=1)

def vline(draw, x, y0, y1, color=LINE):
    draw.line([(x, y0), (x, y1)], fill=color, width=1)

def dot(draw, cx, cy, r=3, color=GREEN):
    draw.ellipse([cx-r, cy-r, cx+r, cy+r], fill=color)

def status_dot(draw, cx, cy, online=True):
    color = GREEN if online is True else (YELLOW if online == "warn" else RED)
    dot(draw, cx, cy, r=3, color=color)

def draw_pie(draw, cx, cy, r):
    """4 equal slices at 90° steps from 3-o'clock. Colours = 4 apps."""
    start = 0.0
    for color in APP_COLS:
        draw.pieslice([cx-r, cy-r, cx+r, cy+r],
                      start=start, end=start+90.0, fill=color)
        start += 90.0
    for deg in [0, 90, 180, 270]:
        rad = math.radians(deg)
        draw.line([(cx, cy),
                   (cx + r * math.cos(rad), cy + r * math.sin(rad))],
                  fill=BG, width=2)

def progress_bar(draw, x, y, w, h, frac, color):
    draw.rectangle([x, y, x+w, y+h], fill=SURFACE)
    fill = max(0, min(w, int(w * frac)))
    if fill:
        draw.rectangle([x, y, x+fill, y+h], fill=color)

def _safe(d, *keys, default="--"):
    """Try multiple key spellings, return first match or default."""
    for k in keys:
        if k in d:
            return d[k]
    return default


# ════════════════════════════════════════════════════════════════════════════════
# CHROME
# ════════════════════════════════════════════════════════════════════════════════

BAR_H = 24
BOT_H = 18

def top_bar(draw, left_text, right_text="", accent=CYAN):
    draw.rectangle([0, 0, ILI_W, BAR_H], fill=SURFACE)
    draw.text((10, (BAR_H - th(draw, left_text, fnt(11, True))) // 2),
              left_text, font=fnt(11, bold=True), fill=accent)
    if right_text:
        rtw = tw(draw, right_text, fnt(11, bold=True))
        draw.text((ILI_W - rtw - 10,
                   (BAR_H - th(draw, right_text, fnt(11, True))) // 2),
                  right_text, font=fnt(11, bold=True), fill=accent)
    hline(draw, 0, ILI_W, BAR_H, LINE)

def bottom_hint(draw, text, color=MUTED):
    """Bottom bar — back text sits bottom-left as a tap target."""
    y = ILI_H - BOT_H
    hline(draw, 0, ILI_W, y, LINE)
    draw.text((10, y + (BOT_H - th(draw, text, fnt(9))) // 2),
              text, font=fnt(9), fill=color)


# ════════════════════════════════════════════════════════════════════════════════
# DASHBOARD
# ════════════════════════════════════════════════════════════════════════════════

def render_dashboard(data: dict) -> Image.Image:
    img  = ili_canvas()
    draw = ImageDraw.Draw(img)

    time_str   = data.get("time_str",   "00:00")
    date_str   = data.get("date_str",   "")
    username   = data.get("username",   "user")
    activities = data.get("activities", [])

    top_bar(draw, "activity", time_str)

    COL_W  = 110
    pie_cx = COL_W // 2
    pie_cy = BAR_H + (ILI_H - BAR_H - BOT_H) // 2
    pie_r  = 38

    draw_pie(draw, pie_cx, pie_cy, pie_r)
    draw.ellipse([pie_cx-pie_r-1, pie_cy-pie_r-1,
                  pie_cx+pie_r+1, pie_cy+pie_r+1],
                 outline=LINE, width=1)

    lbl = "disk"
    lw  = tw(draw, lbl, fnt(9))
    draw.text((pie_cx - lw // 2, pie_cy + pie_r + 5),
              lbl, font=fnt(9), fill=MUTED)

    vline(draw, COL_W, BAR_H + 8, ILI_H - BOT_H - 8, LINE)

    FX    = COL_W + 12
    FW    = ILI_W - FX - 10
    ROW_H = (ILI_H - BAR_H - BOT_H) // 4

    default_activities = [
        {"title": "Reminder",    "subtitle": "Meeting in 15 min",
         "time": time_str,       "color": ORANGE, "online": True},
        {"title": "Inbox",       "subtitle": "3 new messages",
         "time": time_str,       "color": BLUE,   "online": True},
        {"title": "System",      "subtitle": "All services online",
         "time": time_str,       "color": CYAN,   "online": True},
        {"title": "Focus ready", "subtitle": "VS Code queued",
         "time": time_str,       "color": GREEN,  "online": True},
    ]
    items = activities if activities else default_activities

    for i, item in enumerate(items[:4]):
        ry    = BAR_H + i * ROW_H
        color = item.get("color", CYAN)

        if i % 2 == 0:
            draw.rectangle([FX - 4, ry, ILI_W, ry + ROW_H - 1], fill=SURFACE)

        draw.rectangle([FX - 4, ry + 6, FX - 2, ry + ROW_H - 7], fill=color)

        ty = ry + ROW_H // 2 - 11
        draw.text((FX, ty),      item.get("title", ""),
                  font=fnt(11, bold=True), fill=WHITE)
        draw.text((FX, ty + 14), item.get("subtitle", ""),
                  font=fnt(9), fill=MUTED)

        t_str = item.get("time", "")
        t_w   = tw(draw, t_str, fnt(9))
        draw.text((ILI_W - t_w - 14, ty + 14), t_str, font=fnt(9), fill=MUTED)
        status_dot(draw, ILI_W - 7, ry + ROW_H // 2,
                   online=item.get("online", True))

        if i < 3:
            hline(draw, FX, ILI_W, ry + ROW_H - 1, LINE)

    bottom_hint(draw, username)
    return img


# ════════════════════════════════════════════════════════════════════════════════
# APPS GRID
# ════════════════════════════════════════════════════════════════════════════════

APPS_TILES = [
    {"id": SCREEN_EMAILS, "label": "summarize\nmails",  "color": ORANGE},
    {"id": SCREEN_FOCUS,  "label": "focus\nmode",       "color": BLUE},
    {"id": SCREEN_BRIEF,  "label": "brief\nmy day",     "color": CYAN},
    {"id": SCREEN_SYSMON, "label": "system\ncare",      "color": GREEN},
]

def render_apps(data: dict) -> tuple:
    img  = ili_canvas()
    draw = ImageDraw.Draw(img)

    top_bar(draw, "apps")

    PAD    = 6
    tile_w = (ILI_W - PAD * 3) // 2
    tile_h = (ILI_H - BAR_H - PAD * 3) // 2
    hit_rects = []

    for i, tile in enumerate(APPS_TILES):
        col = i % 2
        row = i // 2
        tx  = PAD + col * (tile_w + PAD)
        ty  = BAR_H + PAD + row * (tile_h + PAD)
        tx2 = tx + tile_w
        ty2 = ty + tile_h
        color = tile["color"]

        draw.rectangle([tx, ty, tx2, ty2], fill=SURFACE)

        lines = tile["label"].split("\n")
        lf    = fnt(22, bold=True)
        lh    = 26
        total = len(lines) * lh
        ly    = ty + (tile_h - total) // 2 - 4

        for line in lines:
            lw = tw(draw, line, lf)
            draw.text((tx + (tile_w - lw) // 2, ly), line, font=lf, fill=color)
            ly += lh

        draw.rectangle([tx + 20, ty2 - 5, tx2 - 20, ty2 - 3], fill=color)

        hit_rects.append((tx, ty, tx2, ty2, tile["id"]))

    mid_x = PAD + tile_w + PAD // 2
    mid_y = BAR_H + PAD + tile_h + PAD // 2
    vline(draw, mid_x, BAR_H, ILI_H - BOT_H, LINE)
    hline(draw, 0, ILI_W, mid_y, LINE)

    bottom_hint(draw, "← back")
    return img, hit_rects


# ════════════════════════════════════════════════════════════════════════════════
# BRIEF MY DAY
# ════════════════════════════════════════════════════════════════════════════════

def render_brief(data: dict) -> Image.Image:
    img  = ili_canvas()
    draw = ImageDraw.Draw(img)

    time_str  = data.get("time_str",  "00:00")
    date_str  = data.get("date_str",  "")
    weather   = data.get("weather",   {})
    events    = data.get("events",    [])
    reminders = data.get("reminders", [])

    top_bar(draw, "brief my day", time_str, CYAN)

    y  = BAR_H + 10
    LX = 14

    if date_str:
        draw.text((LX, y), date_str, font=fnt(10), fill=MUTED)
        y += 16

    hline(draw, LX, ILI_W - LX, y, LINE)
    y += 10

    icon = weather.get("icon", "—")
    temp = weather.get("temp", "—")
    desc = weather.get("desc", "")
    draw.text((LX,      y),      icon, font=fnt(24),           fill=WHITE)
    draw.text((LX + 34, y + 2),  temp, font=fnt(18, bold=True), fill=CYAN)
    draw.text((LX + 34, y + 22), desc, font=fnt(9),             fill=MUTED)
    y += 40

    hline(draw, LX, ILI_W - LX, y, LINE)
    y += 10

    draw.text((LX, y), "schedule", font=fnt(9, bold=True), fill=MUTED)
    y += 13

    tag_colors = {"work": BLUE, "break": GREEN, "personal": ORANGE, "focus": MAGENTA}
    default_events = [
        {"time": "09:00", "title": "Morning standup", "tag": "work"},
        {"time": "11:30", "title": "Code review",      "tag": "work"},
        {"time": "14:00", "title": "Lunch",            "tag": "break"},
        {"time": "16:00", "title": "Team sync",        "tag": "work"},
    ]
    for ev in (events or default_events)[:4]:
        tc = tag_colors.get(ev.get("tag", "work"), CYAN)
        draw.rectangle([LX, y + 2, LX + 2, y + 12], fill=tc)
        draw.text((LX + 6,  y), ev.get("time",  ""), font=fnt(10, bold=True), fill=MUTED)
        draw.text((LX + 46, y), ev.get("title", ""), font=fnt(10),            fill=WHITE)
        y += 16

    hline(draw, LX, ILI_W - LX, y, LINE)
    y += 10

    draw.text((LX, y), "reminders", font=fnt(9, bold=True), fill=MUTED)
    y += 13

    default_reminders = ["Check weekly report", "Reply to design team"]
    for rem in (reminders or default_reminders)[:3]:
        dot(draw, LX + 3, y + 5, r=2, color=ORANGE)
        draw.text((LX + 10, y), rem, font=fnt(10), fill=WHITE)
        y += 14

    bottom_hint(draw, "← back")
    return img


# ════════════════════════════════════════════════════════════════════════════════
# SUMMARIZE EMAILS
# ════════════════════════════════════════════════════════════════════════════════

def render_emails(data: dict) -> Image.Image:
    img  = ili_canvas()
    draw = ImageDraw.Draw(img)

    time_str = data.get("time_str",     "00:00")
    summary  = data.get("summary",      "No summary.")
    emails   = data.get("emails",       [])
    unread   = data.get("unread_count",  0)

    top_bar(draw, f"inbox  ·  {unread} unread", time_str, ORANGE)

    y  = BAR_H + 10
    LX = 14

    draw.text((LX, y), "summary", font=fnt(9, bold=True), fill=MUTED)
    y += 13

    words, line = summary.split(), ""
    for word in words:
        if len(line) + len(word) + 1 <= 38:
            line += (" " if line else "") + word
        else:
            draw.text((LX, y), line, font=fnt(10), fill=WHITE)
            y += 13
            line = word
        if y > BAR_H + 70:
            break
    if line:
        draw.text((LX, y), line, font=fnt(10), fill=WHITE)
        y += 13

    hline(draw, LX, ILI_W - LX, y + 4, LINE)
    y += 14

    draw.text((LX, y), "messages", font=fnt(9, bold=True), fill=MUTED)
    y += 13

    default_emails = [
        {"from": "boss@work.com",  "subject": "Q4 review",    "time": "08:14"},
        {"from": "noreply@gh.com", "subject": "PR merged",    "time": "09:02"},
        {"from": "team@corp.com",  "subject": "Daily digest", "time": "09:30"},
        {"from": "alerts@sys.io",  "subject": "Disk warning", "time": "10:01"},
    ]
    for i, mail in enumerate((emails or default_emails)[:5]):
        if i % 2 == 0:
            draw.rectangle([0, y - 1, ILI_W, y + 22], fill=SURFACE)
        dot(draw, LX + 2, y + 6, r=3, color=BLUE)
        draw.text((LX + 10, y),
                  mail.get("from", ""), font=fnt(9, bold=True), fill=CYAN)
        t_w = tw(draw, mail.get("time", ""), fnt(9))
        draw.text((ILI_W - t_w - 10, y),
                  mail.get("time", ""), font=fnt(9), fill=MUTED)
        draw.text((LX + 10, y + 11),
                  mail.get("subject", ""), font=fnt(9), fill=WHITE)
        y += 24

    bottom_hint(draw, "← back")
    return img


# ════════════════════════════════════════════════════════════════════════════════
# SYSTEM CARE
# ════════════════════════════════════════════════════════════════════════════════

def render_sysmon(data: dict) -> Image.Image:
    img  = ili_canvas()
    draw = ImageDraw.Draw(img)

    time_str   = data.get("time_str",   "00:00")
    deck       = data.get("deck",   {"cpu":40,"ram":28,"disk_used":40,"disk_total":64,"fan":35})
    server     = data.get("server", {"cpu":40,"gpu":0, "ram":80,"disk_used":256,"disk_total":500})
    temp_info  = data.get("temp_files", {"count":0, "size_mb":0})
    clean_done = data.get("clean_done", False)

    top_bar(draw, "system care", time_str, GREEN)

    LX    = 14
    MID   = ILI_W // 2
    BAR_W = 68
    PB_H  = 4
    y     = BAR_H + 10

    def stat_col(x, label, online, stats, y_start):
        draw.text((x, y_start), label, font=fnt(10, bold=True), fill=WHITE)
        status_dot(draw,
                   x + tw(draw, label, fnt(10, True)) + 8,
                   y_start + 6, online=online)
        y2 = y_start + 16
        for s_label, frac, value, color in stats:
            draw.text((x,      y2), s_label, font=fnt(9),            fill=MUTED)
            draw.text((x + 30, y2), value,   font=fnt(9, bold=True), fill=WHITE)
            progress_bar(draw, x, y2 + 12, BAR_W, PB_H, frac, color)
            y2 += 24
        return y2

    du, dt  = _safe(deck,   "disk_used", "DISK_USED",  "used",  default=0), \
              _safe(deck,   "disk_total","DISK_TOTAL", "total", default=64)
    su, st2 = _safe(server, "disk_used", "DISK_USED",  "used",  default=0), \
              _safe(server, "disk_total","DISK_TOTAL", "total", default=500)

    d_cpu = _safe(deck,   "cpu", "CPU", default=0)
    d_ram = _safe(deck,   "ram", "RAM", "mem", default=0)
    d_fan = _safe(deck,   "fan", "FAN", default=0)
    s_cpu = _safe(server, "cpu", "CPU", default=0)
    s_gpu = _safe(server, "gpu", "GPU", default=0)
    s_ram = _safe(server, "ram", "RAM", "mem", default=0)

    deck_stats = [
        ("cpu",  d_cpu / 100, f"{d_cpu}%",   CYAN),
        ("ram",  d_ram / 100, f"{d_ram}%",   BLUE),
        ("disk", du / max(dt, 1),  f"{du}/{dt}G",  GREEN),
        ("fan",  d_fan / 100, f"{d_fan}%",   YELLOW),
    ]
    server_stats = [
        ("cpu",  s_cpu / 100, f"{s_cpu}%",   CYAN),
        ("gpu",  s_gpu / 100, f"{s_gpu}%",   MAGENTA),
        ("ram",  s_ram / 100, f"{s_ram}%",   BLUE),
        ("disk", su / max(st2, 1), f"{su}/{st2}G", GREEN),
    ]

    by1 = stat_col(LX,       "deck",   True, deck_stats,   y)
    by2 = stat_col(MID + LX, "server", True, server_stats, y)
    vline(draw, MID, BAR_H + 6, max(by1, by2) + 4, LINE)

    cy = max(by1, by2) + 10
    hline(draw, LX, ILI_W - LX, cy, LINE)
    cy += 8

    cnt = temp_info.get("count",   0)
    mb  = temp_info.get("size_mb", 0)
    draw.text((LX, cy),
              f"temp:  {cnt} files  /  {mb} MB",
              font=fnt(10), fill=MUTED)
    cy += 16

    if clean_done:
        draw.text((LX, cy), "✓  cleaned", font=fnt(10, bold=True), fill=GREEN)
    else:
        draw.text((LX, cy), "tap to clean", font=fnt(10), fill=YELLOW)

    bottom_hint(draw, "← back")
    return img


# ════════════════════════════════════════════════════════════════════════════════
# FOCUS MODE
# ════════════════════════════════════════════════════════════════════════════════

def render_focus(data: dict) -> Image.Image:
    img  = ili_canvas()
    draw = ImageDraw.Draw(img)

    time_str     = data.get("time_str",     "00:00")
    session_mins = data.get("session_mins", 25)
    elapsed_mins = data.get("elapsed_mins", 0)
    app_name     = data.get("app_name",     "")
    active       = data.get("active",       False)
    message      = data.get("message",      "")

    top_bar(draw, "focus", time_str, MAGENTA)

    frac      = elapsed_mins / max(1, session_mins)
    remaining = max(0, session_mins - elapsed_mins)
    LX        = 30

    # ── Timer — sits comfortably below top bar ────────────────────────────────
    timer_str = f"{remaining:02d}:00"
    tf  = fnt(54, bold=True)
    t_w = tw(draw, timer_str, tf)
    t_h = th(draw, timer_str, tf)
    timer_y = BAR_H + 22
    draw.text(((ILI_W - t_w) // 2, timer_y),
              timer_str, font=tf, fill=WHITE)

    # ── Progress bar — 18px below timer ──────────────────────────────────────
    pb_y = timer_y + t_h + 18
    progress_bar(draw, LX, pb_y, ILI_W - LX * 2, 5, frac, MAGENTA)

    # ── Status row — 22px below bar ───────────────────────────────────────────
    my      = pb_y + 26
    s_color = GREEN if active else MUTED
    status_dot(draw, LX, my + 5, online=active)
    draw.text((LX + 12, my),
              "active" if active else "idle",
              font=fnt(11), fill=s_color)

    if app_name:
        a_w = tw(draw, app_name, fnt(11, bold=True))
        draw.text((ILI_W - a_w - LX, my),
                  app_name, font=fnt(11, bold=True), fill=CYAN)

    # ── Notes — 20px below status ─────────────────────────────────────────────
    ny = my + 26
    if active:
        draw.text((LX, ny),
                  "windows closed  ·  notifications off",
                  font=fnt(9), fill=MUTED)
        ny += 18

    # ── Optional message ──────────────────────────────────────────────────────
    if message and ny + 10 < ILI_H - BOT_H:
        draw.text((LX, ny), message, font=fnt(9), fill=YELLOW)

    bottom_hint(draw, "← back / end session")
    return img


# ════════════════════════════════════════════════════════════════════════════════
# ST7735  –  STATUS WIDGET
# ════════════════════════════════════════════════════════════════════════════════

def render_st_status(data: dict) -> Image.Image:
    """
    ST7735 160×128 landscape — larger, clearer elements.
    Top 2/3: DECK (left) | SERVER (right)
    Bottom 1/3: weather full width
    """
    img  = st_canvas()
    draw = ImageDraw.Draw(img)

    deck          = data.get("deck",   {})
    server        = data.get("server", {})
    weather       = data.get("weather", {})
    deck_online   = data.get("deck_online",   True)
    server_online = data.get("server_online", True)

    d_cpu  = _safe(deck,   "cpu",  "CPU",  default=0)
    d_fan  = _safe(deck,   "fan",  "FAN",  default=0)
    d_ram  = _safe(deck,   "ram",  "RAM",  "mem", default=0)
    d_du   = _safe(deck,   "disk_used",  "DISK_USED",  "used",  default=0)
    d_dt   = _safe(deck,   "disk_total", "DISK_TOTAL", "total", default=64)

    s_cpu  = _safe(server, "cpu",  "CPU",  default=0)
    s_gpu  = _safe(server, "gpu",  "GPU",  default=0)
    s_ram  = _safe(server, "ram",  "RAM",  "mem", default=0)
    s_du   = _safe(server, "disk_used",  "DISK_USED",  "used",  default=0)
    s_dt   = _safe(server, "disk_total", "DISK_TOTAL", "total", default=500)

    w_icon   = _safe(weather, "icon",    "Icon",   default="~")
    w_hi     = _safe(weather, "temp_hi", "high",   "hi",  default="--")
    w_lo     = _safe(weather, "temp_lo", "low",    "lo",  default="--")
    w_online = _safe(weather, "online",  "Online", default=True)

    HW    = ST_W // 2    # 80  — column midpoint
    TOP_H = 86           # stats occupy top 86px, weather gets 42px

    # ── Structure lines ───────────────────────────────────────────────────────
    vline(draw, HW,   0,    TOP_H, LINE)
    hline(draw, 0,    ST_W, TOP_H, LINE)

    # ── DECK header ───────────────────────────────────────────────────────────
    draw.text((4, 2), "DECK", font=fnt(9, bold=True), fill=CYAN)
    status_dot(draw, HW - 8, 7, online=deck_online)
    hline(draw, 2, HW - 2, 15, LINE)

    # ── SERVER header ─────────────────────────────────────────────────────────
    draw.text((HW + 4, 2), "SERVER", font=fnt(9, bold=True), fill=CYAN)
    status_dot(draw, ST_W - 6, 7, online=server_online)
    hline(draw, HW + 2, ST_W - 2, 15, LINE)

    # ── Stat rows ─────────────────────────────────────────────────────────────
    def stat_row(x, y, label, value, color):
        """One stat: colour dot + label + value on same line."""
        dot(draw, x + 3, y + 5, r=3, color=color)
        draw.text((x + 10, y), label,
                  font=fnt(9, bold=True), fill=MUTED)
        draw.text((x + 10, y + 11), value,
                  font=fnt(10, bold=True), fill=WHITE)
        return y + 24

    sy = 18
    sy = stat_row(2,       sy, "CPU",  f"{d_cpu}°C",       CYAN)
    sy = stat_row(2,       sy, "FAN",  f"{d_fan}%",        YELLOW)
    sy = stat_row(2,       sy, "DISK", f"{d_du}/{d_dt}G",  GREEN)

    sy = 18
    sy = stat_row(HW + 2,  sy, "CPU",  f"{s_cpu}°C",       CYAN)
    sy = stat_row(HW + 2,  sy, "GPU",  f"{s_gpu}%",        MAGENTA)
    sy = stat_row(HW + 2,  sy, "DISK", f"{s_du}/{s_dt}G",  GREEN)

    # ── WEATHER panel ─────────────────────────────────────────────────────────
    wy = TOP_H + 3
    draw.text((4, wy), "weather", font=fnt(8, bold=True), fill=MUTED)
    status_dot(draw, ST_W - 6, wy + 5, online=w_online)
    hline(draw, 2, ST_W - 2, wy + 14, LINE)

    draw.text((5,  wy + 16), str(w_icon),
              font=fnt(18), fill=WHITE)
    draw.text((30, wy + 17), f"{w_hi}\u00b0/{w_lo}\u00b0 C",
              font=fnt(16, bold=True), fill=WHITE)

    return img


# ════════════════════════════════════════════════════════════════════════════════
# TOUCH HELPERS
# ════════════════════════════════════════════════════════════════════════════════

def hit_test(tx, ty, regions):
    for x0, y0, x1, y1, payload in regions:
        if x0 <= tx <= x1 and y0 <= ty <= y1:
            return payload
    return None

DASHBOARD_PIE_REGION = [(14, 82, 96, 162, SCREEN_APPS)]
# Back tap zone — bottom-left corner, matches the "← back" text position
BACK_REGION          = [(0, ILI_H - BOT_H, 100, ILI_H, SCREEN_DASHBOARD)]


# ════════════════════════════════════════════════════════════════════════════════
# RENDER TEST
# ════════════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    import os
    out = "/tmp/and-desk-preview"
    os.makedirs(out, exist_ok=True)

    now  = time.strftime("%H:%M")
    date = time.strftime("%a, %d %b %Y")

    renders = [
        ("ili_dashboard.png", lambda: render_dashboard(
            {"time_str": now, "date_str": date, "username": "tork"})),
        ("ili_apps.png",      lambda: render_apps({})[0]),
        ("ili_brief.png",     lambda: render_brief(
            {"time_str": now, "date_str": date,
             "weather": {"icon": "~", "temp": "24deg", "desc": "Cloudy"}})),
        ("ili_emails.png",    lambda: render_emails(
            {"time_str": now, "unread_count": 3,
             "summary": "Three messages: Q4 review, merged PR, team digest."})),
        ("ili_sysmon.png",    lambda: render_sysmon(
            {"time_str": now, "temp_files": {"count": 127, "size_mb": 340}})),
        ("ili_focus.png",     lambda: render_focus(
            {"time_str": now, "session_mins": 25, "elapsed_mins": 8,
             "app_name": "VS Code", "active": True})),
        ("st_status.png",     lambda: render_st_status({})),
    ]

    for fname, fn in renders:
        img = fn()
        img.save(f"{out}/{fname}")
        print(f"[saved] {out}/{fname}")
    print("done.")
