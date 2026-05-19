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
        winsound.PlaySound("SystemExclamation", winsound.SND_ALIAS)
except ImportError:
    def _beep():
        print("\a")

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


class PomodoroTimer:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Pomodoro Timer")
        self.root.geometry("340x520")
        self.root.resizable(False, False)
        self.root.configure(bg="#fafafa")

        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TButton", font=("Segoe UI", 10), padding=6)
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
        main = tk.Frame(self.root, bg="#fafafa")
        main.pack(fill=tk.BOTH, expand=True, padx=24, pady=20)

        ttk.Label(main, text="Pomodoro", font=("Segoe UI", 20, "bold"),
                  background="#fafafa").pack(pady=(0, 2))

        self.session_lbl = ttk.Label(main, text="", font=("Segoe UI", 11), background="#fafafa")
        self.session_lbl.pack()

        # canvas ring
        self.canvas = tk.Canvas(main, width=220, height=220, bg="#fafafa",
                                highlightthickness=0)
        self.canvas.pack(pady=(16, 4))
        # background ring, segments ring, center text
        self._ring_bg = self.canvas.create_oval(20, 20, 200, 200,
                                                outline="#e0e0e0", width=10)
        self._ring_fg = self.canvas.create_arc(20, 20, 200, 200,
                                               start=90, extent=359.999,
                                               outline=COLORS["work"]["fg"],
                                               width=10, style="arc")
        self._timer_id = self.canvas.create_text(110, 100, text="25:00",
                                                 font=("Consolas", 38, "bold"),
                                                 fill=COLORS["work"]["fg"])
        self._status_id = self.canvas.create_text(110, 148, text="",
                                                  font=("Segoe UI", 10),
                                                  fill="#888888")

        # progress bar
        self.progress = ttk.Progressbar(main, length=280, mode="determinate")
        self.progress.pack(pady=(0, 12))

        # buttons
        row = tk.Frame(main, bg="#fafafa")
        row.pack()
        self.start_btn = ttk.Button(row, text="Start", command=self._toggle, width=8)
        self.start_btn.pack(side=tk.LEFT, padx=3)
        ttk.Button(row, text="Reset", command=self._reset, width=8).pack(side=tk.LEFT, padx=3)
        ttk.Button(row, text="Skip", command=self._skip, width=8).pack(side=tk.LEFT, padx=3)

        # count + on-top
        info = tk.Frame(main, bg="#fafafa")
        info.pack(pady=(14, 4))
        self.count_lbl = tk.Label(info, text="", font=("Segoe UI", 10),
                                  bg="#fafafa", fg="#555555")
        self.count_lbl.pack(side=tk.LEFT)

        # presets
        preset_frame = tk.Frame(main, bg="#fafafa")
        preset_frame.pack(pady=(6, 0))
        for label, mins in [("25 min", 25), ("15 min", 15), ("5 min", 5)]:
            ttk.Button(preset_frame, text=label, width=7,
                       command=lambda m=mins: self._set_work(m)).pack(side=tk.LEFT, padx=2)

        # settings gear
        bottom = tk.Frame(main, bg="#fafafa")
        bottom.pack(fill=tk.X, pady=(8, 0))
        self.ontop_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(bottom, text="Pin on top", variable=self.ontop_var,
                        command=lambda: self.root.attributes("-topmost", self.ontop_var.get())
                        ).pack(side=tk.LEFT)

        self.status_lbl = tk.Label(bottom, text="Ready", font=("Segoe UI", 9, "italic"),
                                   bg="#fafafa", fg="#999999")
        self.status_lbl.pack(side=tk.RIGHT)

    # —— display —————————————————————————————————————————————————
    def _update(self):
        mins, secs = divmod(self.remaining, 60)
        total = self._total()
        ratio = 1 - self.remaining / total if total else 0
        c = COLORS[self.session]

        self.canvas.itemconfig(self._timer_id, text=f"{mins:02d}:{secs:02d}", fill=c["fg"])
        self.canvas.itemconfig(self._ring_fg, outline=c["fg"],
                               extent=359.999 * ratio if ratio > 0 else 0.001,
                               start=90 - (360 * ratio))
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
