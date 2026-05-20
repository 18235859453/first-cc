"""
Pomodoro Timer — desktop productivity app.
25 min work → 5 min break → repeat (long break every 4 sessions).
"""
import tkinter as tk
from tkinter import ttk
import time
import threading
import json
import os
from datetime import date

try:
    import winsound
    def _beep():
        winsound.PlaySound("MailBeep", winsound.SND_ALIAS)
except ImportError:
    def _beep():
        print("\a")

BG = "#e8f4fd"
CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".pomodoro.json")
WORK = 25 * 60
SHORT_BREAK = 5 * 60
LONG_BREAK = 15 * 60
POMODOROS_BEFORE_LONG = 4

COLORS = {
    "work":     {"fg": "#e74c3c", "bg": "#fde8e8", "label": "Focus Time"},
    "short_break": {"fg": "#27ae60", "bg": "#e8f8ef", "label": "Short Break"},
    "long_break":  {"fg": "#2980b9", "bg": "#e8f0f8", "label": "Long Break"},
}


BTN_TOP = "#c084fc"
BTN_BOT = "#7c3aed"
BTN_HOVER_TOP = "#a855f7"
BTN_HOVER_BOT = "#6d28d9"
BTN_FG = "#ffffff"
RADIUS = 10


def _hex_to_rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))


def _interp(c1, c2, t):
    return "#{:02x}{:02x}{:02x}".format(
        *(int(a + (b - a) * t) for a, b in zip(c1, c2)))


class RoundedButton(tk.Canvas):
    def __init__(self, parent, text="", command=None, width=100, height=36, **kwargs):
        super().__init__(parent, width=width, height=height, bg=BG,
                         highlightthickness=0, **kwargs)
        self.command = command
        self.btn_text = text
        self.btn_width = width
        self.btn_height = height
        self._top = BTN_TOP
        self._bot = BTN_BOT
        self._draw()
        self.bind("<Button-1>", self._click)
        self.bind("<Enter>", lambda e: self._hover(True))
        self.bind("<Leave>", lambda e: self._hover(False))

    def _draw(self):
        self.delete("all")
        r = RADIUS
        w, h = self.btn_width, self.btn_height
        x1, y1, x2, y2 = 2, 2, w - 2, h - 2
        t1, t2 = _hex_to_rgb(self._top), _hex_to_rgb(self._bot)

        for y in range(y1, y2 + 1):
            t = (y - y1) / (y2 - y1)
            color = _interp(t1, t2, t)
            if y < y1 + r:
                dy = y - y1 - r
                dx = int(r - (r**2 - dy**2)**0.5)
                self.create_line(x1 + dx, y, x2 - dx, y, fill=color)
            elif y > y2 - r:
                dy = y - y2 + r
                dx = int(r - (r**2 - dy**2)**0.5)
                self.create_line(x1 + dx, y, x2 - dx, y, fill=color)
            else:
                self.create_line(x1, y, x2, y, fill=color)

        self.create_text(w / 2, h / 2, text=self.btn_text,
                         font=("Segoe UI", 10), fill=BTN_FG)

    def _hover(self, enter):
        self._top = BTN_HOVER_TOP if enter else BTN_TOP
        self._bot = BTN_HOVER_BOT if enter else BTN_BOT
        self._draw()

    def _click(self, event):
        if self.command:
            self.command()

    def config(self, **kwargs):
        if "text" in kwargs:
            self.btn_text = kwargs["text"]
            self._draw()


