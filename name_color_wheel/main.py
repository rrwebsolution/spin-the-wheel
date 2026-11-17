"""
Name Color Spin Wheel
Spin a wheel of participant names; the colour of the winning section is the
participant's T-shirt colour (GREEN / BLUE / RED / YELLOW).

Run:  python main.py
"""

import math
import os
import random
import secrets
import sys
import time
import tkinter as tk
import tkinter.font as tkfont

import customtkinter as ctk

os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
try:
    import pygame
except ImportError:  # sound is optional
    pygame = None

try:
    import winsound
except ImportError:
    winsound = None


# --------------------------------------------------------------------------- #
# Theme
# --------------------------------------------------------------------------- #
BG = "#141625"
PANEL = "#1d2033"
CARD = "#272b44"
CARD_HOVER = "#353a5c"
TEXT = "#f1f2f8"
MUTED = "#9aa0bf"
ACCENT = "#7c5cff"
ACCENT_HOVER = "#6846f0"
GOLD = "#ffd84d"
SUCCESS = "#4ade80"
ERROR = "#ff6b81"

# The only wheel colours, in repeating order: (name, fill, text colour)
SHIRT_COLORS = [
    ("GREEN", "#1FA34A", "#ffffff"),
    ("BLUE", "#1E6FE0", "#ffffff"),
    ("RED", "#E53935", "#ffffff"),
    ("YELLOW", "#FFD21F", "#000000"),
]
COLOR_HEX = {name: fill for name, fill, _ in SHIRT_COLORS}
COLOR_TEXT = {name: txt for name, _, txt in SHIRT_COLORS}

# Sections are drawn in neutral shades so nobody can see their colour before
# the spin; the real colour is revealed only when the wheel stops.
NEUTRAL = ["#3d4270", "#2d3155", "#4a5085"]

FONT = "Segoe UI"
MAX_NAME_LEN = 40
FRAME_MS = 15


def color_for_index(i):
    """GREEN, BLUE, RED, YELLOW, GREEN, ... — used to build a balanced colour pool."""
    return SHIRT_COLORS[i % len(SHIRT_COLORS)][0]


def neutral_for(i, n):
    """Alternating neutral shade; a third shade avoids two equal neighbours when n is odd."""
    if n > 1 and n % 2 and i == n - 1:
        return NEUTRAL[2]
    return NEUTRAL[i % 2]


def ease_out(t):
    """Quartic ease-out: fast start, long natural slowdown."""
    return 1 - (1 - t) ** 4


