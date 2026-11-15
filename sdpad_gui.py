#!/usr/bin/env python3
"""sdpad_gui.py - GUI for SDINNOVATION "SIDE-KEYBOARD" macro pads (Linux, Tkinter, no deps).

Needs sdpad.py next to it. Run:  python3 sdpad_gui.py
"""
import os, sys, time, json, colorsys, datetime
import tkinter as tk
from tkinter import ttk, messagebox, colorchooser, simpledialog

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sdpad
import sdpad_macros as M
import sdpad_macro_ui as MUI
import pad_canvas
from sdpad import (Pad, KEYS, KEYS_REV, CONSUMER, CONS_REV, MODS, parse_action,
                   describe, LIGHT_MODES)

BACKUP_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "backups")

# Device-specific physical layouts (key slots 0..N-1, row-major from top-left; dials start at 16)
DEVICE_LAYOUTS = {
    0xDCFE: dict(key_count=9,  cols=3, rows=3, dial_count=2, name="SD-9 PRO"),
    0x2473: dict(key_count=12, cols=3, rows=4, dial_count=2, name="SIDE-KEYBOARD"),
}
DEFAULT_LAYOUT = dict(key_count=9, cols=3, rows=3, dial_count=2, name="MACRO PAD")

# ---- theme (dark + neon green accent, gaming-peripheral style)
BG       = "#0b0b0d"
PANEL    = "#141417"
PANEL2   = "#1b1b20"
KEY_BG   = "#1d1d23"
KEY_HOVER = "#26262e"
BORDER   = "#2c2c35"
FG       = "#e8e8ea"
MUTED    = "#8a8a94"
ACCENT   = "#44d62c"
ACCENT_DK = "#2f9a1e"
DANGER   = "#ff4d4d"
FONT     = ("Segoe UI", 10) if sys.platform == "win32" else ("DejaVu Sans", 10)
FONT_B   = FONT + ("bold",)
FONT_H   = (FONT[0], 16, "bold")

# Tk keysym -> our key name
KEYSYM = {"Return": "enter", "Escape": "esc", "BackSpace": "backspace", "Tab": "tab",
          "space": "space", "Prior": "pageup", "Next": "pagedown", "Delete": "delete",
          "Insert": "insert", "Home": "home", "End": "end", "Left": "left", "Right": "right",
          "Up": "up", "Down": "down", "Caps_Lock": "capslock", "minus": "-", "equal": "=",
          "bracketleft": "[", "bracketright": "]", "backslash": "\\", "semicolon": ";",
          "apostrophe": "'", "grave": "`", "comma": ",", "period": ".", "slash": "/",
          "Print": "printscreen", "Pause": "pause", "Menu": "menu", "Num_Lock": "numlock",
          "Scroll_Lock": "scrolllock",
          # Keypad / numpad
          "KP_0": "kp0", "KP_1": "kp1", "KP_2": "kp2", "KP_3": "kp3", "KP_4": "kp4",
          "KP_5": "kp5", "KP_6": "kp6", "KP_7": "kp7", "KP_8": "kp8", "KP_9": "kp9",
          "KP_Divide": "kp/", "KP_Multiply": "kp*", "KP_Subtract": "kp-", "KP_Add": "kp+",
          "KP_Enter": "kpenter", "KP_Decimal": "kp.", "KP_Separator": "kp.",
          "KP_Insert": "kp0", "KP_End": "kp1", "KP_Down": "kp2", "KP_Next": "kp3",
          "KP_Left": "kp4", "KP_Begin": "kp5", "KP_Right": "kp6", "KP_Home": "kp7",
          "KP_Up": "kp8", "KP_Prior": "kp9", "KP_Delete": "kp.", "KP_Equal": "kp="}

MOD_USAGES = {0xE0: "lctrl", 0xE1: "lshift", 0xE2: "lalt", 0xE3: "lgui",
              0xE4: "rctrl", 0xE5: "rshift", 0xE6: "ralt", 0xE7: "rgui"}
MOD_USAGES_REV = {v: k for k, v in MOD_USAGES.items()}

ACTION_TYPES = ["Keystroke", "Media key", "Keypad", "Mouse", "Run macro", "Keyboard control", "Disabled", "Raw bytes"]
MOUSE_CHOICES = ["left", "right", "middle", "wheelup", "wheeldown", "back", "forward"]


def _slot_to_visual(i, layout):
    if not layout or i >= layout.get("key_count", 0):
        return None
    cols = layout.get("cols", 3)
    rows = layout.get("rows", 3)
    if layout.get("name") == "SIDE-KEYBOARD" and cols == 3 and rows == 4:
        col = i // rows
        row_from_bottom = i % rows
        return (rows - 1 - row_from_bottom, col)
    return (i // cols, i % cols)


def key_slot_label(i, layout=None):
    if i < 16:
        if layout and layout.get("name") == "SIDE-KEYBOARD" and layout.get("cols") == 3 and layout.get("rows") == 4 and i < layout.get("key_count", 0):
            return f"Key K{i + 1} (slot {i})"
        return f"Key {i + 1}"
    d, k = divmod(i - 16, 3)
    return f"Dial {d + 1} {['press', 'turn right', 'turn left'][k]}"


def hex_to_hsv255(hexcol):
    r, g, b = (int(hexcol.lstrip('#')[i:i + 2], 16) / 255 for i in (0, 2, 4))
    h, s, v = colorsys.rgb_to_hsv(r, g, b)
    return int(h * 255), int(s * 255), int(v * 255)


def hsv255_to_hex(h, s, v):
    r, g, b = colorsys.hsv_to_rgb(h / 255, s / 255, v / 255)
    return "#%02x%02x%02x" % (int(r * 255), int(g * 255), int(b * 255))


def gui_describe(e):
    """Like sdpad.describe but with 1-based macro numbers."""
    if e[0] == 0x60:
        mode = {0: "", 1: ", repeats while held", 2: ", repeats until any key", 3: ", toggles repeat"}.get(e[3], "")
        times = f" x{e[2]}" if e[3] == 0 and e[2] > 1 else ""
        return f"Macro {e[1] + 1}{times}{mode}"
    if e[0] == 0x1F and e[1] == 0x13:
        return "Profile switch"
    if e[0] == 0x1F and e[1] == 0x19:
        return "Keyboard lock"
    if e[0] == 0x40 and e[1] == 0x01:
        return "Power"
    if e[0] == 0x40 and e[1] == 0x02:
        return "Sleep"
    if e[0] == 0x40 and e[1] == 0x04:
        return "Wakeup"
    if e[0] == 0x11:
        return describe(e)
    return describe(e)


NAMES_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "macro_names.json")