class PomodoroTimer:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Pomodoro Timer")
        self.root.geometry("340x520")
        self.root.resizable(False, False)
        self.root.configure(bg=BG)

        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TProgressbar", thickness=8)

        self.remaining = WORK
        self.running = False
        self.pomo_count = 0
        self.session = "work"
        self.today = date.today()
        self._load()

        self._build()
        self._update()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    # —— persistence —————————————————————————————————————————————
    def _load(self):
        try:
            with open(CONFIG_FILE) as f:
                d = json.load(f)
            if d.get("date") == str(self.today):
                self.pomo_count = d.get("count", 0)
        except (FileNotFoundError, json.JSONDecodeError):
            pass

    def _save(self):
        with open(CONFIG_FILE, "w") as f:
            json.dump({"date": str(self.today), "count": self.pomo_count}, f)

    # —— UI ——————————————————————————————————————————————————————
    def _build(self):
        main = tk.Frame(self.root, bg=BG)
        main.pack(fill=tk.BOTH, expand=True, padx=24, pady=20)

        self.session_lbl = ttk.Label(main, text="", font=("Segoe UI", 11), background=BG)
        self.session_lbl.pack()

        # canvas ring
        self.canvas = tk.Canvas(main, width=220, height=220, bg=BG,
                                highlightthickness=0)
        self.canvas.pack(pady=(16, 4))
        # background ring, segments ring, center text
        self._ring_bg = self.canvas.create_oval(20, 20, 200, 200,
                                                outline="#e0e0e0", width=10)
        self._ring_fg = self.canvas.create_arc(20, 20, 200, 200,
                                               start=90, extent=0,
                                               outline=COLORS["work"]["fg"],
                                               width=10, style="arc",
                                               state="hidden")
        self._timer_id = self.canvas.create_text(110, 100, text="25:00",
                                                 font=("Consolas", 38, "bold"),
                                                 fill=COLORS["work"]["fg"])
        self._status_id = self.canvas.create_text(110, 148, text="",
                                                  font=("Segoe UI", 10),
                                                  fill="#888888")

        # progress bar
        self.progress = ttk.Progressbar(main, length=280, mode="determinate")
        self.progress.pack(pady=(0, 12))
        self.progress.bind("<Button-1>", self._seek)
        self.progress.bind("<B1-Motion>", self._seek)

        # buttons
        row = tk.Frame(main, bg=BG)
        row.pack()
        self.start_btn = RoundedButton(row, text="Start", command=self._toggle, width=90)
        self.start_btn.pack(side=tk.LEFT, padx=3)
        RoundedButton(row, text="Reset", command=self._reset, width=90).pack(side=tk.LEFT, padx=3)
        RoundedButton(row, text="Skip", command=self._skip, width=90).pack(side=tk.LEFT, padx=3)

        # count + on-top
        info = tk.Frame(main, bg=BG)
        info.pack(pady=(14, 4))
        self.count_lbl = tk.Label(info, text="", font=("Segoe UI", 10),
                                  bg=BG, fg="#555555")
        self.count_lbl.pack(side=tk.LEFT)

        # presets
        preset_frame = tk.Frame(main, bg=BG)
        preset_frame.pack(pady=(6, 0))
        for label, mins in [("25 min", 25), ("15 min", 15), ("5 min", 5)]:
            RoundedButton(preset_frame, text=label, width=80,
                          command=lambda m=mins: self._set_work(m)).pack(side=tk.LEFT, padx=2)

        # settings gear
        bottom = tk.Frame(main, bg=BG)
        bottom.pack(fill=tk.X, pady=(8, 0))
        self.ontop_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(bottom, text="Pin on top", variable=self.ontop_var,
                        command=lambda: self.root.attributes("-topmost", self.ontop_var.get())
                        ).pack(side=tk.LEFT)

        self.status_lbl = tk.Label(bottom, text="Ready", font=("Segoe UI", 9, "italic"),
                                   bg=BG, fg="#999999")
        self.status_lbl.pack(side=tk.RIGHT)

    # —— display —————————————————————————————————————————————————
    def _update(self):
        mins, secs = divmod(self.remaining, 60)
        total = self._total()
        ratio = 1 - self.remaining / total if total else 0
        c = COLORS[self.session]

        self.canvas.itemconfig(self._timer_id, text=f"{mins:02d}:{secs:02d}", fill=c["fg"])
        if ratio > 0:
            self.canvas.itemconfig(self._ring_fg, outline=c["fg"],
                                   extent=359.999 * ratio,
                                   start=90 - (360 * ratio),
                                   state="normal")
        else:
            self.canvas.itemconfig(self._ring_fg, state="hidden")
        self.canvas.itemconfig(self._status_id, text=c["label"])
        self.session_lbl.config(text=c["label"], foreground=c["fg"])
        self.progress["value"] = ratio * 100
        self.count_lbl.config(text=f"Today: {self.pomo_count} completed")

    def _total(self):
        return WORK if self.session == "work" else (
            LONG_BREAK if self.session == "long_break" else SHORT_BREAK
        )

    # —— timer ———————————————————————————————————————————————————
    def _toggle(self):
        if self.running:
            self.running = False
            self.start_btn.config(text="Start")
            self.status_lbl.config(text="Paused")
        else:
            self.running = True
            self.start_btn.config(text="Pause")
            self.status_lbl.config(text={
                "work": "Focusing…", "short_break": "Break…",
                "long_break": "Long break…"
            }.get(self.session, ""))
            threading.Thread(target=self._tick, daemon=True).start()

    def _tick(self):
        while self.running and self.remaining > 0:
            time.sleep(1)
            if not self.running:
                return
            self.remaining -= 1
            self.root.after(0, self._update)
        if self.remaining <= 0 and self.running:
            self.running = False
            self.root.after(0, self._done)

    def _done(self):
        _beep()
        self.root.lift()
        self.root.attributes("-topmost", True)
        self.root.after(600, lambda: self.root.attributes("-topmost", self.ontop_var.get()))

        if self.session == "work":
            self.pomo_count += 1
            self._save()
            if self.pomo_count % POMODOROS_BEFORE_LONG == 0:
                self.session = "long_break"
                self.remaining = LONG_BREAK
            else:
                self.session = "short_break"
                self.remaining = SHORT_BREAK
        else:
            self.session = "work"
            self.remaining = WORK

        self.start_btn.config(text="Start")
        self.status_lbl.config(text="Done!")
        self._update()

    def _reset(self):
        self.running = False
        self.session = "work"
        self.remaining = WORK
        self.start_btn.config(text="Start")
        self.status_lbl.config(text="Reset")
        self._update()

    def _skip(self):
        self.running = False
        self.remaining = 0
        self._done()

    def _seek(self, event):
        total = self._total()
        ratio = max(0, min(1, event.x / self.progress.winfo_width()))
        self.remaining = int(total * (1 - ratio))
        self._update()

    def _set_work(self, mins):
        self.running = False
        self.session = "work"
        self.remaining = mins * 60
        self.start_btn.config(text="Start")
        self.status_lbl.config(text=f"Set to {mins} min")
        self._update()

    def _on_close(self):
        self.running = False
        self.root.destroy()

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    PomodoroTimer().run()