# --------------------------------------------------------------------------- #
# Sound (optional — the app works without pygame or the .wav files)
# --------------------------------------------------------------------------- #
class SoundPlayer:
    def __init__(self):
        base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
        candidates = {k: os.path.join(base, "assets", f"{k}.wav") for k in ("spin", "winner")}
        self.files = {k: p for k, p in candidates.items() if os.path.isfile(p)}
        self.muted = False
        self.backend = None
        self.sounds = {}
        if not self.files:
            return
        if pygame is not None:
            try:
                pygame.mixer.init(frequency=44100, size=-16, channels=2, buffer=512)
                self.sounds = {k: pygame.mixer.Sound(p) for k, p in self.files.items()}
                self.backend = "pygame"
            except Exception:
                self.sounds = {}
        if self.backend is None and winsound is not None:
            self.backend = "winsound"

    def play(self, key):
        if self.muted or self.backend is None or key not in self.files:
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
# Application
# --------------------------------------------------------------------------- #
class NameColorWheelApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        ctk.set_appearance_mode("dark")
        self.title("Name Color Spin Wheel")
        self.geometry("1440x860")
        self.minsize(1100, 680)
        self.configure(fg_color=BG)

        self.sound = SoundPlayer()
        self.measure_font = tkfont.Font(family=FONT, size=-100, weight="bold")
        self._width_cache = {}

        self.all_names = []      # original roster, restored by RESET
        self.names = []          # names currently on the wheel
        self.history = []        # [(name, colour)] in selection order
        self.selected = None     # (name, colour) of the most recent spin
        self.hidden_colors = []  # secret colour of each section, set at spin start
        self.revealed = None     # (section index, colour) shown after the wheel stops
        self.reveal_on = False
        self.reveal_step = 0
        self.angle = 0.0         # wheel rotation in degrees (Tk: counter-clockwise)
        self.spinning = False
        self.spin_job = None
        self.show_popup = False
        self.particles = []
        self.confetti_job = None
        self.last_tick_index = None
        self.last_tick_time = 0.0

        self._build_ui()
        self.refresh()
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.after(50, lambda: self.state("zoomed"))

    # ------------------------------------------------------------------ UI --
    def _build_ui(self):
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)
        self._build_left()
        self._build_center()
        self._build_right()

    def _button(self, parent, text, command, primary=False, **kw):
        opts = dict(height=38, font=(FONT, 13, "bold"), corner_radius=10,
                    fg_color=ACCENT if primary else CARD,
                    hover_color=ACCENT_HOVER if primary else CARD_HOVER)
        opts.update(kw)
        return ctk.CTkButton(parent, text=text, command=command, **opts)

    def _build_left(self):
        side = ctk.CTkScrollableFrame(self, width=300, fg_color=PANEL, corner_radius=0)
        side.grid(row=0, column=0, sticky="ns")
        pad = {"padx": 18}

        ctk.CTkLabel(side, text="Name Color\nSpin Wheel", font=(FONT, 26, "bold"),
                     text_color=TEXT, justify="left").pack(anchor="w", pady=(16, 2), **pad)
        swatches = ctk.CTkFrame(side, fg_color="transparent")
        swatches.pack(anchor="w", pady=(0, 14), **pad)
        for _, fill, _ in SHIRT_COLORS:
            ctk.CTkFrame(swatches, width=26, height=8, corner_radius=4,
                         fg_color=fill).pack(side="left", padx=(0, 5))

        ctk.CTkLabel(side, text="Enter names (one per line)", font=(FONT, 13, "bold"),
                     text_color=TEXT).pack(anchor="w", **pad)
        self.textbox = ctk.CTkTextbox(side, height=140, font=(FONT, 13), fg_color=CARD,
                                      border_width=0, corner_radius=10)
        self.textbox.pack(fill="x", pady=(6, 8), **pad)
        self.add_btn = self._button(side, "ADD NAMES", self.add_names, primary=True)
        self.add_btn.pack(fill="x", pady=(0, 14), **pad)

        self.count_label = ctk.CTkLabel(side, text="Participants: 0", font=(FONT, 16, "bold"),
                                        text_color=TEXT)
        self.count_label.pack(anchor="w", **pad)

        list_frame = ctk.CTkFrame(side, fg_color=CARD, corner_radius=10)
        list_frame.pack(fill="x", pady=(6, 8), **pad)
        self.listbox = tk.Listbox(
            list_frame, height=9, font=(FONT, 12), bg=CARD, fg=TEXT, bd=0,
            highlightthickness=0, selectbackground=ACCENT, selectforeground="#ffffff",
            activestyle="none", exportselection=False)
        self.listbox.pack(side="left", fill="both", expand=True, padx=(10, 0), pady=8)
        scroll = ctk.CTkScrollbar(list_frame, command=self.listbox.yview)
        scroll.pack(side="right", fill="y", pady=6)
        self.listbox.configure(yscrollcommand=scroll.set)
        self.listbox.bind("<Delete>", lambda e: self.remove_name())

        self.remove_name_btn = self._button(side, "REMOVE NAME", self.remove_name)
        self.remove_name_btn.pack(fill="x", pady=(0, 14), **pad)

        row = ctk.CTkFrame(side, fg_color="transparent")
        row.pack(fill="x", **pad)
        row.grid_columnconfigure((0, 1), weight=1, uniform="c")
        self.reset_btn = self._button(row, "RESET", self.reset)
        self.reset_btn.grid(row=0, column=0, sticky="ew", padx=(0, 4))
        self.clear_btn = self._button(row, "CLEAR ALL", self.clear_all,
                                      fg_color="#5a2333", hover_color="#74293f")
        self.clear_btn.grid(row=0, column=1, sticky="ew", padx=(4, 0))

        self.mute_btn = self._button(side, "🔊 Sound: On", self.toggle_mute,
                                     font=(FONT, 12))
        self.mute_btn.pack(fill="x", pady=(8, 0), **pad)

        self.status_label = ctk.CTkLabel(side, text="", font=(FONT, 12), text_color=MUTED,
                                         wraplength=260, justify="left")
        self.status_label.pack(anchor="w", pady=(10, 16), **pad)

    def _build_center(self):
        main = ctk.CTkFrame(self, fg_color=BG, corner_radius=0)
        main.grid(row=0, column=1, sticky="nsew")

        btn_row = ctk.CTkFrame(main, fg_color="transparent")
        btn_row.pack(side="bottom", pady=(4, 20))
        self.spin_btn = ctk.CTkButton(
            btn_row, text="SPIN THE WHEEL", width=300, height=66, corner_radius=33,
            font=(FONT, 24, "bold"), fg_color="#ff4d6d", hover_color="#e63b5b",
            command=self.spin)
        self.spin_btn.pack(side="left", padx=8)
        self.spin_again_btn = self._button(btn_row, "↻ SPIN AGAIN", self.spin, width=170,
                                           height=52, corner_radius=26, font=(FONT, 15, "bold"))
        self.spin_again_btn.pack(side="left", padx=8)
        self.remove_selected_btn = self._button(
            btn_row, "REMOVE SELECTED NAME", self.remove_selected, width=230, height=52,
            corner_radius=26, font=(FONT, 15, "bold"))
        self.remove_selected_btn.pack(side="left", padx=8)

        self.result_label = ctk.CTkLabel(main, text="", font=(FONT, 20, "bold"),
                                         text_color=MUTED)
        self.result_label.pack(side="bottom", pady=(0, 4))

        self.canvas = tk.Canvas(main, bg=BG, highlightthickness=0)
        self.canvas.pack(fill="both", expand=True, padx=16, pady=(16, 4))
        self.canvas.bind("<Configure>", lambda e: self.render())
        self.canvas.bind("<Button-1>", lambda e: self.hide_popup())

    def _build_right(self):
        right = ctk.CTkFrame(self, width=300, fg_color=PANEL, corner_radius=0)
        right.grid(row=0, column=2, sticky="ns")
        right.grid_propagate(False)
        right.pack_propagate(False)

        ctk.CTkLabel(right, text="SELECTED PARTICIPANTS", font=(FONT, 16, "bold"),
                     text_color=TEXT).pack(anchor="w", padx=18, pady=(20, 8))

        counters = ctk.CTkFrame(right, fg_color="transparent")
        counters.pack(fill="x", padx=18, pady=(0, 10))
        counters.grid_columnconfigure((0, 1), weight=1, uniform="c")
        self.selected_count = self._counter(counters, 0, "Selected")
        self.remaining_count = self._counter(counters, 1, "Remaining")

        self.history_frame = ctk.CTkScrollableFrame(right, fg_color=CARD, corner_radius=12)
        self.history_frame.pack(fill="both", expand=True, padx=18, pady=(0, 18))

    def _counter(self, parent, col, title):
        box = ctk.CTkFrame(parent, fg_color=CARD, corner_radius=12)
        box.grid(row=0, column=col, sticky="ew", padx=(0, 4) if col == 0 else (4, 0))
        value = ctk.CTkLabel(box, text="0", font=(FONT, 26, "bold"), text_color=TEXT)
        value.pack(pady=(8, 0))
        ctk.CTkLabel(box, text=title, font=(FONT, 12), text_color=MUTED).pack(pady=(0, 8))
        return value

    # ------------------------------------------------------------ Drawing --
    def _geometry(self):
        w = max(self.canvas.winfo_width(), 50)
        h = max(self.canvas.winfo_height(), 50)
        r = max(40, min(w, h) / 2 - 30)
        return w, h, w / 2, h / 2 + 10, r

    def _text_width(self, text):
        """Width of text in the bold wheel font at 100px."""
        if text not in self._width_cache:
            self._width_cache[text] = max(1, self.measure_font.measure(text))
        return self._width_cache[text]

    def _fit_text(self, text, room, max_px, min_px=8):
        """Shrink the font so text fits `room` pixels; truncate only below min_px."""
        px = min(max_px, room * 100 / self._text_width(text))
        if px >= min_px:
            return text, px
        while len(text) > 2 and self._text_width(text + "…") * min_px / 100 > room:
            text = text[:-1]
        return text + "…", min_px

    def render(self):
        c = self.canvas
        c.delete("wheel", "popup")
        w, h, cx, cy, r = self._geometry()

        rim = r + 14
        c.create_oval(cx - rim, cy - rim, cx + rim, cy + rim, fill="#262a45",
                      outline="#3a4070", width=2, tags="wheel")
        for k in range(32):
            a = math.radians(k * 360 / 32)
            lx, ly = cx + (r + 7) * math.cos(a), cy - (r + 7) * math.sin(a)
            dot = max(2.5, r * 0.011)
            c.create_oval(lx - dot, ly - dot, lx + dot, ly + dot,
                          fill=GOLD if k % 2 else "#ffffff", outline="", tags="wheel")

        n = len(self.names)
        if n == 0:
            c.create_oval(cx - r, cy - r, cx + r, cy + r, fill=CARD, outline="#3a4070",
                          width=2, tags="wheel")
            c.create_text(cx, cy - r * 0.35, text="Add participant names\nto build the wheel",
                          fill=MUTED, font=(FONT, -int(max(14, r * 0.07)), "bold"),
                          justify="center", tags="wheel")
        elif n == 1:
            fill, text_fill = self._section_colors(0, 1)
            c.create_oval(cx - r, cy - r, cx + r, cy + r, fill=fill,
                          outline="#ffffff", width=3, tags="wheel")
            text, px = self._fit_text(self.names[0], r * 1.4, r * 0.14)
            c.create_text(cx, cy - r * 0.5, text=text, fill=text_fill,
                          font=(FONT, -int(px), "bold"), tags="wheel")
        else:
            self._draw_sections(cx, cy, r, n)

        hub = r * 0.12
        c.create_oval(cx - hub, cy - hub, cx + hub, cy + hub, fill="#ffffff",
                      outline="#262a45", width=3, tags="wheel")
        c.create_oval(cx - hub * 0.45, cy - hub * 0.45, cx + hub * 0.45, cy + hub * 0.45,
                      fill=ACCENT, outline="", tags="wheel")

        # Fixed pointer at top centre
        pw = max(16, r * 0.075)
        top = cy - r - 22
        c.create_polygon(cx - pw, top, cx + pw, top, cx, cy - r + pw * 1.7,
                         fill="#ffffff", outline="#111111", width=2, tags="wheel")
        c.create_oval(cx - pw * 0.42, top + pw * 0.05, cx + pw * 0.42, top + pw * 0.89,
                      fill="#ff4d6d", outline="", tags="wheel")

        if self.show_popup and self.selected:
            self._draw_popup(w, cx, cy, r)
        c.tag_raise("confetti")
        c.tag_raise("popup")

    def _section_colors(self, i, n):
        """(fill, text colour) — neutral unless this section's colour is being revealed."""
        if self.revealed and self.reveal_on and self.revealed[0] == i:
            color = self.revealed[1]
            return COLOR_HEX[color], COLOR_TEXT[color]
        return neutral_for(i, n), "#ffffff"

    def _draw_sections(self, cx, cy, r, n):
        c = self.canvas
        seg = 360.0 / n
        seg_rad = math.radians(seg)
        inner, outer = r * 0.17, r * 0.95
        room = outer - inner
        mid_r = (inner + outer) / 2
        outline_w = 2 if n < 60 else 1
        for i, name in enumerate(self.names):
            fill, text_fill = self._section_colors(i, n)
            start = self.angle + i * seg
            c.create_arc(cx - r, cy - r, cx + r, cy + r, start=start, extent=seg,
                         fill=fill, outline="#ffffff", width=outline_w,
                         style=tk.PIESLICE, tags="wheel")

            # Font: fit the radial length first, then make sure the letter
            # height fits the slice width at the text's innermost point.
            text, px = self._fit_text(name, room, r * 0.085)
            text_len = self._text_width(text) * px / 100
            inner_edge = max(inner, mid_r - text_len / 2)
            px = max(6, min(px, seg_rad * inner_edge * 0.8))

            mid = start + seg / 2
            rad = math.radians(mid)
            tx = cx + mid_r * math.cos(rad)
            ty = cy - mid_r * math.sin(rad)
            text_angle = mid % 360
            if 90 < text_angle < 270:  # keep text readable on the left half
                text_angle = (text_angle + 180) % 360
            c.create_text(tx, ty, text=text, angle=text_angle, fill=text_fill,
                          font=(FONT, -int(px), "bold"), tags="wheel")

    def _draw_popup(self, w, cx, cy, r):
        c = self.canvas
        name, color = self.selected
        card_w = min(w * 0.9, max(r * 1.5, 420))
        title_px = int(max(18, r * 0.075))
        label_px = int(max(13, r * 0.045))
        name_text, name_px = self._fit_text(name.upper(), card_w - 60, max(30, r * 0.19), 18)
        pill_px = int(max(18, r * 0.07))

        gap = r * 0.035
        heights = [title_px * 1.3, name_px * 1.3, label_px * 1.4, pill_px * 2.0]
        card_h = sum(heights) + gap * 3 + 60 + label_px
        x1, y1 = cx - card_w / 2, cy - card_h / 2
        x2, y2 = cx + card_w / 2, cy + card_h / 2
        self._rounded_rect(x1 + 6, y1 + 8, x2 + 6, y2 + 8, 26, fill="#05060c", tags="popup")
        self._rounded_rect(x1, y1, x2, y2, 26, fill="#1a1d31", outline=COLOR_HEX[color],
                           width=4, tags="popup")

        y = y1 + 30
        c.create_text(cx, y + heights[0] / 2, text="🎉 SELECTED 🎉", fill=GOLD,
                      font=(FONT, -title_px, "bold"), tags="popup")
        y += heights[0] + gap
        c.create_text(cx, y + heights[1] / 2, text=name_text, fill="#ffffff",
                      font=(FONT, -int(name_px), "bold"), tags="popup")
        y += heights[1] + gap
        c.create_text(cx, y + heights[2] / 2, text="T-SHIRT COLOR:", fill=MUTED,
                      font=(FONT, -label_px, "bold"), tags="popup")
        y += heights[2] + gap
        pill_w = max(pill_px * 6, card_w * 0.5)
        self._rounded_rect(cx - pill_w / 2, y, cx + pill_w / 2, y + heights[3],
                           heights[3] / 2, fill=COLOR_HEX[color], outline="#ffffff",
                           width=2, tags="popup")
        c.create_text(cx, y + heights[3] / 2, text=color, fill=COLOR_TEXT[color],
                      font=(FONT, -pill_px, "bold"), tags="popup")
        c.create_text(cx, y2 - 14 - label_px * 0.4, text="click to close", fill=MUTED,
                      font=(FONT, -max(11, int(label_px * 0.8))), tags="popup")

    def _rounded_rect(self, x1, y1, x2, y2, rad, **kw):
        rad = min(rad, (x2 - x1) / 2, (y2 - y1) / 2)
        pts = [x1 + rad, y1, x2 - rad, y1, x2, y1, x2, y1 + rad, x2, y2 - rad, x2, y2,
               x2 - rad, y2, x1 + rad, y2, x1, y2, x1, y2 - rad, x1, y1 + rad, x1, y1]
        return self.canvas.create_polygon(pts, smooth=True, **kw)

    def hide_popup(self):
        if self.show_popup:
            self.show_popup = False
            self.render()

    # ------------------------------------------------------------ Spinning --
    def _index_under_pointer(self, angle):
        """Index of the section under the pointer (pointer is at 90°, the top)."""
        n = len(self.names)
        return int(((90.0 - angle) % 360.0) // (360.0 / n)) % n

    def _assign_hidden_colors(self):
        """Secretly give every section a colour from a balanced, shuffled pool.

        The pool holds GREEN/BLUE/RED/YELLOW in equal amounts for the whole
        roster, minus the colours already given out, so the final groups stay
        balanced. Already-selected names keep their recorded colour.
        """
        recorded = dict(self.history)
        pool = [color_for_index(i) for i in range(len(self.all_names))]
        for color in recorded.values():
            if color in pool:
                pool.remove(color)
        unpicked = sum(1 for n in self.names if n not in recorded)
        while len(pool) < unpicked:
            pool.append(color_for_index(len(pool)))
        secrets.SystemRandom().shuffle(pool)
        remaining = iter(pool)
        self.hidden_colors = [recorded[n] if n in recorded else next(remaining)
                              for n in self.names]

    def spin(self):
        if self.spinning or not self.names:
            return
        n = len(self.names)
        seg = 360.0 / n
        self._assign_hidden_colors()
        self.revealed = None

        # Every section is equally likely. The wheel is then rotated so that
        # this exact section ends up under the pointer; the result is read back
        # from the final wheel position, so visual and result always match.
        target_index = secrets.randbelow(n)
        offset = (secrets.randbelow(10001) / 10000 - 0.5) * seg * 0.7
        target_angle = (90.0 - (target_index + 0.5) * seg + offset) % 360.0
        delta = (self.angle % 360.0 - target_angle) % 360.0
        turns = 5 + secrets.randbelow(3)

        self.spin_from = self.angle
        self.spin_distance = turns * 360.0 + delta       # clockwise
        self.spin_duration = 4.0 + secrets.randbelow(2001) / 1000.0  # 4–6 s
        self.spin_t0 = time.perf_counter()

        self.spinning = True
        self.show_popup = False
        self.stop_confetti()
        self.last_tick_index = self._index_under_pointer(self.angle)
        self.result_label.configure(text="Spinning…", text_color=MUTED)
        self.set_status("")
        self.update_controls()
        self._animate_spin()

    def _animate_spin(self):
        t = min(1.0, (time.perf_counter() - self.spin_t0) / self.spin_duration)
        self.angle = self.spin_from - self.spin_distance * ease_out(t)

        idx = self._index_under_pointer(self.angle)
        if idx != self.last_tick_index:
            self.last_tick_index = idx
            now = time.perf_counter()
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
        # The section under the pointer reveals its hidden colour with a blink.
        idx = self._index_under_pointer(self.angle)
        self.revealed = (idx, self.hidden_colors[idx])
        self.reveal_step = 0
        self.result_label.configure(text="Revealing T-shirt color…", text_color=GOLD)
        self._blink_reveal()

    def _blink_reveal(self):
        self.reveal_step += 1
        self.reveal_on = self.reveal_step % 2 == 1
        self.render()
        if self.reveal_step < 7:
            self.spin_job = self.after(150, self._blink_reveal)
        else:
            self.spin_job = None
            self._announce()

    def _announce(self):
        self.spinning = False
        idx, color = self.revealed
        name = self.names[idx]
        if all(n != name for n, _ in self.history):
            self.history.append((name, color))
        self.selected = (name, color)
        self.show_popup = True

        self.listbox.selection_clear(0, "end")
        self.listbox.selection_set(idx)
        self.listbox.see(idx)
        self.result_label.configure(text=f"🎉 {name.upper()}  →  {color} T-SHIRT",
                                    text_color=COLOR_HEX[color])
        self.refresh(keep_popup=True)
        self.sound.play("winner")
        self.start_confetti(COLOR_HEX[color])

    # ------------------------------------------------------------ Confetti --
    def start_confetti(self, main_color):
        self.stop_confetti()
        c = self.canvas
        w, h, cx, cy, _ = self._geometry()
        colors = [fill for _, fill, _ in SHIRT_COLORS] + [main_color] * 3 + ["#ffffff", GOLD]
        for k in range(180):
            if k < 80:   # burst from the centre
                x, y = cx, cy
                ang = random.uniform(0, 2 * math.pi)
                speed = random.uniform(250, 700)
                vx, vy = math.cos(ang) * speed, math.sin(ang) * speed - 250
            else:        # rain from the top
                x, y = random.uniform(0, w), random.uniform(-h * 0.7, -10)
                vx, vy = random.uniform(-40, 40), random.uniform(60, 200)
            size = random.uniform(6, 11)
            shape = c.create_rectangle if k % 3 else c.create_oval
            item = shape(x, y, x + size, y + size, fill=random.choice(colors), outline="",
                         tags="confetti")
            self.particles.append({"id": item, "x": x, "y": y, "vx": vx, "vy": vy,
                                   "size": size, "phase": random.uniform(0, 6.28),
                                   "spin": random.uniform(4, 10)})
        c.tag_raise("popup")
        self.confetti_t0 = self.confetti_last = time.perf_counter()
        self._animate_confetti()

    def _animate_confetti(self):
        now = time.perf_counter()
        dt = min(0.05, now - self.confetti_last)
        self.confetti_last = now
        h = self.canvas.winfo_height()
        alive = False
        for p in self.particles:
            p["vy"] = min(p["vy"] + 600 * dt, 380)
            p["vx"] *= 0.985
            p["phase"] += p["spin"] * dt
            p["x"] += (p["vx"] + math.sin(p["phase"]) * 40) * dt
            p["y"] += p["vy"] * dt
            flutter = abs(math.cos(p["phase"])) * p["size"] + 1
            self.canvas.coords(p["id"], p["x"], p["y"], p["x"] + flutter, p["y"] + p["size"])
            alive = alive or p["y"] < h + 20
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

    # ------------------------------------------------------------ Actions --
    def add_names(self):
        lines = [" ".join(line.split()) for line in self.textbox.get("1.0", "end").splitlines()]
        lines = [line for line in lines if line]
        if not lines:
            self.set_status("Please enter at least one name.", "error")
            return
        existing = {n.casefold() for n in self.all_names}
        added, dupes, too_long = 0, 0, 0
        for name in lines:
            if len(name) > MAX_NAME_LEN:
                too_long += 1
                continue
            if name.casefold() in existing:
                dupes += 1
                continue
            existing.add(name.casefold())
            self.all_names.append(name)
            self.names.append(name)
            added += 1
        self.textbox.delete("1.0", "end")
        self.refresh()
        msg = f"Added {added} name{'s' if added != 1 else ''}."
        if dupes:
            msg += f" Skipped {dupes} duplicate{'s' if dupes != 1 else ''}."
        if too_long:
            msg += f" Skipped {too_long} name(s) over {MAX_NAME_LEN} characters."
        self.set_status(msg, "success" if added else "error")

    def remove_name(self):
        if self.spinning:
            return
        sel = self.listbox.curselection()
        if not sel:
            self.set_status("Select a name in the list first.", "error")
            return
        name = self.names.pop(sel[0])
        if name in self.all_names:
            self.all_names.remove(name)
        if self.selected and self.selected[0] == name:
            self.selected = None
        self.refresh()
        self.set_status(f"Removed “{name}”.", "success")

    def remove_selected(self):
        if self.spinning or not self.selected or self.selected[0] not in self.names:
            return
        name, color = self.selected
        self.names.remove(name)  # stays in history with its colour
        self.selected = None
        self.refresh()
        self.result_label.configure(text=f"{name} ({color}) removed from the wheel.",
                                    text_color=MUTED)
        self.set_status(f"Removed “{name}”. The wheel was rebuilt.", "success")

    def reset(self):
        if self.spinning:
            return
        self.names = list(self.all_names)
        self.history.clear()
        self.selected = None
        self.refresh()
        self.set_status("Original participant list restored and results cleared.", "success")

    def clear_all(self):
        if self.spinning:
            return
        self.names.clear()
        self.all_names.clear()
        self.history.clear()
        self.selected = None
        self.refresh()
        self.set_status("All names and results cleared.", "success")

    def toggle_mute(self):
        self.sound.muted = not self.sound.muted
        self.mute_btn.configure(text="🔇 Sound: Off" if self.sound.muted else "🔊 Sound: On")

    # ------------------------------------------------------------ Refresh --
    def refresh(self, keep_popup=False):
        if not keep_popup:
            self.show_popup = False
            self.revealed = None
            self.stop_confetti()
            n = len(self.names)
            self.result_label.configure(
                text="Ready! Press SPIN THE WHEEL." if n else "Add names to get started.",
                text_color=MUTED)

        sel = self.listbox.curselection()
        self.listbox.delete(0, "end")
        for name in self.names:
            self.listbox.insert("end", name)
        if keep_popup and sel:
            self.listbox.selection_set(sel[0])

        self._refresh_history()
        self.render()
        self.update_controls()

    def _refresh_history(self):
        for child in self.history_frame.winfo_children():
            child.destroy()
        if not self.history:
            ctk.CTkLabel(self.history_frame, text="No one selected yet.", font=(FONT, 13),
                         text_color=MUTED).pack(pady=12)
        for i, (name, color) in enumerate(self.history, start=1):
            row = ctk.CTkFrame(self.history_frame, fg_color="transparent")
            row.pack(fill="x", pady=3, padx=4)
            ctk.CTkFrame(row, width=16, height=16, corner_radius=8,
                         fg_color=COLOR_HEX[color]).pack(side="left", padx=(0, 8))
            ctk.CTkLabel(row, text=f"{i}. {name}", font=(FONT, 13, "bold"), text_color=TEXT,
                         anchor="w").pack(side="left", fill="x", expand=True)
            ctk.CTkLabel(row, text=color, font=(FONT, 12, "bold"),
                         text_color=COLOR_HEX[color]).pack(side="right")

        picked = {n for n, _ in self.history}
        self.selected_count.configure(text=str(len(self.history)))
        self.remaining_count.configure(text=str(sum(1 for n in self.names if n not in picked)))
        self.count_label.configure(text=f"Participants: {len(self.all_names)}")

    def set_status(self, msg, kind="info"):
        color = {"info": MUTED, "success": SUCCESS, "error": ERROR}[kind]
        self.status_label.configure(text=msg, text_color=color)

    def update_controls(self):
        idle = not self.spinning
        has_names = bool(self.names)

        def state(ok):
            return "normal" if ok else "disabled"

        self.spin_btn.configure(state=state(idle and has_names))
        self.spin_again_btn.configure(state=state(idle and has_names and self.selected is not None))
        self.remove_selected_btn.configure(
            state=state(idle and self.selected is not None and self.selected[0] in self.names))
        self.reset_btn.configure(state=state(idle and bool(self.all_names)))
        self.clear_btn.configure(state=state(idle and (bool(self.all_names) or bool(self.history))))
        for btn in (self.add_btn, self.remove_name_btn):
            btn.configure(state=state(idle))

    def on_close(self):
        for job in (self.spin_job, self.confetti_job):
            if job is not None:
                self.after_cancel(job)
        self.sound.shutdown()
        self.destroy()


if __name__ == "__main__":
    NameColorWheelApp().mainloop()
