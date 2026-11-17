"""
Spin the Wheel – Color Picker
The wheel holds COLORS. Add the colors, add the names, then each person spins:
the color the pointer lands on is the color that person gets (e.g. shirt to wear).

Run:  python main.py
"""

import math
import os
import random
import secrets
import struct
import sys
import tempfile
import time
import tkinter as tk
import wave
from tkinter import colorchooser, filedialog

import customtkinter as ctk

os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
try:
    import pygame
except ImportError:  # sound falls back to winsound (Windows) or silence
    pygame = None

try:
    import winsound
except ImportError:
    winsound = None


# --------------------------------------------------------------------------- #
# Theme
# --------------------------------------------------------------------------- #
BG = "#161826"
PANEL = "#1f2235"
CARD = "#2a2e47"
CARD_HOVER = "#383d5e"
TEXT = "#f1f2f8"
MUTED = "#9aa0bf"
ACCENT = "#7c5cff"
ACCENT_HOVER = "#6846f0"
SPIN_COLOR = "#ff4d6d"
SPIN_HOVER = "#e63b5b"
SUCCESS = "#4ade80"
ERROR = "#ff6b81"

BASIC_COLORS = ["Red", "Blue", "Green", "Yellow"]
CONFETTI_COLORS = ["#FF6B6B", "#FFD43B", "#69DB7C", "#4DABF7", "#DA77F2",
                   "#FFA94D", "#FFFFFF", "#38D9A9", "#F783AC"]

FONT = "Segoe UI"
MAX_NAME_LEN = 30
FRAME_MS = 15


# --------------------------------------------------------------------------- #
# Assets / sound
# --------------------------------------------------------------------------- #
def _app_dir():
    """Folder holding bundled files (works for PyInstaller one-file builds)."""
    return getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))


def _write_wav(path, samples, rate=44100):
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(b"".join(
            struct.pack("<h", int(max(-1.0, min(1.0, s)) * 32767)) for s in samples))


def _tick_samples(rate=44100):
    n = int(rate * 0.035)
    return [0.6 * math.sin(2 * math.pi * 1700 * t / rate) * math.exp(-t / (rate * 0.006))
            for t in range(n)]


def _fanfare_samples(rate=44100):
    notes = [(523.25, 0.11), (659.25, 0.11), (783.99, 0.11), (1046.50, 0.55)]
    out = []
    for freq, dur in notes:
        n = int(rate * dur)
        for t in range(n):
            env = min(1.0, t / (rate * 0.01)) * math.exp(-t / (rate * dur * 0.6))
            s = math.sin(2 * math.pi * freq * t / rate) + 0.3 * math.sin(4 * math.pi * freq * t / rate)
            out.append(0.45 * env * s)
    return out


def ensure_assets():
    """Return paths to spin.wav / winner.wav, generating them if missing."""
    folder = os.path.join(_app_dir(), "assets")
    generators = {"spin.wav": _tick_samples, "winner.wav": _fanfare_samples}
    paths = {}
    for filename, gen in generators.items():
        path = os.path.join(folder, filename)
        if not os.path.exists(path):
            try:
                os.makedirs(folder, exist_ok=True)
                _write_wav(path, gen())
            except OSError:  # read-only location: fall back to temp dir
                path = os.path.join(tempfile.gettempdir(), "spin_the_wheel_" + filename)
                if not os.path.exists(path):
                    _write_wav(path, gen())
        paths[filename.split(".")[0]] = path
    return paths


class SoundPlayer:
    def __init__(self, files):
        self.files = files
        self.muted = False
        self.backend = None
        self.sounds = {}
        if pygame is not None:
            try:
                pygame.mixer.init(frequency=44100, size=-16, channels=2, buffer=512)
                self.sounds = {k: pygame.mixer.Sound(p) for k, p in files.items()}
                self.backend = "pygame"
            except Exception:
                self.sounds = {}
        if self.backend is None and winsound is not None:
            self.backend = "winsound"

    def play(self, key):
        if self.muted or self.backend is None:
            return
        try:
            if self.backend == "pygame":
                self.sounds[key].play()
            else:
                winsound.PlaySound(self.files[key], winsound.SND_FILENAME
                                   | winsound.SND_ASYNC | winsound.SND_NODEFAULT)
        except Exception:
            pass

    def shutdown(self):
        if self.backend == "pygame":
            try:
                pygame.mixer.quit()
            except Exception:
                pass


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def text_color_for(hex_color):
    r, g, b = (int(hex_color[k:k + 2], 16) for k in (1, 3, 5))
    luminance = 0.299 * r + 0.587 * g + 0.114 * b
    return "#1b1b2b" if luminance > 165 else "#ffffff"


def ease_out(t):
    """Quartic ease-out: fast start, long gradual slowdown."""
    return 1 - (1 - t) ** 4


def clean_text(raw):
    return " ".join(raw.split())[:MAX_NAME_LEN]


# --------------------------------------------------------------------------- #
# Results image (needs Pillow)
# --------------------------------------------------------------------------- #
def _load_font(bold, size):
    from PIL import ImageFont
    for name in (("segoeuib.ttf", "arialbd.ttf", "DejaVuSans-Bold.ttf") if bold
                 else ("segoeui.ttf", "arial.ttf", "DejaVuSans.ttf")):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default(size)


