"""Friendly macro builder UI pieces for sdpad_gui (dialogs, recorder). Imported by sdpad_gui.py."""
import time
import tkinter as tk
from tkinter import ttk, messagebox

import sdpad_macros as M

# colours are injected by sdpad_gui (set_theme) so the dialogs match the main window
T = dict(BG="#0b0b0d", PANEL="#141417", PANEL2="#1b1b20", BORDER="#2c2c35", FG="#e8e8ea",
         MUTED="#8a8a94", ACCENT="#44d62c")


def set_theme(**kw):
    T.update(kw)


# Tk keysym -> our key names (used by capture + recorder)
SHIFTED_SYMS = {"exclam": "1", "at": "2", "numbersign": "3", "dollar": "4", "percent": "5",
                "asciicircum": "6", "ampersand": "7", "asterisk": "8", "parenleft": "9", "parenright": "0",
                "underscore": "-", "plus": "=", "braceleft": "[", "braceright": "]", "bar": "\\",
                "colon": ";", "quotedbl": "'", "asciitilde": "`", "less": ",", "greater": ".",
                "question": "/"}
PLAIN_SYMS = {"Return": "enter", "Escape": "esc", "BackSpace": "backspace", "Tab": "tab", "ISO_Left_Tab": "tab",
              "space": "space", "Prior": "pageup", "Next": "pagedown", "Delete": "delete", "Insert": "insert",
              "Home": "home", "End": "end", "Left": "left", "Right": "right", "Up": "up", "Down": "down",
              "Caps_Lock": "capslock", "minus": "-", "equal": "=", "bracketleft": "[", "bracketright": "]",
              "backslash": "\\", "semicolon": ";", "apostrophe": "'", "grave": "`", "comma": ",",
              "period": ".", "slash": "/", "Print": "printscreen", "Pause": "pause", "Menu": "menu",
              "Num_Lock": "numlock", "Scroll_Lock": "scrolllock", "KP_Enter": "kpenter",
              "KP_Add": "kp+", "KP_Subtract": "kp-", "KP_Multiply": "kp*", "KP_Divide": "kp/",
              "KP_Decimal": "kp.", "KP_Delete": "kp.", "KP_Insert": "kp0", "KP_End": "kp1", "KP_Down": "kp2",
              "KP_Next": "kp3", "KP_Left": "kp4", "KP_Begin": "kp5", "KP_Right": "kp6", "KP_Home": "kp7",
              "KP_Up": "kp8", "KP_Prior": "kp9"}
MOD_SYMS = {"Shift_L": "lshift", "Shift_R": "rshift", "Control_L": "lctrl", "Control_R": "rctrl",
            "Alt_L": "lalt", "Alt_R": "ralt", "Super_L": "lgui", "Super_R": "rgui", "Meta_L": "lalt",
            "Meta_R": "ralt"}


def keysym_to_name(ks):
    if ks in MOD_SYMS:
        return MOD_SYMS[ks]
    if ks in PLAIN_SYMS:
        return PLAIN_SYMS[ks]
    if ks in SHIFTED_SYMS:
        return SHIFTED_SYMS[ks]
    for i in range(10):
        if ks == f"KP_{i}":
            return f"kp{i}"
    n = ks.lower()
    try:
        M.name_to_usage(n)
        return n
    except ValueError:
        return None


def style_toplevel(win, title):
    win.title(title)
    win.configure(bg=T["BG"], padx=18, pady=14)
    win.resizable(False, False)


def hint(parent, text):
    return ttk.Label(parent, text=text, style="Muted.TLabel", wraplength=420, justify="left")