# ------------------------------------------------------------------ app
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("SD Macro Pad Configurator")
        self.geometry("1180x820")
        self.pad = None
        self.table = []
        self.selected = None
        self.macros = {}
        self.layout = dict(DEFAULT_LAYOUT)
        self.key_count = self.layout["key_count"]
        self.cols = self.layout["cols"]
        self.rows = self.layout["rows"]
        self.dial_count = self.layout["dial_count"]
        self.style = ttk.Style(self)
        self.apply_theme()

        header = tk.Frame(self, bg=BG)
        header.pack(fill="x", padx=16, pady=(14, 4))
        tk.Label(header, text="SD", bg=BG, fg=ACCENT, font=FONT_H).pack(side="left")
        tk.Label(header, text=" MACRO PAD", bg=BG, fg=FG, font=FONT_H).pack(side="left")
        tk.Frame(self, bg=ACCENT, height=2).pack(fill="x", padx=16)

        top = ttk.Frame(self, padding=(16, 8))
        top.pack(fill="x")
        self.status = tk.StringVar(value="Not connected")
        ttk.Label(top, textvariable=self.status, style="Muted.TLabel").pack(side="left")
        ttk.Button(top, text="Reconnect / Refresh", command=self.connect).pack(side="right")
        ttk.Button(top, text="Backup all profiles", command=self.backup_profiles).pack(side="right", padx=(0, 8))
        ttk.Label(top, text="   PROFILE", style="Muted.TLabel").pack(side="left")
        self.profile_var = tk.IntVar(value=1)
        self.profile_box = ttk.Combobox(top, width=3, state="readonly", textvariable=self.profile_var,
                                        values=[1, 2, 3, 4, 5, 6])
        self.profile_box.pack(side="left")
        self.profile_box.bind("<<ComboboxSelected>>", lambda e: self.change_profile())

        self.notebook = ttk.Notebook(self)
        nb = self.notebook
        nb.pack(fill="both", expand=True, padx=6, pady=6)
        self.keys_tab = ttk.Frame(nb)
        self.macro_tab = ttk.Frame(nb)
        self.light_tab = ttk.Frame(nb)
        nb.add(self.keys_tab, text="Keys")
        nb.add(self.macro_tab, text="Macros")
        nb.add(self.light_tab, text="Lighting")
        self.build_keys_tab()
        self.build_macro_tab()
        self.build_light_tab()
        self.after(100, self.connect)

    def apply_theme(self):
        self.configure(bg=BG)
        st = self.style
        st.theme_use("clam")
        self.option_add("*Font", FONT)
        self.option_add("*TCombobox*Listbox.background", PANEL2)
        self.option_add("*TCombobox*Listbox.foreground", FG)
        self.option_add("*TCombobox*Listbox.selectBackground", ACCENT)
        self.option_add("*TCombobox*Listbox.selectForeground", "#000000")
        self.option_add("*TCombobox*Listbox.font", FONT)
        st.configure(".", background=BG, foreground=FG, fieldbackground=PANEL2, bordercolor=BORDER,
                     lightcolor=BG, darkcolor=BG, troughcolor=PANEL2, focuscolor=ACCENT, font=FONT)
        st.configure("TFrame", background=BG)
        st.configure("TLabel", background=BG, foreground=FG)
        st.configure("Muted.TLabel", background=BG, foreground=MUTED)
        st.configure("TLabelframe", background=BG, bordercolor=BORDER, relief="solid", borderwidth=1)
        st.configure("TLabelframe.Label", background=BG, foreground=ACCENT, font=FONT_B)
        st.configure("TNotebook", background=BG, borderwidth=0, tabmargins=(0, 6, 0, 0))
        st.configure("TNotebook.Tab", background=BG, foreground=MUTED, padding=(22, 9),
                     borderwidth=0, font=FONT_B)
        st.map("TNotebook.Tab", background=[("selected", BG)], foreground=[("selected", ACCENT), ("active", FG)],
               bordercolor=[("selected", ACCENT)], lightcolor=[("selected", ACCENT)])
        st.configure("TButton", background=PANEL2, foreground=FG, bordercolor=BORDER, padding=(14, 7),
                     relief="flat", font=FONT_B)
        st.map("TButton", background=[("active", KEY_HOVER), ("pressed", BORDER)],
               bordercolor=[("active", ACCENT)])
        st.configure("Accent.TButton", background=ACCENT, foreground="#000000", bordercolor=ACCENT,
                     padding=(18, 8), font=FONT_B)
        st.map("Accent.TButton", background=[("active", "#5cf044"), ("pressed", ACCENT_DK)],
               bordercolor=[("active", "#5cf044")])
        st.configure("TEntry", fieldbackground=PANEL2, foreground=FG, insertcolor=ACCENT,
                     bordercolor=BORDER, padding=4)
        st.configure("TCombobox", fieldbackground=PANEL2, background=PANEL2, foreground=FG,
                     arrowcolor=ACCENT, bordercolor=BORDER, padding=4, selectbackground=PANEL2,
                     selectforeground=FG)
        st.map("TCombobox", fieldbackground=[("readonly", PANEL2)], foreground=[("readonly", FG)],
               bordercolor=[("focus", ACCENT)])
        st.configure("TSpinbox", fieldbackground=PANEL2, foreground=FG, arrowcolor=ACCENT,
                     bordercolor=BORDER, insertcolor=ACCENT, background=PANEL2, padding=4)
        st.configure("TCheckbutton", background=BG, foreground=FG, indicatorcolor=PANEL2,
                     indicatorbackground=PANEL2, focuscolor=BG)
        st.map("TCheckbutton", indicatorcolor=[("selected", ACCENT)], background=[("active", BG)],
               foreground=[("active", ACCENT)])
        st.configure("Horizontal.TScale", background=BG, troughcolor=PANEL2, bordercolor=BORDER)
        st.map("Horizontal.TScale", background=[("active", ACCENT)])
        st.configure("TSeparator", background=BORDER)
        st.configure("Treeview", background=PANEL2, fieldbackground=PANEL2, foreground=FG, rowheight=30,
                     borderwidth=0, font=FONT)
        st.map("Treeview", background=[("selected", ACCENT)], foreground=[("selected", "#000000")])
        st.configure("Treeview.Heading", background=PANEL, foreground=MUTED, relief="flat", font=FONT_B, padding=6)
        st.map("Treeview.Heading", background=[("active", PANEL)])
        st.configure("TRadiobutton", background=BG, foreground=FG, indicatorcolor=PANEL2, focuscolor=BG)
        st.map("TRadiobutton", indicatorcolor=[("selected", ACCENT)], background=[("active", BG)],
               foreground=[("active", ACCENT)])
        for orient in ("Vertical", "Horizontal"):
            st.configure(f"{orient}.TScrollbar", background=BORDER, troughcolor=PANEL, bordercolor=PANEL,
                         lightcolor=BORDER, darkcolor=BORDER, arrowcolor=ACCENT, gripcount=0, relief="flat")
            st.map(f"{orient}.TScrollbar", background=[("active", ACCENT_DK), ("pressed", ACCENT)])

    def make_tile(self, parent, command, height):
        b = tk.Button(parent, width=15, height=height, wraplength=110, justify="center", command=command,
                      bg=KEY_BG, fg=FG, activebackground=KEY_HOVER, activeforeground=FG,
                      relief="flat", bd=0, highlightthickness=2, highlightbackground=BORDER,
                      highlightcolor=ACCENT, font=FONT, cursor="hand2")
        b._sel = False
        b.bind("<Enter>", lambda e: b.config(bg=KEY_HOVER) if not b._sel else None)
        b.bind("<Leave>", lambda e: b.config(bg=PANEL2 if b._sel else KEY_BG))
        return b

    # -- helpers
    def guard(self, fn):
        try:
            return fn()
        except SystemExit as e:
            messagebox.showerror("Device", str(e))
        except Exception as e:
            messagebox.showerror("Error", f"{type(e).__name__}: {e}")

    def apply_layout(self, layout):
        self.layout = dict(layout)
        self.key_count = self.layout["key_count"]
        self.cols = self.layout["cols"]
        self.rows = self.layout["rows"]
        self.dial_count = self.layout["dial_count"]
        if hasattr(self, "pad_canvas"):
            self.pad_canvas.set_layout(self.layout)
        self.rebuild_perkey_grid()
        # Refresh macro trigger slot choices if macro tab is built
        if hasattr(self, "trig_slots"):
            slots = list(range(self.key_count)) + list(range(16, 16 + self.dial_count * 3))
            self.trig_slots = {key_slot_label(i, self.layout): i for i in slots}
            self.trig_ctl_box.config(values=list(self.trig_slots))
            if self.trig_ctl.get() not in self.trig_slots:
                self.trig_ctl.set(key_slot_label(0, self.layout))

    def connect(self):
        def go():
            if self.pad:
                try:
                    if self.pad.fd is not None:
                        os.close(self.pad.fd)
                except OSError:
                    pass
                try:
                    if getattr(self.pad, "hid_dev", None):
                        self.pad.hid_dev.close()
                except Exception:
                    pass
            self.pad = Pad()
            info = self.pad.info()
            self.profile_var.set(info["active"] + 1)
            layout = DEVICE_LAYOUTS.get(info.get("pid"), DEFAULT_LAYOUT)
            self.apply_layout(layout)
            self.status.set(f"Connected: {self.pad.path}   PID {info['pid']:04X}   "
                            f"firmware {info['firmware']}   profiles {info['profiles']}   "
                            f"layout {self.key_count} keys ({self.cols}x{self.rows}), {self.dial_count} dials")
            self.refresh_all()
        self.guard(go)

    def refresh_all(self):
        self.table = self.pad.read_table()
        self.refresh_keys()
        self.load_macros()
        self.load_light()

    def change_profile(self):
        def go():
            self._switch_to_profile(self.profile_var.get() - 1, update_ui=True)
        self.guard(go)

    def _switch_to_profile(self, target, update_ui=False):
        self.pad.select_profile(target)
        deadline = time.time() + 2.0
        info = self.pad.info()
        while time.time() < deadline and info.get("active") != target:
            time.sleep(0.1)
            info = self.pad.info()
        time.sleep(0.15)
        self.table = self.pad.read_table()
        if update_ui:
            try:
                self.load_light()
            except Exception:
                pass
            self.refresh_keys()
            self.status.set(f"Connected: {self.pad.path}   PID {info['pid']:04X}   "
                            f"firmware {info['firmware']}   profiles {info['profiles']}   "
                            f"layout {self.key_count} keys ({self.cols}x{self.rows}), {self.dial_count} dials"
                            f"   profile {info.get('active', target) + 1}")
        return info

    def backup_profiles(self):
        if not self.pad:
            messagebox.showinfo("Backup", "Not connected.")
            return

        def go():
            info = self.pad.info()
            nprofiles = info.get("profiles", 1)
            orig = info.get("active", self.profile_var.get() - 1)
            sdpad_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sdpad.py")
            ts = datetime.datetime.now().strftime("%Y%m%d-%H%M")
            out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), f"sdpad-backup-{ts}.txt")
            lines = []
            lines.append(f"# sdpad backup {ts}")
            lines.append(f"# device: PID {info.get('pid', 0):04X} firmware {info.get('firmware')} profiles {nprofiles}")
            lines.append("")
            for p in range(nprofiles):
                self._switch_to_profile(p, update_ui=False)
                table = self.pad.read_table()
                lines.append(f"# --- Profile {p + 1} ---")
                lines.append(f"python3 {sdpad_path} profile {p + 1}")
                for i, e in enumerate(table):
                    act = sdpad.action_to_cli(tuple(e))
                    # comment with human label
                    try:
                        desc = gui_describe(tuple(e))
                    except Exception:
                        desc = ""
                    lines.append(f"python3 {sdpad_path} set {i} {act}  # {key_slot_label(i, self.layout)}: {desc}")
                lines.append("")
            with open(out_path, "w", encoding="utf-8") as f:
                f.write("\n".join(lines))
            # restore original
            self._switch_to_profile(orig, update_ui=True)
            self.profile_var.set(orig + 1)
            self.status.set(f"Backup saved: {out_path}")
            messagebox.showinfo("Backup", f"Saved backup for {nprofiles} profiles to:\n{out_path}")
        self.guard(go)

    # ================================================================== KEYS TAB
    def build_keys_tab(self):
        # Master container for Keys tab
        main_box = ttk.Frame(self.keys_tab, padding=12)
        main_box.pack(fill="both", expand=True)

        # LEFT COLUMN: Graphical Hardware Pad + Quick Legend
        left_col = ttk.Frame(main_box)
        left_col.pack(side="left", fill="both", padx=(0, 16))

        info_header = ttk.Frame(left_col)
        info_header.pack(fill="x", pady=(0, 6))
        ttk.Label(info_header, text="PHYSICAL KEYPAD PREVIEW", font=FONT_B, foreground=ACCENT).pack(side="left")
        ttk.Label(info_header, text="• Click any key or dial to configure", style="Muted.TLabel").pack(side="left", padx=8)

        # Pad canvas instance
        self.pad_canvas = pad_canvas.PadCanvas(left_col, on_select_slot=self.select_key, layout=self.layout)
        self.pad_canvas.pack(fill="both", expand=True)

        # Legend pill bar at the bottom
        leg = ttk.Frame(left_col)
        leg.pack(fill="x", pady=(8, 0))
        for cat_name, fg, bg in (("MACRO", "#ff9900", "#2d1f0b"), ("MEDIA", "#00b4d8", "#0b2530"),
                                 ("KEY", "#a0a0b0", "#1e1e24"), ("MOUSE", "#9d4edd", "#251233"),
                                 ("OFF", "#555560", "#141416")):
            pill = tk.Label(leg, text=f" {cat_name} ", bg=bg, fg=fg, font=("DejaVu Sans", 7, "bold"), relief="flat", bd=0)
            pill.pack(side="left", padx=3)
        ttk.Label(leg, text="= Action type", style="Muted.TLabel", font=("DejaVu Sans", 8)).pack(side="left", padx=4)

        # RIGHT COLUMN: Idiot-Proof Configuration Inspector
        right_col = ttk.Frame(main_box)
        right_col.pack(side="left", fill="both", expand=True)

        ed_outer = ttk.LabelFrame(right_col, text="KEY CONFIGURATION", padding=(8, 8))
        ed_outer.pack(fill="both", expand=True)

        ed_canvas = tk.Canvas(ed_outer, bg=BG, highlightthickness=0, bd=0)
        ed_scroll = ttk.Scrollbar(ed_outer, orient="vertical", command=ed_canvas.yview)
        ed_canvas.configure(yscrollcommand=ed_scroll.set)
        ed_scroll.pack(side="right", fill="y")
        ed_canvas.pack(side="left", fill="both", expand=True)

        ed = ttk.Frame(ed_canvas)
        ed_window = ed_canvas.create_window((0, 0), window=ed, anchor="nw")

        def _ed_on_configure(event=None):
            ed_canvas.configure(scrollregion=ed_canvas.bbox("all"))
            ed_canvas.itemconfig(ed_window, width=ed_canvas.winfo_width())
        ed.bind("<Configure>", _ed_on_configure)
        ed_canvas.bind("<Configure>", _ed_on_configure)

        def _ed_mousewheel(event):
            if event.delta:
                ed_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
            elif event.num == 4:
                ed_canvas.yview_scroll(-3, "units")
            elif event.num == 5:
                ed_canvas.yview_scroll(3, "units")
        ed_canvas.bind_all("<MouseWheel>", _ed_mousewheel)
        ed_canvas.bind_all("<Button-4>", _ed_mousewheel)
        ed_canvas.bind_all("<Button-5>", _ed_mousewheel)

        # Top status bar of selected control
        self.ed_title = tk.StringVar(value="Select a Key or Dial to Configure")
        ttk.Label(ed, textvariable=self.ed_title, font=FONT_H, foreground=ACCENT).pack(anchor="w")
        self.ed_subtitle = tk.StringVar(value="Click any key on the visual pad to inspect or change its assignment.")
        ttk.Label(ed, textvariable=self.ed_subtitle, style="Muted.TLabel", wraplength=480).pack(anchor="w", pady=(2, 10))

        # Easy Action Category Selector with clear explanations
        ttk.Label(ed, text="ACTION TYPE", style="Muted.TLabel").pack(anchor="w")
        cat_bar = ttk.Frame(ed)
        cat_bar.pack(fill="x", pady=(4, 10))
        
        self.type_var = tk.StringVar(value=ACTION_TYPES[0])
        # Segmented action buttons or clean combobox with large clear prompt
        cb = ttk.Combobox(cat_bar, state="readonly", values=ACTION_TYPES, textvariable=self.type_var, font=FONT_B, width=20)
        cb.pack(side="left")
        cb.bind("<<ComboboxSelected>>", lambda e: self.show_type_panel())

        # Quick preset buttons right next to it
        ttk.Label(cat_bar, text="  Quick presets:", style="Muted.TLabel").pack(side="left", padx=(10, 4))
        for p_name, p_act in (("Mute", "media:mute"), ("Vol +", "media:volup"), ("Vol -", "media:voldown"), ("Copy", "ctrl+c"), ("Paste", "ctrl+v"), ("Profile", "profile:switch")):
            ttk.Button(cat_bar, text=p_name, padding=(6, 4), command=lambda a=p_act: self.apply_preset(a)).pack(side="left", padx=2)

        ttk.Separator(ed).pack(fill="x", pady=6)

        self.panel_host = ttk.Frame(ed)
        self.panel_host.pack(fill="both", expand=True, pady=6)

        # 1. KEYSTROKE PANEL (Idiot-proof shortcut recorder + manual pickers)
        self.p_key = ttk.Frame(self.panel_host)
        
        card1 = ttk.LabelFrame(self.p_key, text="Press a shortcut on your keyboard", padding=10)
        card1.pack(fill="x", pady=(0, 10))
        self.capture = tk.Entry(card1, width=32, justify="center", bg=PANEL2, fg=ACCENT, insertbackground=ACCENT,
                                font=("DejaVu Sans", 11, "bold"), relief="flat", highlightthickness=1,
                                highlightbackground=BORDER, highlightcolor=ACCENT)
        self.capture.insert(0, "Click here, then press keys...")
        self.capture.pack(fill="x", ipady=8, pady=(4, 6))
        self.capture.bind("<KeyPress>", self.on_capture)
        ttk.Label(card1, text="Automatically recognizes any combo like Ctrl+C, Alt+Tab, Win+D, F1-F24.", style="Muted.TLabel").pack(anchor="w")

        card2 = ttk.LabelFrame(self.p_key, text="Or customize modifiers and key manually", padding=10)
        card2.pack(fill="x")
        self.mod_vars = {n: tk.BooleanVar() for n in ("ctrl", "shift", "alt", "gui")}
        mf = ttk.Frame(card2)
        mf.pack(anchor="w", pady=(0, 6))
        for n, v in self.mod_vars.items():
            ttk.Checkbutton(mf, text=n.capitalize() if n != "gui" else "Win/Super", variable=v).pack(side="left", padx=6)
        kf = ttk.Frame(card2)
        kf.pack(anchor="w", pady=4)
        ttk.Label(kf, text="Target Key:").pack(side="left")
        self.key_var = tk.StringVar()
        ttk.Combobox(kf, textvariable=self.key_var, values=[""] + sorted(KEYS), width=16).pack(side="left", padx=6)

        sc = ttk.LabelFrame(self.p_key, text="Shortcuts / function keys", padding=10)
        sc.pack(fill="x", pady=(10, 0))
        ttk.Label(sc, text="Common shortcuts:").pack(anchor="w")
        srow = ttk.Frame(sc)
        srow.pack(anchor="w", pady=2)
        for lbl, combo in (("Ctrl+A", "ctrl+a"), ("Ctrl+C", "ctrl+c"), ("Ctrl+V", "ctrl+v"),
                           ("Ctrl+S", "ctrl+s"), ("Ctrl+G", "ctrl+g"), ("Ctrl+Z", "ctrl+z")):
            ttk.Button(srow, text=lbl, padding=(6, 4), command=lambda c=combo: self.apply_shortcut_combo(c)).pack(side="left", padx=2, pady=2)
        ttk.Label(sc, text="F13–F24:").pack(anchor="w", pady=(6, 0))
        frow = ttk.Frame(sc)
        frow.pack(anchor="w", pady=2)
        for i in range(13, 25):
            ttk.Button(frow, text=f"F{i}", padding=(4, 3), width=4, command=lambda k=f"f{i}": self.apply_shortcut_combo(k)).pack(side="left", padx=1, pady=1)
        # Keypad keys are supported via capture (e.g. KP_6 -> kp6) and the key dropdown (kp0-kp9, kp/, kp*, ...).
        ttk.Label(sc, text="Common keys:").pack(anchor="w", pady=(6, 0))
        crow = ttk.Frame(sc)
        crow.pack(anchor="w", pady=2)
        for lbl, key in (("Caps Lock", "capslock"), ("Num Lock", "numlock"), ("Scroll Lock", "scrolllock"),
                         ("Lock Caps", "locking_caps"), ("Lock Num", "locking_num"), ("Lock Scroll", "locking_scroll")):
            ttk.Button(crow, text=lbl, padding=(4, 3), command=lambda k=key: self.apply_shortcut_combo(k)).pack(side="left", padx=1, pady=1)
        crow2 = ttk.Frame(sc)
        crow2.pack(anchor="w", pady=1)
        for lbl, key in (("Insert", "insert"), ("Delete", "delete"), ("PrtSc", "printscreen"), ("Pause", "pause")):
            ttk.Button(crow2, text=lbl, padding=(4, 3), command=lambda k=key: self.apply_shortcut_combo(k)).pack(side="left", padx=1, pady=1)
        ttk.Label(sc, text="Mouse move is available under Mouse actions. 'Custom' key combinations can be set via Keystroke capture/manual.",
                  style="Muted.TLabel", wraplength=460).pack(anchor="w", pady=(6, 0))

        # 2. MEDIA KEY PANEL
        self.p_media = ttk.Frame(self.panel_host)
        ttk.Label(self.p_media, text="Select media, system, or special key control:").pack(anchor="w", pady=(0, 8))
        self.media_var = tk.StringVar(value="volup")
        self.special_keystroke_media = ["execute", "help", "menu2", "select", "again", "undo",
                                        "cut", "copy", "paste", "find", "kbmute", "volup_kb", "voldown_kb", "stop_kb"]

        # Grid of popular media/system/special keys for 1-click selection
        mgrid = ttk.Frame(self.p_media)
        mgrid.pack(anchor="w", pady=(0, 8))
        m_common = [("Mute Audio", "mute"), ("Volume Up", "volup"), ("Volume Down", "voldown"),
                    ("Play / Pause", "play"), ("Next Track", "next"), ("Previous Track", "prev"),
                    ("Stop", "stop"), ("Brightness +", "brightup"), ("Brightness -", "brightdown"),
                    ("Multimedia", "multimedia"), ("Mail", "mail"), ("Calculator", "calculator"),
                    ("My PC", "mypc"), ("Web Search", "web-search"), ("Web Home", "web-home"),
                    ("Web Back", "web-backward"), ("Web Forward", "web-forward"), ("Web Stop", "web-stop"),
                    ("Web Refresh", "web-refresh"), ("Web Favorites", "web-favorites"),
                    ("Power", "power"), ("Sleep", "sleep"), ("Wakeup", "wakeup"),
                    ("Cut", "cut"), ("Copy", "copy"), ("Paste", "paste"), ("Find", "find"),
                    ("Undo", "undo"), ("Again", "again"), ("Select", "select"), ("Execute", "execute"),
                    ("Help", "help"), ("Menu 2", "menu2"), ("Stop (key)", "stop_kb"), ("KB Mute", "kbmute"),
                    ("KB Vol +", "volup_kb"), ("KB Vol -", "voldown_kb")]
        for m_idx, (m_lbl, m_val) in enumerate(m_common):
            b = ttk.Button(mgrid, text=m_lbl, padding=(10, 6), command=lambda v=m_val: self.media_var.set(v))
            b.grid(row=m_idx // 3, column=m_idx % 3, padx=4, pady=4, sticky="ew")

        r_m = ttk.Frame(self.p_media)
        r_m.pack(anchor="w", pady=6)
        ttk.Label(r_m, text="Active Selection:").pack(side="left")
        # "stop" appears in both CONSUMER (media) and as keyboard usage (0x78); include once - resolves to consumer by default in this UI
        media_values = sorted(CONSUMER.keys()) + ["power", "sleep", "wakeup"] + self.special_keystroke_media + ["stop"]
        ttk.Combobox(r_m, state="readonly", values=sorted(set(media_values)), textvariable=self.media_var, width=16).pack(side="left", padx=6)

        # 3. MOUSE PANEL
        self.p_mouse = ttk.Frame(self.panel_host)
        ttk.Label(self.p_mouse, text="Select mouse button, scroll, or cursor move action:").pack(anchor="w", pady=(0, 8))
        self.mouse_var = tk.StringVar(value="left")
        ms_frame = ttk.Frame(self.p_mouse)
        ms_frame.pack(anchor="w")
        for m_name, m_val in (("Left Click", "left"), ("Right Click", "right"), ("Middle Click", "middle"),
                              ("Scroll Up ⇡", "wheelup"), ("Scroll Down ⇣", "wheeldown"),
                              ("Back", "back"), ("Forward", "forward"),
                              ("Mouse Move", "mousemove")):
            ttk.Radiobutton(ms_frame, text=m_name, value=m_val, variable=self.mouse_var, command=self._show_mouse_cursor).pack(anchor="w", pady=2)

        self.cursor_box = ttk.LabelFrame(self.p_mouse, text="Mouse move (steps, 0-255)", padding=8)
        self.cur_up = tk.IntVar(value=0)
        self.cur_down = tk.IntVar(value=0)
        self.cur_left = tk.IntVar(value=0)
        self.cur_right = tk.IntVar(value=0)
        self._cur_guard = False

        def _cur_exclusive(changed):
            if self._cur_guard:
                return
            self._cur_guard = True
            try:
                if changed == "up" and self.cur_up.get() > 0:
                    self.cur_down.set(0)
                elif changed == "down" and self.cur_down.get() > 0:
                    self.cur_up.set(0)
                elif changed == "left" and self.cur_left.get() > 0:
                    self.cur_right.set(0)
                elif changed == "right" and self.cur_right.get() > 0:
                    self.cur_left.set(0)
            finally:
                self._cur_guard = False

        self.cur_up.trace_add("write", lambda *_: _cur_exclusive("up"))
        self.cur_down.trace_add("write", lambda *_: _cur_exclusive("down"))
        self.cur_left.trace_add("write", lambda *_: _cur_exclusive("left"))
        self.cur_right.trace_add("write", lambda *_: _cur_exclusive("right"))

        grid = ttk.Frame(self.cursor_box)
        grid.pack(anchor="w")
        for r, (lbl, var) in enumerate((("Up", self.cur_up), ("Down", self.cur_down), ("Left", self.cur_left), ("Right", self.cur_right))):
            ttk.Label(grid, text=lbl, width=6).grid(row=r, column=0, sticky="w", pady=2)
            ttk.Spinbox(grid, from_=0, to=255, width=6, textvariable=var).grid(row=r, column=1, sticky="w", pady=2)
        ttk.Label(self.cursor_box, text="Uses device mouse-move encoding (type 0x11). Set up/down and/or left/right amounts (positive values).",
                  style="Muted.TLabel", wraplength=420).pack(anchor="w", pady=(6, 0))
        self._show_mouse_cursor()

        # 4. KEYPAD PANEL
        self.p_keypad = ttk.Frame(self.panel_host)
        ttk.Label(self.p_keypad, text="Select keypad / numpad key:").pack(anchor="w", pady=(0, 8))
        self.keypad_var = tk.StringVar(value="kpenter")
        keypad_keys = [k for k in KEYS if k.startswith("kp") or k == "numlock"]
        # keep a stable useful order subset at top, rest sorted
        preferred = ["numlock","kp/","kp*","kp-","kp+","kpenter","kp1","kp2","kp3","kp4","kp5","kp6","kp7","kp8","kp9","kp0","kp.","kp=","kp,","kp00","kp000"]
        rest = [k for k in sorted(keypad_keys) if k not in preferred]
        keypad_values = [k for k in preferred if k in keypad_keys] + rest
        self.keypad_values = keypad_values
        kpgrid = ttk.Frame(self.p_keypad)
        kpgrid.pack(anchor="w", pady=(0, 8))
        # show common ones as buttons
        common_kp = [("NumLock","numlock"),("KP /","kp/"),("KP *","kp*"),("KP -","kp-"),("KP +","kp+"),("KP Enter","kpenter"),
                     ("KP 7","kp7"),("KP 8","kp8"),("KP 9","kp9"),("KP 4","kp4"),("KP 5","kp5"),("KP 6","kp6"),
                     ("KP 1","kp1"),("KP 2","kp2"),("KP 3","kp3"),("KP 0","kp0"),("KP .","kp."),("KP =","kp=")]
        for i,(lbl,val) in enumerate(common_kp):
            ttk.Button(kpgrid, text=lbl, padding=(6,4), command=lambda v=val: self.keypad_var.set(v)).grid(row=i//6, column=i%6, padx=2, pady=2, sticky="ew")
        rkp = ttk.Frame(self.p_keypad)
        rkp.pack(anchor="w", pady=4)
        ttk.Label(rkp, text="All keypad keys:").pack(side="left")
        ttk.Combobox(rkp, state="readonly", values=keypad_values, textvariable=self.keypad_var, width=20).pack(side="left", padx=6)

        # 5. KEYBOARD CONTROL PANEL
        self.p_kbctl = ttk.Frame(self.panel_host)
        ttk.Label(self.p_kbctl, text="Keyboard/device control actions:").pack(anchor="w", pady=(0, 8))
        self.kbctl_var = tk.StringVar(value="profile_switch")
        kb_opts = [("Profile Switch", "profile_switch"), ("Keyboard Lock", "keyboard_lock"),
                   ("Light Switch", "light_switch"), ("Light Effect", "light_effect"),
                   ("Light Direction", "light_direction"), ("Color Switch", "color_switch"),
                   ("Light Speed +", "light_speed_up"), ("Light Speed -", "light_speed_down"),
                   ("KB Brightness +", "kb_brightness_up"), ("KB Brightness -", "kb_brightness_down")]
        kbgrid = ttk.Frame(self.p_kbctl)
        kbgrid.pack(anchor="w")
        for i, (lbl, val) in enumerate(kb_opts):
            ttk.Radiobutton(kbgrid, text=lbl, value=val, variable=self.kbctl_var).grid(row=i // 2, column=i % 2, sticky="w", padx=4, pady=2)
        ttk.Label(self.p_kbctl, text="Note: KB Brightness +/- (1F 03 00 00 / 1F 02 00 00) usually do not work, due to firmware error or lack of hardware.",
                  style="Muted.TLabel", wraplength=460).pack(anchor="w", pady=(8, 0))

        # 6. MACRO PANEL
        self.p_macro = ttk.Frame(self.panel_host)
        ttk.Label(self.p_macro, text="Choose which recorded macro this key will play:", font=FONT_B).pack(anchor="w")
        
        mr = ttk.Frame(self.p_macro)
        mr.pack(anchor="w", pady=8)
        ttk.Label(mr, text="Macro:").pack(side="left")
        self.macro_idx = tk.IntVar(value=1)
        self.macro_cb = ttk.Combobox(mr, state="readonly", width=28)
        self.macro_cb.pack(side="left", padx=6)
        self.macro_cb.bind("<<ComboboxSelected>>", self._on_macro_cb_sel)
        
        ttk.Button(mr, text="Go to Macro Editor", padding=(8, 4), command=lambda: self.notebook.select(1)).pack(side="left", padx=6)

        rep_box = ttk.LabelFrame(self.p_macro, text="Playback behavior", padding=10)
        rep_box.pack(fill="x", pady=6)
        self.macro_mode_str = tk.StringVar(value="once")
        self.macro_rep = tk.IntVar(value=1)
        
        for text_lbl, m_mode in (("Play once", "once"), ("Repeat while button is held", "hold"),
                                 ("Toggle loop (press once to start, again to stop)", "toggle"),
                                 ("Play fixed number of times", "times")):
            ttk.Radiobutton(rep_box, text=text_lbl, value=m_mode, variable=self.macro_mode_str).pack(anchor="w", pady=2)
        
        rep_cnt_row = ttk.Frame(rep_box)
        rep_cnt_row.pack(anchor="w", padx=20, pady=2)
        ttk.Label(rep_cnt_row, text="Count (if fixed):").pack(side="left")
        ttk.Spinbox(rep_cnt_row, from_=1, to=255, width=5, textvariable=self.macro_rep).pack(side="left", padx=4)

        # 7. RAW BYTES PANEL
        self.p_raw = ttk.Frame(self.panel_host)
        self.raw_var = tk.StringVar(value="13 00 00 00")
        ttk.Label(self.p_raw, text="Raw hex bytes [type c1 c2 c3]:").pack(side="left")
        ttk.Entry(self.p_raw, textvariable=self.raw_var, width=16).pack(side="left", padx=4)

        # 8. DISABLED PANEL
        self.p_none = ttk.Frame(self.panel_host)
        ttk.Label(self.p_none, text="This key will be completely disabled (sends nothing).", style="Muted.TLabel").pack(anchor="w")

        # Bottom Action Bar
        act_bar = ttk.Frame(ed)
        act_bar.pack(fill="x", pady=(14, 0))

        ttk.Button(act_bar, text="Clear / Disable Key", command=lambda: self.apply_preset("none")).pack(side="left")
        ttk.Button(act_bar, text="APPLY TO PAD", style="Accent.TButton", command=self.apply_key).pack(side="right")
        self.show_type_panel()

    def show_type_panel(self):
        for p in (self.p_key, self.p_media, self.p_keypad, self.p_mouse, self.p_macro, self.p_kbctl, self.p_raw, self.p_none):
            p.pack_forget()
        t = self.type_var.get()
        {"Keystroke": self.p_key, "Media key": self.p_media, "Keypad": self.p_keypad, "Mouse": self.p_mouse,
         "Run macro": self.p_macro, "Keyboard control": self.p_kbctl,
         "Raw bytes": self.p_raw, "Disabled": self.p_none}[t].pack(anchor="w")

    def on_capture(self, e):
        ks = e.keysym
        if ks in ("Shift_L", "Shift_R", "Control_L", "Control_R", "Alt_L", "Alt_R",
                  "Super_L", "Super_R", "Meta_L", "Meta_R", "ISO_Level3_Shift"):
            return "break"
        name = KEYSYM.get(ks)
        if name is None:
            name = ks.lower()
        if name not in KEYS:
            self.capture.delete(0, "end")
            self.capture.insert(0, f"unsupported key: {ks}")
            return "break"
        self.mod_vars["ctrl"].set(bool(e.state & 0x4))
        self.mod_vars["shift"].set(bool(e.state & 0x1))
        self.mod_vars["alt"].set(bool(e.state & 0x8))
        self.mod_vars["gui"].set(bool(e.state & 0x40))
        self.key_var.set(name)
        self.capture.delete(0, "end")
        self.capture.insert(0, "captured: " + self.current_combo_text())
        return "break"

    def current_combo_text(self):
        parts = [n for n, v in self.mod_vars.items() if v.get()]
        if self.key_var.get():
            parts.append(self.key_var.get())
        return "+".join(parts)

    def _show_mouse_cursor(self):
        if not hasattr(self, "cursor_box"):
            return
        if getattr(self, "mouse_var", None) and self.mouse_var.get() == "mousemove":
            self.cursor_box.pack(anchor="w", fill="x", pady=(8, 0))
        else:
            self.cursor_box.pack_forget()

    def apply_shortcut_combo(self, combo):
        # Fill keystroke UI from a combo string like ctrl+c or f13
        for v in self.mod_vars.values():
            v.set(False)
        self.key_var.set("")
        for part in combo.lower().split("+"):
            if part in self.mod_vars:
                self.mod_vars[part].set(True)
            elif part in KEYS:
                self.key_var.set(part)
        self.type_var.set("Keystroke")
        self.capture.delete(0, "end")
        self.capture.insert(0, "shortcut: " + self.current_combo_text())
        self.show_type_panel()

    def refresh_keys(self):
        # Update canvas visualization
        if hasattr(self, "pad_canvas"):
            cols = {}
            if hasattr(self, "colour_vals") and self.colour_vals:
                for i in range(min(len(self.colour_vals), self.key_count)):
                    cols[i] = "#%02x%02x%02x" % self.colour_vals[i]
            mode = getattr(self, "mode_var", None)
            rgb_mode = mode.get() if mode else "palette"
            self.pad_canvas.set_data(self.table, self.selected, key_colors=cols, rgb_mode=rgb_mode)
        # Update macro combobox choices if on Macro panel
        if hasattr(self, "macro_cb"):
            m_choices = []
            for s in range(16):
                name = self.macro_names.get(s, "").strip() if hasattr(self, "macro_names") else ""
                m_choices.append(f"Macro {s + 1}" + (f": {name}" if name else ""))
            self.macro_cb.config(values=m_choices)
            if 1 <= self.macro_idx.get() <= 16:
                self.macro_cb.current(self.macro_idx.get() - 1)

    def _on_macro_cb_sel(self, e):
        idx = self.macro_cb.current()
        if idx >= 0:
            self.macro_idx.set(idx + 1)

    def apply_preset(self, act_str):
        if self.selected is None:
            messagebox.showinfo("Select", "Click a key on the visual pad first.")
            return
        entry = parse_action(act_str)
        self.pad.write_key(self.selected, entry)
        self.table = self.pad.read_table()
        self.select_key(self.selected)
        self.status.set(f"Saved {key_slot_label(self.selected, self.layout)} -> {gui_describe(self.table[self.selected])}")

    def select_key(self, i):
        self.selected = i
        e = self.table[i] if i < len(self.table) else (0x13, 0, 0, 0)
        self.ed_title.set(f"CONFIGURING {key_slot_label(i, getattr(self, 'layout', None)).upper()}")
        self.ed_subtitle.set(f"Assigned action: {gui_describe(e)}  (Hardware memory slot {i})")
        t, a, b, c = e
        key_name = KEYS_REV.get(b, "")
        keypad_set = set(getattr(self, "keypad_values", [])) - {"numlock"}
        special_media = set(getattr(self, "special_keystroke_media", [])) | {"stop"}
        if t == 0x20 and a == 0 and key_name in keypad_set:
            self.type_var.set("Keypad")
            self.keypad_var.set(key_name)
        elif t == 0x20 and a == 0 and key_name in special_media and key_name != "stop":
            self.type_var.set("Media key")
            self.media_var.set(key_name)
        elif t == 0x20:
            self.type_var.set("Keystroke")
            for n, bit in (("ctrl", 1), ("shift", 2), ("alt", 4), ("gui", 8)):
                self.mod_vars[n].set(bool(a & bit))
            self.key_var.set(key_name)
        elif t == 0x30:
            self.type_var.set("Media key")
            self.media_var.set(CONS_REV.get(a | b << 8, "volup"))
        elif t == 0x40 and a in (0x01, 0x02, 0x04):
            self.type_var.set("Media key")
            self.media_var.set({0x01: "power", 0x02: "sleep", 0x04: "wakeup"}[a])
        elif t == 0x1F and a in (0x00, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x13, 0x14, 0x19):
            self.type_var.set("Keyboard control")
            rev = {0x00: "light_switch", 0x01: "light_effect", 0x02: "kb_brightness_down", 0x03: "kb_brightness_up",
                   0x04: "color_switch", 0x05: "light_speed_up", 0x06: "light_speed_down",
                   0x13: "profile_switch", 0x14: "light_direction", 0x19: "keyboard_lock"}
            self.kbctl_var.set(rev.get(a, "profile_switch"))
        elif t == 0x10 and a in (1, 2, 4, 8, 16) and c == 0:
            self.type_var.set("Mouse")
            self.mouse_var.set({1: "left", 2: "right", 4: "middle", 8: "back", 16: "forward"}.get(a, "left"))
        elif t == 0x10 and c in (1, 0xFF):
            self.type_var.set("Mouse")
            self.mouse_var.set("wheelup" if c == 1 else "wheeldown")
        elif t == 0x11:
            self.type_var.set("Mouse")
            self.mouse_var.set("mousemove")
            # populate mouse move fields (mutually exclusive directions)
            self._cur_guard = True
            try:
                self.cur_up.set(c if (a & 0x08) else 0)
                self.cur_down.set(0 if (a & 0x08) else c)
                self.cur_left.set(b if (a & 0x80) else 0)
                self.cur_right.set(0 if (a & 0x80) else b)
            finally:
                self._cur_guard = False
            self._show_mouse_cursor()
        elif t == 0x60:
            self.type_var.set("Run macro")
            self.macro_idx.set(a + 1)
            self.macro_rep.set(max(1, b))
            if hasattr(self, "macro_mode_str"):
                if c == 1:
                    self.macro_mode_str.set("hold")
                elif c == 3:
                    self.macro_mode_str.set("toggle")
                elif b > 1:
                    self.macro_mode_str.set("times")
                else:
                    self.macro_mode_str.set("once")
        # 0x1F/0x40 handled above as Keyboard control / Media key; other unknowns fall through to Raw bytes below
        elif t == 0x13:
            self.type_var.set("Disabled")
        else:
            self.type_var.set("Raw bytes")
            self.raw_var.set(bytes(e).hex(" "))
        self.show_type_panel()
        self.refresh_keys()

    def current_entry(self):
        t = self.type_var.get()
        if t == "Keystroke":
            mods = sum(bit for n, bit in (("ctrl", 1), ("shift", 2), ("alt", 4), ("gui", 8)) if self.mod_vars[n].get())
            k = self.key_var.get()
            if not k and not mods:
                raise ValueError("Choose a key or modifier")
            return (0x20, mods, KEYS[k] if k else 0, 0)
        if t == "Media key":
            v = self.media_var.get()
            if v in ("power", "sleep", "wakeup"):
                return parse_action(v)
            # special HID keystroke usages shown in media group
            special = set(getattr(self, "special_keystroke_media", []))
            if v in special and v in KEYS:
                return (0x20, 0, KEYS[v], 0)
            # "stop" is ambiguous (consumer 0xB7 in CONSUMER vs keyboard 0x78 in KEYS); in Media panel treat as consumer
            return parse_action("media:" + v)
        if t == "Keypad":
            k = self.keypad_var.get()
            if k not in KEYS:
                raise ValueError("Choose a keypad key")
            return (0x20, 0, KEYS[k], 0)
        if t == "Keyboard control":
            return parse_action(self.kbctl_var.get())
        if t == "Mouse":
            if self.mouse_var.get() == "mousemove":
                up = max(0, min(255, int(self.cur_up.get() or 0)))
                down = max(0, min(255, int(self.cur_down.get() or 0)))
                left = max(0, min(255, int(self.cur_left.get() or 0)))
                right = max(0, min(255, int(self.cur_right.get() or 0)))
                a = b = c = 0
                if up:
                    a |= 0x08; c = up
                elif down:
                    c = down
                if left:
                    a |= 0x80; b = left
                elif right:
                    b = right
                return (0x11, a, b, c)
            return parse_action("mouse:" + self.mouse_var.get())
        if t == "Run macro":
            mode_map = {"once": 0, "hold": 1, "times": 0, "toggle": 3}
            m_mode = mode_map.get(getattr(self, "macro_mode_str", tk.StringVar(value="once")).get(), 0)
            rep = self.macro_rep.get() if self.macro_mode_str.get() == "times" else 1
            return (0x60, self.macro_idx.get() - 1, max(1, rep), m_mode)
        if t == "Disabled":
            return (0x13, 0, 0, 0)
        b = bytes.fromhex(self.raw_var.get())
        if len(b) != 4:
            raise ValueError("Need exactly 4 bytes")
        return tuple(b)

    def apply_key(self):
        if self.selected is None:
            messagebox.showinfo("Apply", "Select a key first")
            return

        def go():
            entry = self.current_entry()
            self.pad.write_key(self.selected, entry)
            self.table = self.pad.read_table()      # read back to verify
            self.select_key(self.selected)
            self.status.set(f"Saved {key_slot_label(self.selected, self.layout)} -> {gui_describe(self.table[self.selected])}")
        self.guard(go)

    # ================================================================== MACROS TAB
    def build_macro_tab(self):
        MUI.set_theme(BG=BG, PANEL=PANEL, PANEL2=PANEL2, BORDER=BORDER, FG=FG, MUTED=MUTED, ACCENT=ACCENT)
        self.macro_events = {}      # slot -> raw events as stored on the pad
        self.macro_steps = {}       # slot -> editable steps (decoded lazily)
        self.macro_dirty = set()
        self.macro_slot = None
        try:
            with open(NAMES_FILE) as fh:
                self.macro_names = {int(k): v for k, v in json.load(fh).items()}
        except (OSError, ValueError):
            self.macro_names = {}

        f = ttk.Frame(self.macro_tab, padding=(14, 12))
        f.pack(fill="both", expand=True)
        left = ttk.Frame(f)
        left.pack(side="left", fill="y")
        ttk.Label(left, text="YOUR MACROS", style="Muted.TLabel").pack(anchor="w", pady=(0, 6))
        self.macro_list = tk.Listbox(left, width=22, height=17, exportselection=False, bg=PANEL2, fg=FG,
                                     selectbackground=ACCENT, selectforeground="#000000", relief="flat", bd=0,
                                     highlightthickness=1, highlightbackground=BORDER, highlightcolor=ACCENT,
                                     activestyle="none", font=FONT)
        self.macro_list.pack(fill="y", expand=True)
        self.macro_list.bind("<<ListboxSelect>>", lambda e: self.show_macro())

        right = ttk.Frame(f)
        right.pack(side="left", fill="both", expand=True, padx=(16, 0))

        head = ttk.Frame(right)
        head.pack(fill="x")
        ttk.Label(head, text="Name").pack(side="left")
        self.macro_name = tk.StringVar()
        ent = ttk.Entry(head, textvariable=self.macro_name, width=26)
        ent.pack(side="left", padx=8)
        ent.bind("<KeyRelease>", lambda e: self.rename_macro())
        self.mem_label = ttk.Label(head, text="", style="Muted.TLabel")
        self.mem_label.pack(side="right")

        ttk.Label(right, text="WHAT THIS MACRO DOES  (runs top to bottom)", style="Muted.TLabel").pack(anchor="w", pady=(12, 4))
        tree_frame = ttk.Frame(right)
        tree_frame.pack(fill="both", expand=True)
        self.steps_tree = ttk.Treeview(tree_frame, columns=("n", "what"), show="headings", height=7, selectmode="browse")
        self.steps_tree.heading("n", text="#")
        self.steps_tree.heading("what", text="Action")
        self.steps_tree.column("n", width=40, anchor="center", stretch=False)
        self.steps_tree.column("what", anchor="w")
        sb = ttk.Scrollbar(tree_frame, orient="vertical", command=self.steps_tree.yview)
        self.steps_tree.configure(yscrollcommand=sb.set)
        self.steps_tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="left", fill="y")
        self.steps_tree.bind("<Double-1>", lambda e: self.edit_step())
        self.steps_tree.bind("<Delete>", lambda e: self.delete_step())
        self.empty_hint = ttk.Label(right, text="This macro is empty. Add a step below, or press Record and just type.",
                                    style="Muted.TLabel")

        ttk.Label(right, text="ADD A STEP", style="Muted.TLabel").pack(anchor="w", pady=(10, 4))
        add = ttk.Frame(right)
        add.pack(fill="x")
        for label, kind in (("Type text", "text"), ("Press keys", "press"), ("Wait", "wait"),
                            ("Mouse click", "mouse"), ("Hold / release", "hold")):
            ttk.Button(add, text=label, padding=(8, 6), command=lambda k=kind: self.add_step(k)).pack(side="left", padx=(0, 4))
        ttk.Button(add, text="●  Record", padding=(8, 6), command=self.record_steps).pack(side="left", padx=(6, 0))

        edit = ttk.Frame(right)
        edit.pack(fill="x", pady=(8, 0))
        for label, cmd in (("Edit", self.edit_step), ("Move up", lambda: self.move_step(-1)),
                           ("Move down", lambda: self.move_step(1)), ("Delete", self.delete_step),
                           ("Clear all", self.clear_steps)):
            ttk.Button(edit, text=label, padding=(10, 5), command=cmd).pack(side="left", padx=(0, 5))

        ttk.Separator(right).pack(fill="x", pady=12)
        trig = ttk.Frame(right)
        trig.pack(fill="x")
        ttk.Label(trig, text="RUN FROM", style="Muted.TLabel").pack(side="left", padx=(0, 6))
        slots = list(range(self.key_count)) + list(range(16, 16 + self.dial_count * 3))
        self.trig_slots = {key_slot_label(i, self.layout): i for i in slots}
        self.trig_ctl = tk.StringVar(value=key_slot_label(0, self.layout))
        self.trig_ctl_box = ttk.Combobox(trig, state="readonly", values=list(self.trig_slots), textvariable=self.trig_ctl, width=18)
        self.trig_ctl_box.pack(side="left")
        ttk.Label(trig, text="  PLAYS", style="Muted.TLabel").pack(side="left", padx=(8, 6))
        self.PLAY_MODES = {"once": (0, 1), "a number of times": (0, 2), "repeating while held": (1, 1),
                           "repeating until pressed again": (3, 1), "repeating until any key": (2, 1)}
        self.play_mode = tk.StringVar(value="once")
        ttk.Combobox(trig, state="readonly", values=list(self.PLAY_MODES), textvariable=self.play_mode, width=26).pack(side="left")
        self.play_count = tk.IntVar(value=2)
        self.count_spin = ttk.Spinbox(trig, from_=2, to=255, width=4, textvariable=self.play_count)
        self.count_spin.pack(side="left", padx=6)
        ttk.Button(trig, text="Assign", command=self.assign_macro).pack(side="left", padx=(6, 0))

        bottom = ttk.Frame(right)
        bottom.pack(fill="x", pady=(12, 0))
        self.dirty_label = ttk.Label(bottom, text="", foreground="#ffb020")
        self.dirty_label.pack(side="left")
        ttk.Button(bottom, text="SAVE TO PAD", style="Accent.TButton", command=self.save_macros).pack(side="right")
        ttk.Button(bottom, text="Discard changes", command=self.load_macros).pack(side="right", padx=8)

    # -- loading / list
    def load_macros(self):
        self.macro_table = self.pad.read_macro_table()
        self.macro_events = M.read_macro_events(self.macro_table)
        self.macro_steps = {}
        self.macro_dirty = set()
        self.refresh_macro_list()
        if self.macro_slot is None:
            self.macro_slot = 0
        self.macro_list.selection_clear(0, "end")
        self.macro_list.selection_set(self.macro_slot)
        self.show_macro()

    def steps_for(self, slot):
        if slot not in self.macro_steps:
            ev = self.macro_events.get(slot)
            self.macro_steps[slot] = M.decompile(ev) if ev else []
        return self.macro_steps[slot]

    def macro_title(self, slot):
        name = self.macro_names.get(slot, "").strip()
        n = len(self.steps_for(slot))
        mark = "● " if slot in self.macro_dirty else ""
        body = name or ("(empty)" if n == 0 else f"{n} step{'s' if n != 1 else ''}")
        return f"{mark}{slot + 1:>2}   {body}"

    def refresh_macro_list(self):
        sel = self.macro_list.curselection()
        self.macro_list.delete(0, "end")
        for s in range(16):
            self.macro_list.insert("end", self.macro_title(s))
        if sel:
            self.macro_list.selection_set(sel[0])
        self.update_macro_status()

    def update_macro_status(self):
        used = 64
        try:
            for s in range(16):
                st = self.steps_for(s)
                if st:
                    used += 4 * len(M.compile_steps(st)) if s in self.macro_dirty or s not in self.macro_events \
                        else 4 * len(self.macro_events[s])
            self.mem_label.config(text=f"Memory used: {used} of 4096 bytes",
                                  foreground=DANGER if used > 4096 else MUTED)
        except ValueError:
            self.mem_label.config(text="")
        self.dirty_label.config(text="●  Unsaved changes" if self.macro_dirty else "")

    def show_macro(self):
        sel = self.macro_list.curselection()
        if sel:
            self.macro_slot = sel[0]
        self.macro_name.set(self.macro_names.get(self.macro_slot, ""))
        self.refresh_steps()

    def refresh_steps(self, select=None):
        t = self.steps_tree
        t.delete(*t.get_children())
        steps = self.steps_for(self.macro_slot)
        for i, st in enumerate(steps):
            t.insert("", "end", iid=str(i), values=(i + 1, M.describe_step(st)))
        if select is not None and steps:
            select = max(0, min(select, len(steps) - 1))
            t.selection_set(str(select))
            t.see(str(select))
        if steps:
            self.empty_hint.pack_forget()
        else:
            self.empty_hint.pack(anchor="w", pady=4)
        self.refresh_macro_list()

    def rename_macro(self):
        self.macro_names[self.macro_slot] = self.macro_name.get()
        try:
            with open(NAMES_FILE, "w") as fh:
                json.dump({str(k): v for k, v in self.macro_names.items() if v}, fh)
        except OSError:
            pass
        sel = self.macro_slot
        self.macro_list.delete(sel)
        self.macro_list.insert(sel, self.macro_title(sel))
        self.macro_list.selection_set(sel)

    # -- editing steps
    def cur_step_index(self):
        sel = self.steps_tree.selection()
        return int(sel[0]) if sel else None

    def touch(self):
        self.macro_dirty.add(self.macro_slot)

    def add_step(self, kind):
        d = MUI.StepDialog(self, kind)
        if not d.result:
            return
        steps = self.steps_for(self.macro_slot)
        i = self.cur_step_index()
        pos = len(steps) if i is None else i + 1
        steps.insert(pos, d.result)
        self.touch()
        self.refresh_steps(select=pos)

    def record_steps(self):
        d = MUI.RecordDialog(self)
        if not d.result:
            return
        steps = self.steps_for(self.macro_slot)
        i = self.cur_step_index()
        pos = len(steps) if i is None else i + 1
        steps[pos:pos] = d.result
        self.touch()
        self.refresh_steps(select=pos + len(d.result) - 1)

    def edit_step(self):
        i = self.cur_step_index()
        if i is None:
            return
        steps = self.steps_for(self.macro_slot)
        st = steps[i]
        kind = {"text": "text", "press": "press", "wait": "wait", "mouse": "mouse", "down": "hold", "up": "hold"}.get(st["t"])
        if kind is None:
            messagebox.showinfo("Edit", "This step can't be edited here. You can move or delete it.")
            return
        if st["t"] == "keys":
            return
        d = MUI.StepDialog(self, kind, st)
        if d.result:
            steps[i] = d.result
            self.touch()
            self.refresh_steps(select=i)

    def move_step(self, delta):
        i = self.cur_step_index()
        steps = self.steps_for(self.macro_slot)
        if i is None or not 0 <= i + delta < len(steps):
            return
        steps[i], steps[i + delta] = steps[i + delta], steps[i]
        self.touch()
        self.refresh_steps(select=i + delta)

    def delete_step(self):
        i = self.cur_step_index()
        if i is None:
            return
        del self.steps_for(self.macro_slot)[i]
        self.touch()
        self.refresh_steps(select=i)

    def clear_steps(self):
        steps = self.steps_for(self.macro_slot)
        if steps and messagebox.askyesno("Clear macro", f"Remove all {len(steps)} steps from macro {self.macro_slot + 1}?"):
            steps.clear()
            self.touch()
            self.refresh_steps()

    # -- save / assign
    def backup_macros(self):
        os.makedirs(BACKUP_DIR, exist_ok=True)
        p = os.path.join(BACKUP_DIR, "macros-" + datetime.datetime.now().strftime("%Y%m%d-%H%M%S") + ".bin")
        with open(p, "wb") as fh:
            fh.write(self.macro_table)
        return p

    def save_macros(self):
        if not self.macro_dirty:
            self.status.set("No macro changes to save")
            return

        def go():
            events = dict(self.macro_events)
            for slot in self.macro_dirty:
                steps = self.steps_for(slot)
                if steps:
                    try:
                        events[slot] = M.compile_steps(steps)
                    except ValueError as e:
                        raise ValueError(f"Macro {slot + 1}: {e}")
                else:
                    events.pop(slot, None)
            table = M.build_table(events)
            bk = self.backup_macros()
            self.pad.write_macro_table(table)
            self.load_macros()
            self.status.set(f"Macros saved to pad (backup: {os.path.basename(bk)})")
        self.guard(go)

    def assign_macro(self):
        slot = self.trig_slots[self.trig_ctl.get()]
        mode, count = self.PLAY_MODES[self.play_mode.get()]
        if self.play_mode.get() == "a number of times":
            count = max(2, self.play_count.get())

        def go():
            if self.macro_dirty:
                if not messagebox.askyesno("Unsaved changes", "You have unsaved macro changes. Assign anyway?\n"
                                           "(Save to pad afterwards so the key plays the new version.)"):
                    return
            self.pad.write_key(slot, (0x60, self.macro_slot, count, mode))
            self.table = self.pad.read_table()
            self.refresh_keys()
            self.status.set(f"{key_slot_label(slot, self.layout)} now runs macro {self.macro_slot + 1}")
        self.guard(go)

    # ================================================================== LIGHTING TAB
    def build_light_tab(self):
        f = ttk.Frame(self.light_tab, padding=14)
        f.pack(fill="both", expand=True)
        self.mode_var = tk.StringVar()
        self.bright_var = tk.IntVar()
        self.speed_var = tk.IntVar()
        self.dir_var = tk.IntVar()
        self.use_colour = tk.BooleanVar()
        self.light_hex = "#ff0000"
        r = ttk.Frame(f); r.pack(anchor="w", pady=4)
        ttk.Label(r, text="Effect:", width=12).pack(side="left")
        ttk.Combobox(r, state="readonly", values=LIGHT_MODES, textvariable=self.mode_var, width=14).pack(side="left")
        for label, var, hi in (("Brightness:", self.bright_var, 4), ("Speed:", self.speed_var, 4)):
            r = ttk.Frame(f); r.pack(anchor="w", pady=4)
            ttk.Label(r, text=label, width=12).pack(side="left")
            ttk.Scale(r, from_=0, to=hi, variable=var, length=200,
                      command=lambda v, var=var: var.set(round(float(v)))).pack(side="left")
            ttk.Label(r, textvariable=var, width=3).pack(side="left")
        r = ttk.Frame(f); r.pack(anchor="w", pady=4)
        ttk.Checkbutton(r, text="Use custom colour (otherwise palette cycles)", variable=self.use_colour).pack(side="left")
        self.colour_btn = tk.Button(r, text="  pick colour  ", command=self.pick_light_colour, relief="flat", bd=0,
                                    highlightthickness=1, highlightbackground=BORDER, fg="#000000", cursor="hand2")
        self.colour_btn.pack(side="left", padx=8)
        ttk.Button(f, text="APPLY LIGHTING", style="Accent.TButton", command=self.apply_light).pack(anchor="w", pady=8)
        ttk.Label(f, text="Note: effects run in firmware and brightness may only be visible via the colour's value.",
                  style="Muted.TLabel").pack(anchor="w")

        ttk.Separator(f).pack(fill="x", pady=12)
        ttk.Label(f, text="Per-key colours (shown when effect = perkey)").pack(anchor="w")
        self.pk_grid_frame = ttk.Frame(f)
        self.pk_grid_frame.pack(anchor="w", pady=6)
        self.colour_vals = [(0, 255, 0)] * self.key_count
        self.pk_btns = []
        self.rebuild_perkey_grid()
        ttk.Button(f, text="Switch to per-key mode", command=self.set_perkey).pack(anchor="w")

    def rebuild_perkey_grid(self):
        if not hasattr(self, "pk_grid_frame"):
            return
        for child in self.pk_grid_frame.winfo_children():
            child.destroy()
        self.pk_btns = []
        # preserve existing colours where possible
        old = list(getattr(self, "colour_vals", []))
        self.colour_vals = [old[i] if i < len(old) else (0, 255, 0) for i in range(self.key_count)]
        for i in range(self.key_count):
            pos = _slot_to_visual(i, self.layout)
            if pos is None:
                pos = (i // self.cols, i % self.cols)
            vrow, vcol = pos
            if self.layout.get("name") == "SIDE-KEYBOARD" and self.cols == 3 and self.rows == 4:
                label = f"K{i+1}\nslot {i}"
            else:
                label = f"K{i+1}\nslot {i}"
            b = tk.Button(self.pk_grid_frame, text=label, width=9, height=2,
                          command=lambda i=i: self.pick_key_colour(i),
                          relief="flat", bd=0, highlightthickness=1, highlightbackground=BORDER,
                          fg="#000000", cursor="hand2")
            b.grid(row=vrow, column=vcol, padx=3, pady=3)
            hx = "#%02x%02x%02x" % self.colour_vals[i]
            b.config(bg=hx, activebackground=hx)
            self.pk_btns.append(b)

    def load_light(self):
        cur = self.pad.read_light()
        self.mode_var.set(LIGHT_MODES[cur[2]] if cur[2] < 6 else "tide")
        self.bright_var.set(cur[3]); self.speed_var.set(cur[4]); self.dir_var.set(cur[5])
        self.use_colour.set(bool(cur[6]))
        self.light_hex = hsv255_to_hex(cur[8], cur[9], cur[10])
        self.colour_btn.config(bg=self.light_hex)
        try:
            self.colour_vals = self.pad.read_colours(self.key_count)
        except Exception:
            self.colour_vals = [(0, 255, 0)] * self.key_count
        # ensure button grid matches layout
        if len(getattr(self, "pk_btns", [])) != self.key_count:
            self.rebuild_perkey_grid()
        for b, c in zip(self.pk_btns, self.colour_vals):
            hx = "#%02x%02x%02x" % c
            b.config(bg=hx, activebackground=hx)

    def pick_light_colour(self):
        c = colorchooser.askcolor(color=self.light_hex, parent=self)[1]
        if c:
            self.light_hex = c
            self.colour_btn.config(bg=c)
            self.use_colour.set(True)

    def apply_light(self):
        def go():
            cur = bytearray(self.pad.read_light())
            cur[2] = LIGHT_MODES.index(self.mode_var.get())
            cur[3] = self.bright_var.get()
            cur[4] = self.speed_var.get()
            use = self.use_colour.get() and cur[2] != 0
            cur[6] = 1 if use else 0
            if use:
                cur[8], cur[9], cur[10] = hex_to_hsv255(self.light_hex)
            self.pad.write_light(bytes(cur))
            self.status.set("Lighting applied")
        self.guard(go)

    def set_perkey(self):
        self.mode_var.set("perkey")
        self.use_colour.set(False)
        self.apply_light()

    def pick_key_colour(self, i):
        c = colorchooser.askcolor(color="#%02x%02x%02x" % self.colour_vals[i], parent=self)
        if not c[1]:
            return

        def go():
            rgb = tuple(int(x) for x in c[0])
            self.pad.write_colour(i, bytes(rgb))
            self.colour_vals[i] = rgb
            self.pk_btns[i].config(bg=c[1], activebackground=c[1])
            self.status.set(f"Key {i + 1} colour set (visible in perkey mode)")
        self.guard(go)


if __name__ == "__main__":
    App().mainloop()