def render_results_image(groups, total):
    """Draw one card per color listing the people who got it. Returns a PIL Image."""
    from PIL import Image, ImageDraw

    title_f, sub_f = _load_font(True, 40), _load_font(False, 20)
    head_f, name_f, small_f = _load_font(True, 24), _load_font(False, 21), _load_font(False, 16)

    margin, gap, card_w = 48, 24, 300
    head_h, row_h, card_pad = 64, 36, 16
    cols = max(1, min(4, len(groups)))
    rows = [groups[i:i + cols] for i in range(0, len(groups), cols)]
    row_heights = [head_h + card_pad * 2 + max(1, max(len(g[2]) for g in r)) * row_h
                   for r in rows]

    width = margin * 2 + cols * card_w + (cols - 1) * gap
    top = 150
    height = top + sum(row_heights) + gap * (len(rows) - 1) + margin + 30
    img = Image.new("RGB", (width, height), BG)
    d = ImageDraw.Draw(img)

    d.text((margin, 44), "Color Wheel Results", font=title_f, fill=TEXT)
    d.text((margin, 98), f"{total} people  ·  {len(groups)} colors  ·  "
                         f"{time.strftime('%B %d, %Y  %I:%M %p')}", font=sub_f, fill=MUTED)

    y = top
    for r, rh in zip(rows, row_heights):
        x = margin
        for label, color, names in r:
            d.rounded_rectangle((x, y, x + card_w, y + rh), radius=18, fill=CARD)
            d.rounded_rectangle((x, y, x + card_w, y + head_h), radius=18, fill=color)
            d.rectangle((x, y + head_h - 18, x + card_w, y + head_h), fill=color)
            fg = text_color_for(color)
            d.text((x + 18, y + head_h / 2), label.upper(), font=head_f, fill=fg, anchor="lm")
            d.text((x + card_w - 18, y + head_h / 2), str(len(names)), font=head_f, fill=fg,
                   anchor="rm")
            ny = y + head_h + card_pad
            if not names:
                d.text((x + 18, ny + row_h / 2), "—", font=name_f, fill=MUTED, anchor="lm")
            for k, name in enumerate(names, 1):
                d.text((x + 18, ny + row_h / 2), f"{k}.", font=name_f, fill=MUTED, anchor="lm")
                room = card_w - 52 - 14
                while len(name) > 1 and d.textlength(name, font=name_f) > room:
                    name = name[:-2].rstrip() + "…"
                d.text((x + 52, ny + row_h / 2), name, font=name_f, fill=TEXT, anchor="lm")
                ny += row_h
            x += card_w + gap
        y += rh + gap

    d.text((width - margin, height - 28), "Spin the Wheel – Color Picker", font=small_f,
           fill=MUTED, anchor="rm")
    return img