class StepDialog(tk.Toplevel):
    """Add / edit one step. kind in text|press|wait|mouse|hold. result = step dict or None."""
    SPEEDS = {"Fast (5 ms)": 5, "Normal (10 ms)": 10, "Slow (30 ms)": 30, "Very slow (50 ms)": 50}

    def __init__(self, parent, kind, step=None):
        super().__init__(parent)
        self.result = None
        self.kind = kind
        titles = {"text": "Type text", "press": "Press keys", "wait": "Wait", "mouse": "Mouse click",
                  "hold": "Hold / release a key"}
        style_toplevel(self, titles[kind])
        getattr(self, "_build_" + kind)(step)
        row = ttk.Frame(self)
        row.pack(fill="x", pady=(14, 0))
        ttk.Button(row, text="Cancel", command=self.destroy).pack(side="right", padx=(6, 0))
        ttk.Button(row, text="OK", style="Accent.TButton", command=self._ok).pack(side="right")
        self.bind("<Escape>", lambda e: self.destroy())
        self.transient(parent)
        self.grab_set()
        self.update_idletasks()
        x = parent.winfo_rootx() + 80
        y = parent.winfo_rooty() + 80
        self.geometry(f"+{x}+{y}")
        parent.wait_window(self)

    # -- text
    def _build_text(self, step):
        ttk.Label(self, text="What should the pad type?").pack(anchor="w")
        self.txt = tk.Text(self, width=48, height=5, bg=T["PANEL2"], fg=T["FG"], insertbackground=T["ACCENT"],
                           relief="flat", bd=0, padx=8, pady=8, highlightthickness=1,
                           highlightbackground=T["BORDER"], highlightcolor=T["ACCENT"], wrap="word")
        self.txt.pack(pady=6)
        if step:
            self.txt.insert("1.0", step["text"])
        self.txt.focus_set()
        hint(self, "Letters, numbers and common symbols work. A new line presses Enter, a tab presses Tab.").pack(anchor="w")
        r = ttk.Frame(self)
        r.pack(anchor="w", pady=(10, 0))
        ttk.Label(r, text="Typing speed:").pack(side="left")
        gap = step["gap"] if step else M.DEFAULT_GAP
        label = min(self.SPEEDS, key=lambda k: abs(self.SPEEDS[k] - gap))
        self.speed = tk.StringVar(value=label)
        ttk.Combobox(r, state="readonly", values=list(self.SPEEDS), textvariable=self.speed, width=18).pack(side="left", padx=6)

    # -- press
    def _build_press(self, step):
        ttk.Label(self, text="Hold these modifiers (optional):").pack(anchor="w")
        mf = ttk.Frame(self)
        mf.pack(anchor="w", pady=4)
        self.mods = {m: tk.BooleanVar(value=bool(step and m in step.get("mods", []))) for m in M.MOD_ORDER}
        for m, v in self.mods.items():
            ttk.Checkbutton(mf, text=M.pretty_key(m), variable=v).pack(side="left", padx=(0, 12))
        kf = ttk.Frame(self)
        kf.pack(anchor="w", pady=8)
        ttk.Label(kf, text="Then press:").pack(side="left")
        self.key = tk.StringVar(value=step["key"] if step else "")
        ttk.Combobox(kf, textvariable=self.key, values=M.ALL_KEY_NAMES, width=14).pack(side="left", padx=6)
        ttk.Label(self, text="…or click the box and press the shortcut on your keyboard:").pack(anchor="w", pady=(8, 2))
        self.cap = tk.Entry(self, width=34, justify="center", bg=T["PANEL2"], fg=T["ACCENT"],
                            insertbackground=T["ACCENT"], relief="flat", highlightthickness=1,
                            highlightbackground=T["BORDER"], highlightcolor=T["ACCENT"])
        self.cap.insert(0, "click here, then press your shortcut")
        self.cap.pack(anchor="w", ipady=5)
        self.cap.bind("<KeyPress>", self._capture)

    def _capture(self, e):
        name = keysym_to_name(e.keysym)
        if e.keysym in MOD_SYMS or e.keysym in ("ISO_Level3_Shift",):
            return "break"
        if not name:
            self.cap.delete(0, "end")
            self.cap.insert(0, f"can't use that key ({e.keysym})")
            return "break"
        self.mods["ctrl"].set(bool(e.state & 0x4))
        self.mods["shift"].set(bool(e.state & 0x1) or e.keysym in SHIFTED_SYMS)
        self.mods["alt"].set(bool(e.state & 0x8))
        self.mods["gui"].set(bool(e.state & 0x40))
        self.key.set(name)
        self.cap.delete(0, "end")
        self.cap.insert(0, "✔ " + " + ".join([M.pretty_key(m) for m in M.MOD_ORDER if self.mods[m].get()] + [M.pretty_key(name)]))
        return "break"

    # -- wait
    def _build_wait(self, step):
        ttk.Label(self, text="Pause for how long?").pack(anchor="w")
        r = ttk.Frame(self)
        r.pack(anchor="w", pady=8)
        ms = step["ms"] if step else 500
        self.ms = tk.IntVar(value=ms)
        ttk.Spinbox(r, from_=1, to=60000, increment=50, width=8, textvariable=self.ms).pack(side="left")
        ttk.Label(r, text=" milliseconds").pack(side="left")
        q = ttk.Frame(self)
        q.pack(anchor="w")
        for label, v in (("0.1 s", 100), ("0.25 s", 250), ("0.5 s", 500), ("1 s", 1000), ("2 s", 2000), ("5 s", 5000)):
            ttk.Button(q, text=label, padding=(8, 4), command=lambda v=v: self.ms.set(v)).pack(side="left", padx=(0, 4))
        hint(self, "Use this to wait for a window or page to be ready before the next step.").pack(anchor="w", pady=(10, 0))

    # -- mouse
    def _build_mouse(self, step):
        ttk.Label(self, text="Which mouse button should be clicked?").pack(anchor="w")
        self.btn = tk.StringVar(value=M.MOUSE_NAMES.get(step["btn"], "left") if step else "left")
        ttk.Combobox(self, state="readonly", values=["left", "right", "middle"], textvariable=self.btn,
                     width=12).pack(anchor="w", pady=8)
        hint(self, "Clicks wherever the mouse pointer currently is.").pack(anchor="w")

    # -- hold / release
    def _build_hold(self, step):
        self.mode = tk.StringVar(value="up" if step and step["t"] == "up" else "down")
        r = ttk.Frame(self)
        r.pack(anchor="w")
        ttk.Radiobutton(r, text="Hold the key down", value="down", variable=self.mode).pack(side="left", padx=(0, 14))
        ttk.Radiobutton(r, text="Release the key", value="up", variable=self.mode).pack(side="left")
        kf = ttk.Frame(self)
        kf.pack(anchor="w", pady=8)
        ttk.Label(kf, text="Key:").pack(side="left")
        self.key = tk.StringVar(value=step["key"] if step else "lshift")
        ttk.Combobox(kf, textvariable=self.key, values=list(M.MOD_NAMES_REV) + M.ALL_KEY_NAMES, width=14).pack(side="left", padx=6)
        hint(self, "Advanced: a key stays held until you add a matching 'Release' step. "
                   "Useful for holding Shift or Ctrl across several steps.").pack(anchor="w")

    def _ok(self):
        try:
            self.result = getattr(self, "_get_" + self.kind)()
        except ValueError as e:
            messagebox.showerror("Can't use that", str(e), parent=self)
            return
        self.destroy()

    def _get_text(self):
        text = self.txt.get("1.0", "end-1c")
        if not text:
            raise ValueError("Type some text first.")
        bad = M.can_type(text)
        if bad:
            raise ValueError("The pad can't type these characters: " + " ".join(sorted(set(repr(c) for c in bad))) +
                             "\n\nUse 'Press keys' for special keys.")
        return {"t": "text", "text": text, "gap": self.SPEEDS[self.speed.get()]}

    def _get_press(self):
        key = self.key.get().strip().lower()
        if not key:
            raise ValueError("Choose a key to press (or capture one).")
        M.name_to_usage(key)
        return {"t": "press", "mods": [m for m in M.MOD_ORDER if self.mods[m].get()], "key": key, "gap": M.DEFAULT_GAP}

    def _get_wait(self):
        try:
            ms = int(self.ms.get())
        except (tk.TclError, ValueError):
            raise ValueError("Enter a number of milliseconds.")
        if not 1 <= ms <= 60000:
            raise ValueError("Wait between 1 and 60000 ms.")
        return {"t": "wait", "ms": ms}

    def _get_mouse(self):
        return {"t": "mouse", "btn": {"left": 1, "right": 2, "middle": 4}[self.btn.get()], "gap": M.DEFAULT_GAP}

    def _get_hold(self):
        key = self.key.get().strip().lower()
        M.name_to_usage(key)
        return {"t": self.mode.get(), "key": key, "gap": M.DEFAULT_GAP}