# --------------------------------------------------------------------------- #
# Application
# --------------------------------------------------------------------------- #
class SpinWheelApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        ctk.set_appearance_mode("dark")
        self.title("Spin the Wheel – Color Picker")
        self.geometry("1400x820")
        self.minsize(1150, 660)
        self.configure(fg_color=BG)

        self.sound = SoundPlayer(ensure_assets())

        self.colors = []         # [(label, hex)] — the slices on the wheel
        self.waiting = []        # names that still need to spin
        self.results = []        # [(name, label, hex)] in spin order
        self.spinner = None      # name of the person currently spinning
        self.last_result = None  # (name, label, hex) of the most recent spin
        self.angle = 0.0         # wheel rotation in degrees (Tk: counter-clockwise)
        self.spinning = False
        self.spin_job = None
        self.show_banner = False
        self.particles = []
        self.confetti_job = None
        self.confetti_t0 = 0.0
        self.last_tick_index = None
        self.last_tick_time = 0.0

        self._build_ui()
        self.refresh()
        self.protocol("WM_DELETE_WINDOW", self.on_close)

    # ------------------------------------------------------------------ UI --
    def _build_ui(self):
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)
        self._build_left()
        self._build_center()
        self._build_right()

    def _button(self, parent, text, command, primary=False, **kw):
        opts = dict(height=36, font=(FONT, 13, "bold" if primary else "normal"),
                    fg_color=ACCENT if primary else CARD,
                    hover_color=ACCENT_HOVER if primary else CARD_HOVER)
        opts.update(kw)
        return ctk.CTkButton(parent, text=text, command=command, **opts)

    def _heading(self, parent, text):
        ctk.CTkLabel(parent, text=text, font=(FONT, 15, "bold"),
                     text_color=TEXT).pack(anchor="w", padx=18, pady=(10, 0))

    def _listbox(self, parent, height):
        frame = ctk.CTkFrame(parent, fg_color=CARD, corner_radius=10)
        frame.pack(fill="x", padx=18, pady=(6, 8))
        lb = tk.Listbox(frame, height=height, font=(FONT, 12), bg=CARD, fg=TEXT, bd=0,
                        highlightthickness=0, selectbackground=ACCENT,
                        selectforeground="#ffffff", activestyle="none",
                        exportselection=False)
        lb.pack(side="left", fill="both", expand=True, padx=(10, 0), pady=8)
        scroll = ctk.CTkScrollbar(frame, command=lb.yview)
        scroll.pack(side="right", fill="y", pady=6)
        lb.configure(yscrollcommand=scroll.set)
        return lb

    def _build_left(self):
        side = ctk.CTkScrollableFrame(self, width=330, fg_color=PANEL, corner_radius=0)
        side.grid(row=0, column=0, sticky="ns")
        pad = {"padx": 18}

        ctk.CTkLabel(side, text="🎨 Spin the Wheel", font=(FONT, 26, "bold"),
                     text_color=TEXT).pack(anchor="w", pady=(14, 0), **pad)
        ctk.CTkLabel(side, text="Spin to get your color", font=(FONT, 14),
                     text_color=MUTED).pack(anchor="w", pady=(0, 4), **pad)

        # ---- Step 1: colors -------------------------------------------------
        self._heading(side, "1. Colors on the wheel")
        ctk.CTkLabel(side, text="Type a color name (Red, Pink, Navy…) or a hex code (#FF8800)",
                     font=(FONT, 11), text_color=MUTED, wraplength=290,
                     justify="left").pack(anchor="w", **pad)
        row = ctk.CTkFrame(side, fg_color="transparent")
        row.pack(fill="x", pady=(6, 6), **pad)
        self.color_entry = ctk.CTkEntry(row, placeholder_text="Type a color…", height=36,
                                        font=(FONT, 13), fg_color=CARD, border_width=0)
        self.color_entry.pack(side="left", fill="x", expand=True, padx=(0, 6))
        self.color_entry.bind("<Return>", lambda e: self.add_color())
        self.add_color_btn = self._button(row, "Add", self.add_color, primary=True, width=58)
        self.add_color_btn.pack(side="left")
        self.pick_color_btn = self._button(row, "🎨", self.pick_color, width=40)
        self.pick_color_btn.pack(side="left", padx=(6, 0))

        self.basic_btn = self._button(side, "Add Red, Blue, Green, Yellow", self.add_basic_colors)
        self.basic_btn.pack(fill="x", **pad)

        self.balance_var = tk.BooleanVar(value=True)
        self.balance_switch = ctk.CTkSwitch(
            side, text="⚖ Balanced colors", variable=self.balance_var,
            font=(FONT, 13, "bold"), text_color=TEXT, progress_color=ACCENT,
            command=self.on_balance_toggle)
        self.balance_switch.pack(anchor="w", pady=(10, 0), **pad)
        ctk.CTkLabel(side, text="Every color ends up with the same number of people, but "
                                "the order stays random — colors can repeat back-to-back.",
                     font=(FONT, 11), text_color=MUTED, wraplength=290,
                     justify="left").pack(anchor="w", **pad)

        self.color_count_label = ctk.CTkLabel(side, text="Colors: 0", font=(FONT, 13, "bold"),
                                              text_color=TEXT)
        self.color_count_label.pack(anchor="w", pady=(8, 0), **pad)
        self.color_list = self._listbox(side, 5)
        self.color_list.bind("<Delete>", lambda e: self.remove_color())

        crow = ctk.CTkFrame(side, fg_color="transparent")
        crow.pack(fill="x", **pad)
        crow.grid_columnconfigure((0, 1), weight=1, uniform="c")
        self.remove_color_btn = self._button(crow, "Remove Color", self.remove_color)
        self.remove_color_btn.grid(row=0, column=0, sticky="ew", padx=(0, 4))
        self.clear_colors_btn = self._button(crow, "Clear Colors", self.clear_colors)
        self.clear_colors_btn.grid(row=0, column=1, sticky="ew", padx=(4, 0))

        # ---- Step 2: names --------------------------------------------------
        self._heading(side, "2. Names (one per line)")
        self.textbox = ctk.CTkTextbox(side, height=90, font=(FONT, 13), fg_color=CARD,
                                      border_width=0, corner_radius=10)
        self.textbox.pack(fill="x", pady=(6, 6), **pad)
        self.add_names_btn = self._button(side, "Add Names", self.add_names, primary=True)
        self.add_names_btn.pack(fill="x", **pad)

        self.name_count_label = ctk.CTkLabel(side, text="Waiting to spin: 0",
                                             font=(FONT, 13, "bold"), text_color=TEXT)
        self.name_count_label.pack(anchor="w", pady=(8, 0), **pad)
        ctk.CTkLabel(side, text="Click a name to choose who spins next.", font=(FONT, 11),
                     text_color=MUTED).pack(anchor="w", **pad)
        self.name_list = self._listbox(side, 6)
        self.name_list.bind("<Delete>", lambda e: self.remove_name())
        self.name_list.bind("<<ListboxSelect>>", lambda e: self.update_next_label())

        self.shuffle_btn = self._button(side, "🔀 Shuffle Order", self.shuffle_names,
                                        primary=True)
        self.shuffle_btn.pack(fill="x", pady=(0, 6), **pad)

        nrow = ctk.CTkFrame(side, fg_color="transparent")
        nrow.pack(fill="x", **pad)
        nrow.grid_columnconfigure((0, 1), weight=1, uniform="c")
        self.remove_name_btn = self._button(nrow, "Remove Name", self.remove_name)
        self.remove_name_btn.grid(row=0, column=0, sticky="ew", padx=(0, 4))
        self.clear_names_btn = self._button(nrow, "Clear Names", self.clear_names)
        self.clear_names_btn.grid(row=0, column=1, sticky="ew", padx=(4, 0))

        self.mute_btn = self._button(side, "🔊 Sound: On", self.toggle_mute)
        self.mute_btn.pack(fill="x", pady=(14, 0), **pad)

        self.status_label = ctk.CTkLabel(side, text="", font=(FONT, 12), text_color=MUTED,
                                         wraplength=290, justify="left")
        self.status_label.pack(anchor="w", pady=(10, 20), **pad)

    def _build_center(self):
        main = ctk.CTkFrame(self, fg_color=BG, corner_radius=0)
        main.grid(row=0, column=1, sticky="nsew")

        btn_row = ctk.CTkFrame(main, fg_color="transparent")
        btn_row.pack(side="bottom", pady=(4, 22))
        self.spin_btn = ctk.CTkButton(
            btn_row, text="SPIN", width=260, height=66, corner_radius=33,
            font=(FONT, 28, "bold"), fg_color=SPIN_COLOR, hover_color=SPIN_HOVER,
            command=self.spin)
        self.spin_btn.pack()

        self.result_label = ctk.CTkLabel(main, text="", font=(FONT, 20, "bold"),
                                         text_color=MUTED)
        self.result_label.pack(side="bottom", pady=(0, 6))

        self.canvas = tk.Canvas(main, bg=BG, highlightthickness=0)
        self.canvas.pack(fill="both", expand=True, padx=20, pady=(20, 6))
        self.canvas.bind("<Configure>", lambda e: self.render())
        self.canvas.bind("<Button-1>", lambda e: self.hide_banner())

    def _build_right(self):
        right = ctk.CTkFrame(self, width=300, fg_color=PANEL, corner_radius=0)
        right.grid(row=0, column=2, sticky="ns")
        right.pack_propagate(False)

        ctk.CTkLabel(right, text="Results", font=(FONT, 20, "bold"),
                     text_color=TEXT).pack(anchor="w", padx=18, pady=(18, 0))
        ctk.CTkLabel(right, text="Name → color they got", font=(FONT, 12),
                     text_color=MUTED).pack(anchor="w", padx=18)

        self.summary_label = ctk.CTkLabel(right, text="", font=(FONT, 12), text_color=MUTED,
                                          wraplength=260, justify="left")
        self.summary_label.pack(side="bottom", anchor="w", padx=18, pady=(0, 18))
        self.reset_btn = self._button(right, "↺ Reset Results (spin again)", self.reset_results)
        self.reset_btn.pack(side="bottom", fill="x", padx=18, pady=(0, 10))
        self.save_img_btn = self._button(right, "💾 Save Results as Image",
                                         self.save_results_image, primary=True)
        self.save_img_btn.pack(side="bottom", fill="x", padx=18, pady=(0, 8))

        frame = ctk.CTkFrame(right, fg_color=CARD, corner_radius=10)
        frame.pack(fill="both", expand=True, padx=18, pady=(10, 10))
        self.result_list = tk.Listbox(
            frame, font=(FONT, 13, "bold"), bg=CARD, fg=TEXT, bd=0, highlightthickness=0,
            activestyle="none", exportselection=False, selectbackground=CARD)
        self.result_list.pack(side="left", fill="both", expand=True, padx=(8, 0), pady=8)
        scroll = ctk.CTkScrollbar(frame, command=self.result_list.yview)
        scroll.pack(side="right", fill="y", pady=6)
        self.result_list.configure(yscrollcommand=scroll.set)

    # ------------------------------------------------------------ Drawing --
    def _geometry(self):
        w = max(self.canvas.winfo_width(), 50)
        h = max(self.canvas.winfo_height(), 50)
        r = max(40, min(w, h) / 2 - 28)
        return w, h, w / 2, h / 2 + 8, r

    def render(self):
        c = self.canvas
        c.delete("wheel", "banner")
        w, h, cx, cy, r = self._geometry()

        # Outer rim with decorative lights
        rim = r + 12
        c.create_oval(cx - rim, cy - rim, cx + rim, cy + rim, fill="#2c3150",
                      outline="#3b4170", width=2, tags="wheel")
        for k in range(24):
            a = math.radians(k * 15)
            lx, ly = cx + (r + 6) * math.cos(a), cy - (r + 6) * math.sin(a)
            dot = max(2.5, r * 0.012)
            c.create_oval(lx - dot, ly - dot, lx + dot, ly + dot,
                          fill="#ffe066" if k % 2 else "#ffffff", outline="", tags="wheel")

        n = len(self.colors)
        if n == 0:
            c.create_oval(cx - r, cy - r, cx + r, cy + r, fill=CARD, outline="#3b4170",
                          width=2, tags="wheel")
            c.create_text(cx, cy, text="Add colors to\nfill the wheel", fill=MUTED,
                          font=(FONT, -int(max(14, r * 0.08)), "bold"),
                          justify="center", tags="wheel")
        elif n == 1:
            label, color = self.colors[0]
            c.create_oval(cx - r, cy - r, cx + r, cy + r, fill=color, outline="#ffffff",
                          width=2, tags="wheel")
            c.create_text(cx, cy - r * 0.55, text=self._fit(label, r * 0.9, r * 0.1),
                          fill=text_color_for(color), font=(FONT, -int(r * 0.1), "bold"),
                          tags="wheel")
        else:
            self._draw_segments(cx, cy, r, n)

        # Hub
        hub = r * 0.13
        c.create_oval(cx - hub, cy - hub, cx + hub, cy + hub, fill="#ffffff",
                      outline="#2c3150", width=3, tags="wheel")
        c.create_oval(cx - hub * 0.45, cy - hub * 0.45, cx + hub * 0.45, cy + hub * 0.45,
                      fill=ACCENT, outline="", tags="wheel")

        # Fixed pointer at the top (points down into the wheel)
        pw = max(14, r * 0.075)
        top = cy - r - 18
        c.create_polygon(cx - pw, top, cx + pw, top, cx, cy - r + pw * 1.6,
                         fill="#ffffff", outline="#1b1b2b", width=2, tags="wheel")
        c.create_oval(cx - pw * 0.45, top - pw * 0.25, cx + pw * 0.45, top + pw * 0.65,
                      fill=SPIN_COLOR, outline="", tags="wheel")

        if self.show_banner and self.last_result:
            self._draw_banner(w, h, cx, cy, r)
        c.tag_raise("confetti")
        c.tag_raise("banner")

    def _draw_segments(self, cx, cy, r, n):
        c = self.canvas
        seg = 360.0 / n
        arc_len = math.radians(seg) * r * 0.62
        font_px = int(max(7, min(r * 0.075, arc_len * 0.55)))
        radial_room = r * 0.58
        outline_w = 2 if n < 60 else 1
        for i, (label, color) in enumerate(self.colors):
            start = self.angle + i * seg
            c.create_arc(cx - r, cy - r, cx + r, cy + r, start=start, extent=seg,
                         fill=color, outline="#ffffff", width=outline_w,
                         style=tk.PIESLICE, tags="wheel")
            mid = start + seg / 2
            rad = math.radians(mid)
            tx = cx + r * 0.62 * math.cos(rad)
            ty = cy - r * 0.62 * math.sin(rad)
            text_angle = mid % 360
            if 90 < text_angle < 270:  # keep text upright-ish on the left side
                text_angle = (text_angle + 180) % 360
            c.create_text(tx, ty, text=self._fit(label, radial_room, font_px), angle=text_angle,
                          fill=text_color_for(color), font=(FONT, -font_px, "bold"),
                          tags="wheel")

    @staticmethod
    def _fit(text, room_px, font_px):
        max_chars = max(3, int(room_px / (font_px * 0.62)))
        return text if len(text) <= max_chars else text[:max_chars - 1] + "…"

    def _draw_banner(self, w, h, cx, cy, r):
        c = self.canvas
        name, label, color = self.last_result
        title_px = int(max(16, r * 0.075))
        big_px = int(max(22, r * 0.13))

        items = []
        y = cy - big_px * 1.6
        if name:
            items.append(c.create_text(cx, y, text=name, fill="#ffffff",
                                       font=(FONT, -big_px, "bold"), width=w * 0.7,
                                       justify="center", tags="banner"))
            y += big_px * 1.1
            items.append(c.create_text(cx, y, text="gets the color", fill=MUTED,
                                       font=(FONT, -title_px), tags="banner"))
        else:
            items.append(c.create_text(cx, y + big_px * 0.6, text="🎉 The color is 🎉",
                                       fill="#ffe066", font=(FONT, -title_px, "bold"),
                                       tags="banner"))
        y += title_px * 1.1 + big_px * 0.9
        sw_w, sw_h = big_px * 5.5, big_px * 1.6
        swatch = self._rounded_rect(cx - sw_w / 2, y - sw_h / 2, cx + sw_w / 2, y + sw_h / 2,
                                    18, fill=color, outline="#ffffff", width=3, tags="banner")
        items.append(swatch)
        items.append(c.create_text(cx, y, text=label.upper(), fill=text_color_for(color),
                                   font=(FONT, -big_px, "bold"), tags="banner"))

        boxes = [c.bbox(i) for i in items]
        x1 = min(b[0] for b in boxes) - 34
        y1 = min(b[1] for b in boxes) - 22
        x2 = max(b[2] for b in boxes) + 34
        y2 = max(b[3] for b in boxes) + 40
        rect = self._rounded_rect(x1, y1, x2, y2, 22, fill="#1b1d30", outline="#ffe066",
                                  width=3, tags="banner")
        c.tag_lower(rect, items[0])
        c.create_text(cx, y2 - 16, text="click to close", fill=MUTED,
                      font=(FONT, -13), tags="banner")

    def _rounded_rect(self, x1, y1, x2, y2, rad, **kw):
        pts = [x1 + rad, y1, x2 - rad, y1, x2, y1, x2, y1 + rad, x2, y2 - rad, x2, y2,
               x2 - rad, y2, x1 + rad, y2, x1, y2, x1, y2 - rad, x1, y1 + rad, x1, y1]
        return self.canvas.create_polygon(pts, smooth=True, **kw)

    def hide_banner(self):
        if self.show_banner:
            self.show_banner = False
            self.render()

    # ------------------------------------------------------------ Spinning --
    def _index_under_pointer(self, angle):
        """Index of the slice under the pointer (pointer sits at 90°, the top)."""
        seg = 360.0 / len(self.colors)
        return int(((90.0 - angle) % 360.0) // seg) % len(self.colors)

    def _color_counts(self):
        """How many people already got each color currently on the wheel."""
        counts = {label: 0 for label, _ in self.colors}
        for _, label, _ in self.results:
            if label in counts:
                counts[label] += 1
        return counts

    def _available_indices(self):
        """Colors the next spin may land on.

        Balanced mode works on the WHOLE group, not round by round: with N people and
        C colors every color ends with N // C people, and N % C colors get one extra.
        Any color that still has room can come up next, so the order stays random
        (Red, Red, Blue, … is possible) while the final totals are still even.
        """
        all_idx = list(range(len(self.colors)))
        if not self.colors or not self.balance_var.get():
            return all_idx
        counts = self._color_counts()
        total = len(self.results) + len(self.waiting)
        base, extra = divmod(total, len(self.colors))
        over = sum(1 for c in counts.values() if c > base)   # colors using an extra slot
        allowed = [i for i, (label, _) in enumerate(self.colors)
                   if counts[label] < base or (counts[label] == base and over < extra)]
        if allowed:
            return allowed
        # Names/colors changed mid-way so the quotas no longer fit: fall back to the
        # least-used colors so things stay as even as possible.
        low = min(counts.values())
        return [i for i in all_idx if counts[self.colors[i][0]] == low]

    def on_balance_toggle(self):
        self.set_status("Balanced colors ON — everyone is spread evenly."
                        if self.balance_var.get() else
                        "Balanced colors OFF — every spin is fully random.", "info")
        self.refresh()

    def _next_spinner(self):
        """Selected name in the waiting list, otherwise the first one (or None)."""
        if not self.waiting:
            return None
        sel = self.name_list.curselection()
        return self.waiting[sel[0]] if sel else self.waiting[0]

    def spin(self):
        if self.spinning or len(self.colors) < 2:
            return
        n = len(self.colors)
        seg = 360.0 / n
        self.spinner = self._next_spinner()

        # Fair pick among the allowed colors (all of them, or the least-used ones
        # in balanced mode).
        available = (self._available_indices() if self.spinner is not None
                     else list(range(n)))   # a spin with no name doesn't count
        target_index = available[secrets.randbelow(len(available))]
        # Land somewhere inside the slice (not dead-centre), clear of the edges.
        offset = (secrets.randbelow(10001) / 10000 - 0.5) * seg * 0.7
        target = (90.0 - (target_index + 0.5) * seg + offset) % 360.0
        delta = (self.angle % 360.0 - target) % 360.0
        turns = 5 + secrets.randbelow(3)

        self.spin_from = self.angle
        self.spin_distance = turns * 360.0 + delta   # clockwise = decreasing angle
        self.spin_duration = 4.0 + secrets.randbelow(2001) / 1000.0  # 4–6 s
        self.spin_t0 = time.perf_counter()

        self.spinning = True
        self.show_banner = False
        self.stop_confetti()
        self.last_tick_index = self._index_under_pointer(self.angle)
        who = f"{self.spinner} is spinning…" if self.spinner else "Spinning…"
        self.result_label.configure(text=who, text_color=MUTED)
        self.set_status("")
        self.update_controls()
        self._animate_spin()

    def _animate_spin(self):
        t = min(1.0, (time.perf_counter() - self.spin_t0) / self.spin_duration)
        self.angle = self.spin_from - self.spin_distance * ease_out(t)

        idx = self._index_under_pointer(self.angle)
        now = time.perf_counter()
        if idx != self.last_tick_index:
            self.last_tick_index = idx
            if now - self.last_tick_time > 0.045:
                self.last_tick_time = now
                self.sound.play("spin")

        self.render()
        if t < 1.0:
            self.spin_job = self.after(FRAME_MS, self._animate_spin)
        else:
            self.spin_job = None
            self.angle %= 360.0
            self._finish_spin()

    def _finish_spin(self):
        self.spinning = False
        # The result is whatever color is physically under the pointer.
        label, color = self.colors[self._index_under_pointer(self.angle)]
        name = self.spinner
        self.last_result = (name, label, color)

        if name is not None:
            self.waiting.remove(name)
            self.results.append((name, label, color))
            self.result_label.configure(text=f"{name}  →  {label.upper()}",
                                        text_color="#ffe066")
        else:
            self.result_label.configure(text=f"🎉 {label.upper()} 🎉", text_color="#ffe066")
        self.spinner = None
        self.show_banner = True
        self.refresh(keep_result_label=True)
        self.sound.play("winner")
        self.start_confetti()

    # ------------------------------------------------------------ Confetti --
    def start_confetti(self):
        self.stop_confetti()
        c = self.canvas
        w, h, cx, cy, _ = self._geometry()
        palette = CONFETTI_COLORS + ([self.last_result[2]] * 6 if self.last_result else [])
        for k in range(170):
            if k < 70:   # burst from the centre
                x, y = cx, cy
                ang = random.uniform(0, 2 * math.pi)
                speed = random.uniform(250, 650)
                vx, vy = math.cos(ang) * speed, math.sin(ang) * speed - 250
            else:        # rain from the top
                x, y = random.uniform(0, w), random.uniform(-h * 0.7, -10)
                vx, vy = random.uniform(-40, 40), random.uniform(60, 200)
            size = random.uniform(5, 10)
            color = random.choice(palette)
            shape = c.create_rectangle if k % 3 else c.create_oval
            item = shape(x, y, x + size, y + size, fill=color, outline="", tags="confetti")
            self.particles.append({"id": item, "x": x, "y": y, "vx": vx, "vy": vy,
                                   "size": size, "phase": random.uniform(0, 6.28),
                                   "spin": random.uniform(4, 10)})
        c.tag_raise("banner")
        self.confetti_t0 = self.confetti_last = time.perf_counter()
        self._animate_confetti()

    def _animate_confetti(self):
        now = time.perf_counter()
        dt = min(0.05, now - self.confetti_last)
        self.confetti_last = now
        h = self.canvas.winfo_height()
        alive = False
        for p in self.particles:
            p["vy"] += 600 * dt          # gravity
            p["vx"] *= 0.985             # air drag
            p["vy"] = min(p["vy"], 380)  # terminal velocity
            p["phase"] += p["spin"] * dt
            p["x"] += (p["vx"] + math.sin(p["phase"]) * 40) * dt
            p["y"] += p["vy"] * dt
            flutter = abs(math.cos(p["phase"])) * p["size"] + 1
            self.canvas.coords(p["id"], p["x"], p["y"], p["x"] + flutter, p["y"] + p["size"])
            if p["y"] < h + 20:
                alive = True
        if alive and now - self.confetti_t0 < 6:
            self.confetti_job = self.after(FRAME_MS, self._animate_confetti)
        else:
            self.stop_confetti()

    def stop_confetti(self):
        if self.confetti_job is not None:
            self.after_cancel(self.confetti_job)
            self.confetti_job = None
        self.canvas.delete("confetti")
        self.particles = []

    # ------------------------------------------------------------ Colors --
    def _parse_color(self, raw):
        """Return (label, '#rrggbb') or None if Tk doesn't know the color."""
        text = clean_text(raw)
        if not text:
            return None
        try:
            r, g, b = self.winfo_rgb(text if text.startswith("#") else text.replace(" ", ""))
        except tk.TclError:
            try:
                r, g, b = self.winfo_rgb(text)
            except tk.TclError:
                return None
        hex_color = f"#{r >> 8:02x}{g >> 8:02x}{b >> 8:02x}"
        label = text.upper() if text.startswith("#") else text.title()
        return label, hex_color

    def _try_add_color(self, label, hex_color):
        if any(lbl.casefold() == label.casefold() for lbl, _ in self.colors):
            self.set_status(f"“{label}” is already on the wheel.", "error")
            return False
        self.colors.append((label, hex_color))
        return True

    def add_color(self):
        if self.spinning:
            return
        raw = self.color_entry.get()
        if not raw.strip():
            self.set_status("Type a color first (e.g. Red or #FF8800).", "error")
            return
        parsed = self._parse_color(raw)
        if parsed is None:
            self.set_status(f"“{raw.strip()}” is not a color I know. Try a common name "
                            "(Red, Orange, Pink, Purple…) or a hex code like #FF8800, "
                            "or use the 🎨 button.", "error")
            return
        if self._try_add_color(*parsed):
            self.color_entry.delete(0, "end")
            self.set_status(f"Added color “{parsed[0]}”.", "success")
            self.refresh()

    def pick_color(self):
        if self.spinning:
            return
        _, hex_color = colorchooser.askcolor(title="Pick a color for the wheel", parent=self)
        if not hex_color:
            return
        # Use the typed text as the label if there is one, otherwise the hex code.
        label = clean_text(self.color_entry.get()) or hex_color.upper()
        if self._try_add_color(label, hex_color.lower()):
            self.color_entry.delete(0, "end")
            self.set_status(f"Added color “{label}”.", "success")
            self.refresh()

    def add_basic_colors(self):
        if self.spinning:
            return
        added = 0
        for name in BASIC_COLORS:
            if not any(lbl.casefold() == name.casefold() for lbl, _ in self.colors):
                self.colors.append(self._parse_color(name))
                added += 1
        self.set_status(f"Added {added} color{'s' if added != 1 else ''}." if added
                        else "Those colors are already on the wheel.",
                        "success" if added else "error")
        self.refresh()

    def remove_color(self):
        if self.spinning:
            return
        sel = self.color_list.curselection()
        if not sel:
            self.set_status("Select a color in the list first.", "error")
            return
        label, _ = self.colors.pop(sel[0])
        self.set_status(f"Removed color “{label}”.", "success")
        self.refresh()

    def clear_colors(self):
        if self.spinning:
            return
        self.colors.clear()
        self.set_status("All colors cleared.", "success")
        self.refresh()

    # ------------------------------------------------------------ Names --
    def add_names(self):
        if self.spinning:
            return
        lines = [clean_text(line) for line in self.textbox.get("1.0", "end").splitlines()]
        lines = [line for line in lines if line]
        if not lines:
            self.set_status("Please enter at least one name.", "error")
            return
        taken = {n.casefold() for n in self.waiting} | {r[0].casefold() for r in self.results}
        added = dupes = 0
        for name in lines:
            if name.casefold() in taken:
                dupes += 1
                continue
            taken.add(name.casefold())
            self.waiting.append(name)
            added += 1
        self.textbox.delete("1.0", "end")
        msg = f"Added {added} name{'s' if added != 1 else ''}."
        if dupes:
            msg += f" Skipped {dupes} duplicate{'s' if dupes != 1 else ''}."
        self.set_status(msg, "success" if added else "error")
        self.refresh()

    def shuffle_names(self):
        if self.spinning:
            return
        if len(self.waiting) < 2:
            self.set_status("Need at least 2 names waiting to shuffle.", "error")
            return
        before = list(self.waiting)
        while self.waiting == before:   # make sure the order actually changes
            random.SystemRandom().shuffle(self.waiting)
        self.set_status("Order shuffled! Next to spin is at the top of the list.", "success")
        self.refresh()

    def remove_name(self):
        if self.spinning:
            return
        sel = self.name_list.curselection()
        if not sel:
            self.set_status("Select a name in the list first.", "error")
            return
        name = self.waiting.pop(sel[0])
        self.set_status(f"Removed “{name}”.", "success")
        self.refresh()

    def clear_names(self):
        if self.spinning:
            return
        self.waiting.clear()
        self.results.clear()
        self.last_result = None
        self.set_status("All names and results cleared.", "success")
        self.refresh()

    def reset_results(self):
        if self.spinning or not self.results:
            return
        self.waiting = [r[0] for r in self.results] + self.waiting
        self.results.clear()
        self.last_result = None
        self.set_status("Results cleared. Everyone can spin again.", "success")
        self.refresh()

    # ------------------------------------------------------------ Export --
    def _grouped_results(self):
        """[(label, hex, [names])] in wheel order, then colors no longer on the wheel."""
        groups = {label: (color, []) for label, color in self.colors}
        for name, label, color in self.results:
            groups.setdefault(label, (color, []))[1].append(name)
        return [(label, color, names) for label, (color, names) in groups.items()]

    def save_results_image(self):
        if self.spinning or not self.results:
            return
        stamp = time.strftime("%Y%m%d_%H%M")
        path = filedialog.asksaveasfilename(
            parent=self, title="Save results as image", defaultextension=".png",
            initialfile=f"color_results_{stamp}.png",
            filetypes=[("PNG image", "*.png"), ("JPEG image", "*.jpg")])
        if not path:
            return
        try:
            img = render_results_image(self._grouped_results(), len(self.results))
            if path.lower().endswith((".jpg", ".jpeg")):
                img = img.convert("RGB")
            img.save(path)
        except ImportError:
            self.set_status("Saving images needs Pillow: run  pip install pillow", "error")
            return
        except OSError as exc:
            self.set_status(f"Could not save the image: {exc}", "error")
            return
        self.set_status(f"Results saved to {path}", "success")

    # ------------------------------------------------------------ Refresh --
    def refresh(self, keep_result_label=False):
        if not keep_result_label:
            self.show_banner = False
            self.stop_confetti()

        self.color_list.delete(0, "end")
        for i, (label, color) in enumerate(self.colors):
            self.color_list.insert("end", f"  {label}")
            fg = text_color_for(color)
            self.color_list.itemconfig(i, bg=color, fg=fg, selectbackground=color,
                                       selectforeground=fg)
        self.color_count_label.configure(text=f"Colors: {len(self.colors)}")

        self.name_list.delete(0, "end")
        for name in self.waiting:
            self.name_list.insert("end", name)
        self.name_count_label.configure(text=f"Waiting to spin: {len(self.waiting)}")

        self.result_list.delete(0, "end")
        for i, (name, label, color) in enumerate(self.results):
            self.result_list.insert("end", f" {i + 1}. {name}  →  {label}")
            fg = text_color_for(color)
            self.result_list.itemconfig(i, bg=color, fg=fg, selectbackground=color,
                                        selectforeground=fg)
        if self.results:
            self.result_list.see("end")
        self._update_summary()

        if not keep_result_label:
            self.update_next_label()
        self.render()
        self.update_controls()

    def _update_summary(self):
        if not self.results:
            self.summary_label.configure(text="No spins yet.")
            return
        counts = self._color_counts()
        for _, label, _ in self.results:   # colors since removed from the wheel
            counts.setdefault(label, sum(1 for r in self.results if r[1] == label))
        lines = [f"{label}: {n}" for label, n in counts.items()]
        self.summary_label.configure(text="People per color\n" + "\n".join(lines))

    def update_next_label(self):
        if self.spinning:
            return
        if len(self.colors) < 2:
            text = "Add at least 2 colors to the wheel."
        elif not self.waiting:
            text = ("Everyone has a color! Add more names or reset results."
                    if self.results else "Add names, then press SPIN!")
        else:
            text = f"Next to spin:  {self._next_spinner()}"
        self.result_label.configure(text=text, text_color=MUTED)

    # ------------------------------------------------------------ Controls --
    def toggle_mute(self):
        self.sound.muted = not self.sound.muted
        self.mute_btn.configure(text="🔇 Sound: Off" if self.sound.muted else "🔊 Sound: On")

    def set_status(self, msg, kind="info"):
        color = {"info": MUTED, "success": SUCCESS, "error": ERROR}[kind]
        self.status_label.configure(text=msg, text_color=color)

    def update_controls(self):
        idle = not self.spinning

        def state(ok):
            return "normal" if ok else "disabled"

        self.spin_btn.configure(state=state(idle and len(self.colors) >= 2))
        self.reset_btn.configure(state=state(idle and bool(self.results)))
        self.save_img_btn.configure(state=state(idle and bool(self.results)))
        self.remove_color_btn.configure(state=state(idle and bool(self.colors)))
        self.clear_colors_btn.configure(state=state(idle and bool(self.colors)))
        self.remove_name_btn.configure(state=state(idle and bool(self.waiting)))
        self.shuffle_btn.configure(state=state(idle and len(self.waiting) >= 2))
        self.clear_names_btn.configure(state=state(idle and bool(self.waiting or self.results)))
        for btn in (self.add_color_btn, self.pick_color_btn, self.basic_btn,
                    self.add_names_btn, self.balance_switch):
            btn.configure(state=state(idle))

    def on_close(self):
        for job in (self.spin_job, self.confetti_job):
            if job is not None:
                self.after_cancel(job)
        self.sound.shutdown()
        self.destroy()


if __name__ == "__main__":
    app = SpinWheelApp()
    app.mainloop()