class RecordDialog(tk.Toplevel):
    """Records the user's keystrokes (with timing). result = list of steps or None."""

    def __init__(self, parent):
        super().__init__(parent)
        self.result = None
        style_toplevel(self, "Record keystrokes")
        self.events = []
        self.down = set()
        self.pending = {}
        self.last = None
        self.recording = False
        tk.Label(self, text="●  RECORD", bg=T["BG"], fg="#ff4d4d", font=("DejaVu Sans", 14, "bold")).pack(anchor="w")
        self.msg = tk.StringVar(value="Click Start, then type on your keyboard.\nPauses between keys are recorded too.")
        ttk.Label(self, textvariable=self.msg, wraplength=380).pack(anchor="w", pady=8)
        self.live = tk.Text(self, width=46, height=6, bg=T["PANEL2"], fg=T["FG"], relief="flat", bd=0, padx=8,
                            pady=8, highlightthickness=1, highlightbackground=T["BORDER"], state="disabled")
        self.live.pack()
        row = ttk.Frame(self)
        row.pack(fill="x", pady=(14, 0))
        self.start_btn = ttk.Button(row, text="Start recording", style="Accent.TButton", command=self.start)
        self.start_btn.pack(side="left")
        ttk.Button(row, text="Cancel", command=self.destroy).pack(side="right", padx=(6, 0))
        self.done_btn = ttk.Button(row, text="Use recording", command=self.finish, state="disabled")
        self.done_btn.pack(side="right")
        self.bind("<KeyPress>", self._press)
        self.bind("<KeyRelease>", self._release)
        self.transient(parent)
        self.grab_set()
        parent.wait_window(self)

    def start(self):
        self.recording = True
        self.events.clear()
        self.down.clear()
        self.last = None
        self.start_btn.config(state="disabled")
        self.done_btn.config(state="normal")
        self.msg.set("Recording…  type your keystrokes, then press “Use recording”.")
        self.focus_force()
        self._show()

    def _now(self):
        t = time.monotonic()
        d = 0 if self.last is None else int((t - self.last) * 1000)
        self.last = t
        return min(d, 65535)

    def _press(self, e):
        if not self.recording:
            return
        name = keysym_to_name(e.keysym)
        if not name:
            return "break"
        if name in self.pending:                 # auto-repeat fake release+press
            self.after_cancel(self.pending.pop(name))
            return "break"
        if name in self.down:
            return "break"
        self.down.add(name)
        d = self._now()
        self.events.append((min(d, M.DEFAULT_GAP) if not self.events else d, True, 2, M.name_to_usage(name)))
        self._show()
        return "break"

    def _release(self, e):
        if not self.recording:
            return
        name = keysym_to_name(e.keysym)
        if not name or name not in self.down:
            return "break"
        self.pending[name] = self.after(25, lambda: self._really_release(name))
        return "break"

    def _really_release(self, name):
        self.pending.pop(name, None)
        self.down.discard(name)
        self.events.append((self._now(), False, 2, M.name_to_usage(name)))
        self._show()

    def _show(self):
        self.live.config(state="normal")
        self.live.delete("1.0", "end")
        for s in M.decompile(self.events) if self.events else []:
            self.live.insert("end", M.describe_step(s) + "\n")
        self.live.see("end")
        self.live.config(state="disabled")

    def finish(self):
        for name in list(self.pending):          # flush any release still waiting
            self.after_cancel(self.pending[name])
            self._really_release(name)
        if self.down:
            messagebox.showwarning("Keys still held", "Release all keys before finishing.", parent=self)
            return
        if not self.events:
            messagebox.showinfo("Nothing recorded", "No keystrokes were captured.", parent=self)
            return
        steps = M.decompile(self.events)
        for s in steps:                          # a recording never starts with a pause
            pass
        self.result = steps
        self.destroy()
