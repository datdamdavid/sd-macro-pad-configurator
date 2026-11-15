"""pad_canvas.py - High-fidelity realistic graphic rendering of SD macro pads.

Provides interactive visualization:
- Chamfered/rounded chassis with textured bezels
- Keycaps with glow effects matching the pad's RGB per-key colors (or dynamic theme accent)
- CNC-style rotary knurled metal dials with position indicators, turn direction arrows & center push indicator
- Hover states, selection states, badges for key function (MACRO, MEDIA, KEY, MOUSE)
- Crisp labels for both key number and active assigned action
"""
import math
import tkinter as tk

def round_polygon(canvas, x1, y1, x2, y2, radius=12, **kwargs):
    """Draw a rounded rectangle using a polygon with smooth curved corners."""
    r = radius
    points = [
        x1 + r, y1,
        x2 - r, y1,
        x2, y1,
        x2, y1 + r,
        x2, y2 - r,
        x2, y2,
        x2 - r, y2,
        x1 + r, y2,
        x1, y2,
        x1, y2 - r,
        x1, y1 + r,
        x1, y1,
    ]
    return canvas.create_polygon(points, smooth=True, **kwargs)

class PadCanvas(tk.Frame):
    """Custom graphical representation of a macro pad (configurable key matrix + dials)."""
    def __init__(self, parent, on_select_slot=None, layout=None, **kwargs):
        super().__init__(parent, bg="#0b0b0d", **kwargs)
        self.on_select_slot = on_select_slot
        self.selected_slot = None
        self.hovered_slot = None
        self.table = []
        self.key_colors = {}   # slot -> hex color "#rrggbb"
        self.rgb_mode = "palette" # "palette" or "perkey"
        self.layout = dict(layout or dict(key_count=9, cols=3, rows=3, dial_count=2, name="SD-9 PRO"))
        self.cols = self.layout.get("cols", 3)
        self.rows = self.layout.get("rows", 3)
        self.key_count = self.layout.get("key_count", self.cols * self.rows)
        self.dial_count = self.layout.get("dial_count", 2)

        self.canvas = tk.Canvas(self, width=460, height=480, bg="#0b0b0d", highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)

        self.canvas.bind("<Motion>", self._on_motion)
        self.canvas.bind("<Leave>", self._on_leave)
        self.canvas.bind("<Button-1>", self._on_click)

        self.hitboxes = {} # slot -> (type, (x1, y1, x2, y2) or center/radius)

        self.draw()

    def set_layout(self, layout):
        self.layout = dict(layout)
        self.cols = self.layout.get("cols", 3)
        self.rows = self.layout.get("rows", 3)
        self.key_count = self.layout.get("key_count", self.cols * self.rows)
        self.dial_count = self.layout.get("dial_count", 2)
        self.draw()

    def set_data(self, table, selected_slot=None, key_colors=None, rgb_mode=None):
        self.table = table
        self.selected_slot = selected_slot
        if key_colors is not None:
            self.key_colors = key_colors
        if rgb_mode is not None:
            self.rgb_mode = rgb_mode
        self.draw()

    def set_selected(self, slot):
        self.selected_slot = slot
        self.draw()

    def _slot_to_visual(self, slot):
        """Return (visual_row, col) for a key slot, or None."""
        if slot >= self.key_count:
            return None
        # 0816:2473: protocol slots are column-wise, bottom-to-top, left-to-right
        # left: 0,1,2,3 (bottom->top), middle: 4,5,6,7, right: 8,9,10,11
        if self.layout.get("name") == "SIDE-KEYBOARD" and self.cols == 3 and self.rows == 4:
            col = slot // self.rows
            row_from_bottom = slot % self.rows
            return (self.rows - 1 - row_from_bottom, col)
        # default: row-major from top-left
        return (slot // self.cols, slot % self.cols)

    def _key_label(self, slot):
        # 0816:2473 physical numbering follows slot order in this column-wise mapping
        if self.layout.get("name") == "SIDE-KEYBOARD" and self.cols == 3 and self.rows == 4 and slot < self.key_count:
            return f"K{slot + 1}"
        return f"K{slot + 1}"

    def draw(self):
        c = self.canvas
        c.delete("all")
        self.hitboxes.clear()

        # Layout-dependent geometry
        cols = max(1, int(self.cols))
        rows = max(1, int(self.rows))
        kx_start = 45
        ky_start = 165
        kw = 110
        kh = 80
        gap_x = 18
        gap_y = 12
        grid_w = cols * kw + (cols - 1) * gap_x
        grid_h = rows * kh + (rows - 1) * gap_y
        pad_w = max(460, kx_start * 2 + grid_w + 20)
        pad_h = max(480, ky_start + grid_h + 36)
        c.config(width=pad_w, height=pad_h)

        # 1. Draw pad shadow and chassis
        round_polygon(c, 24, 24, pad_w - 24, pad_h - 24, radius=24, fill="#050507", outline="")
        round_polygon(c, 20, 20, pad_w - 30, pad_h - 30, radius=22, fill="#121216", outline="#2c2c36", width=2)
        round_polygon(c, 26, 26, pad_w - 36, pad_h - 36, radius=18, fill="#18181e", outline="#25252e", width=1)
        c.create_line(50, 27, pad_w - 60, 27, fill="#44d62c", width=1.5)

        # Brand badge plate
        badge_w = 150
        bx1 = (pad_w - badge_w) // 2
        bx2 = bx1 + badge_w
        round_polygon(c, bx1, 36, bx2, 58, radius=8, fill="#0f0f13", outline="#282832", width=1)
        label = str(self.layout.get("name", "MACRO PAD"))
        c.create_text((bx1 + bx2) // 2, 47, text=label, fill="#626270", font=("DejaVu Sans", 8, "bold"))

        # Dials at the top
        if self.dial_count >= 1:
            self._draw_dial(dial_num=1, cx=int(pad_w * 0.28), cy=105, press_slot=16, left_slot=18, right_slot=17)
        if self.dial_count >= 2:
            self._draw_dial(dial_num=2, cx=int(pad_w * 0.72), cy=105, press_slot=19, left_slot=21, right_slot=20)

        # Key matrix (position per slot mapping)
        for slot in range(self.key_count):
            pos = self._slot_to_visual(slot)
            if pos is None:
                continue
            row, col = pos
            x1 = kx_start + col * (kw + gap_x)
            y1 = ky_start + row * (kh + gap_y)
            x2 = x1 + kw
            y2 = y1 + kh
            self._draw_key(slot, x1, y1, x2, y2)

    def _get_slot_desc(self, slot):
        if slot < len(self.table):
            e = self.table[slot]
            t, a, b, c = e
            if t == 0x20:
                mods = [n for n, v in (("ctrl", 1), ("shift", 2), ("alt", 4), ("gui", 8)) if a & v]
                kname = ""
                from sdpad import KEYS_REV
                if b in KEYS_REV:
                    kname = KEYS_REV[b]
                elif b:
                    kname = f"#{b:02X}"
                parts = mods + ([kname] if kname else [])
                return ("KEY", "+".join(parts) or "(empty)")
            elif t == 0x30:
                from sdpad import CONS_REV
                u = a | b << 8
                return ("MEDIA", CONS_REV.get(u, f"Media:{u:02X}"))
            elif t == 0x60:
                return ("MACRO", f"Macro {a + 1}")
            elif t == 0x10:
                if a in (1, 2, 4, 8, 16) and c == 0:
                    btn = {1: "Left Click", 2: "Right Click", 4: "Middle Click", 8: "Back", 16: "Forward"}.get(a, "Mouse")
                    return ("MOUSE", btn)
                if c == 1:
                    return ("MOUSE", "Wheel Up")
                if c == 0xFF or c == -1:
                    return ("MOUSE", "Wheel Down")
                return ("MOUSE", "Mouse Action")
            elif t == 0x1F:
                labels = {0x00: "Light Sw", 0x01: "Light FX", 0x02: "KB Bri -", 0x03: "KB Bri +",
                          0x04: "Color Sw", 0x05: "Speed +", 0x06: "Speed -",
                          0x13: "Profile Sw", 0x14: "Light Dir", 0x19: "Kbd Lock"}
                if a in labels:
                    return ("KEY", labels[a])
            elif t == 0x40 and a == 0x01:
                return ("KEY", "Power")
            elif t == 0x40 and a == 0x02:
                return ("KEY", "Sleep")
            elif t == 0x40 and a == 0x04:
                return ("KEY", "Wakeup")
            elif t == 0x11:
                from sdpad import describe as sd_describe
                d = sd_describe(e)
                return ("MOUSE", d.replace("mousemove:", "Move "))
            elif t == 0x13:
                return ("OFF", "Disabled")
            else:
                return ("RAW", f"{t:02X} {a:02X}")
        return ("KEY", "Key")

    def _draw_key(self, slot, x1, y1, x2, y2):
        c = self.canvas
        is_sel = (self.selected_slot == slot)
        is_hov = (self.hovered_slot == slot)
        category, desc = self._get_slot_desc(slot)

        # Register hitbox
        self.hitboxes[slot] = ("rect", (x1, y1, x2, y2))

        # LED Glow Underglow
        glow_color = None
        if self.rgb_mode == "perkey" and slot in self.key_colors:
            glow_color = self.key_colors[slot]
        elif is_sel:
            glow_color = "#44d62c"
        elif is_hov:
            glow_color = "#2a8a1c"

        if glow_color and glow_color not in ("#000000", "#000"):
            # Halo bloom
            round_polygon(c, x1 - 4, y1 - 4, x2 + 4, y2 + 4, radius=16, fill="#122514" if not is_sel else "#1c4020", outline="")
            round_polygon(c, x1 - 2, y1 - 2, x2 + 2, y2 + 2, radius=14, fill="#163018" if not is_sel else "#26542a", outline="")

        # Keycap base shadow & bezel
        round_polygon(c, x1, y1 + 3, x2, y2 + 3, radius=12, fill="#08080a", outline="")

        # Keycap face
        cap_bg = "#22222a" if not is_sel else "#243224"
        if is_hov and not is_sel:
            cap_bg = "#2c2c36"

        border_color = "#44d62c" if is_sel else ("#555566" if is_hov else "#343440")
        border_width = 2.5 if is_sel else 1.2
        round_polygon(c, x1, y1, x2, y2, radius=11, fill=cap_bg, outline=border_color, width=border_width)

        # Subtle top glare reflection on keycap
        c.create_line(x1 + 10, y1 + 4, x2 - 10, y1 + 4, fill="#3e3e4d", width=1)

        # Key label (physical numbering varies by layout)
        key_num_color = "#44d62c" if is_sel else "#888898"
        key_label = self._key_label(slot)
        c.create_text(x1 + 10, y1 + 14, text=key_label, fill=key_num_color, font=("DejaVu Sans", 9, "bold"), anchor="w")

        # Category pill badge
        cat_colors = {
            "MACRO": ("#ff9900", "#2d1f0b"),
            "MEDIA": ("#00b4d8", "#0b2530"),
            "KEY": ("#a0a0b0", "#1e1e24"),
            "MOUSE": ("#9d4edd", "#251233"),
            "OFF": ("#555560", "#141416"),
            "RAW": ("#888888", "#1c1c1c")
        }
        badge_fg, badge_bg = cat_colors.get(category, ("#aaaaaa", "#202020"))
        
        # Draw category pill
        pill_w = 46
        px2 = x2 - 8
        px1 = px2 - pill_w
        py1 = y1 + 8
        py2 = y1 + 20
        round_polygon(c, px1, py1, px2, py2, radius=5, fill=badge_bg, outline=badge_fg, width=0.8)
        c.create_text((px1 + px2) / 2, (py1 + py2) / 2, text=category, fill=badge_fg, font=("DejaVu Sans", 7, "bold"))

        # Main Action Text (Truncated if long)
        act_text = desc
        if len(act_text) > 13:
            act_text = act_text[:11] + "…"
        text_color = "#ffffff" if is_sel else "#e0e0e6"
        c.create_text((x1 + x2) / 2, y1 + 48, text=act_text, fill=text_color, font=("DejaVu Sans", 10, "bold"))

        # Small slot index indicator at bottom right
        c.create_text(x2 - 8, y2 - 9, text=f"slot {slot}", fill="#454552", font=("DejaVu Sans", 6), anchor="e")

    def _draw_dial(self, dial_num, cx, cy, press_slot, left_slot, right_slot):
        c = self.canvas
        r_outer = 38
        r_knob = 28

        # Hitbox areas:
        # 1. Left turn wing (CCW): arc / box to the left
        # 2. Right turn wing (CW): arc / box to the right
        # 3. Knob center: circle press

        # Dial base housing plate
        round_polygon(c, cx - 62, cy - 42, cx + 62, cy + 42, radius=14, fill="#1a1a22", outline="#323242", width=1)
        c.create_text(cx, cy - 31, text=f"DIAL {dial_num}", fill="#a0a0b2", font=("DejaVu Sans", 8, "bold"))

        # Left turn button / wing
        is_left_sel = (self.selected_slot == left_slot)
        is_left_hov = (self.hovered_slot == left_slot)
        lx1, ly1, lx2, ly2 = cx - 56, cy - 18, cx - 32, cy + 24
        self.hitboxes[left_slot] = ("rect", (lx1, ly1, lx2, ly2))
        lbg = "#223824" if is_left_sel else ("#202028" if is_left_hov else "#17171e")
        lborder = "#44d62c" if is_left_sel else ("#666677" if is_left_hov else "#2a2a35")
        round_polygon(c, lx1, ly1, lx2, ly2, radius=6, fill=lbg, outline=lborder, width=1.5 if is_left_sel else 1)
        c.create_text((lx1 + lx2)/2, (ly1 + ly2)/2 - 4, text="⟲", fill="#44d62c" if is_left_sel else "#a0a0b0", font=("DejaVu Sans", 13, "bold"))
        c.create_text((lx1 + lx2)/2, (ly1 + ly2)/2 + 10, text="LEFT", fill="#707080", font=("DejaVu Sans", 6, "bold"))

        # Right turn button / wing
        is_right_sel = (self.selected_slot == right_slot)
        is_right_hov = (self.hovered_slot == right_slot)
        rx1, ry1, rx2, ry2 = cx + 32, cy - 18, cx + 56, cy + 24
        self.hitboxes[right_slot] = ("rect", (rx1, ry1, rx2, ry2))
        rbg = "#223824" if is_right_sel else ("#202028" if is_right_hov else "#17171e")
        rborder = "#44d62c" if is_right_sel else ("#666677" if is_right_hov else "#2a2a35")
        round_polygon(c, rx1, ry1, rx2, ry2, radius=6, fill=rbg, outline=rborder, width=1.5 if is_right_sel else 1)
        c.create_text((rx1 + rx2)/2, (ry1 + ry2)/2 - 4, text="⟳", fill="#44d62c" if is_right_sel else "#a0a0b0", font=("DejaVu Sans", 13, "bold"))
        c.create_text((rx1 + rx2)/2, (ry1 + ry2)/2 + 10, text="RIGHT", fill="#707080", font=("DejaVu Sans", 6, "bold"))

        # Knob Center (Rotary + Press)
        is_press_sel = (self.selected_slot == press_slot)
        is_press_hov = (self.hovered_slot == press_slot)
        self.hitboxes[press_slot] = ("circle", (cx, cy, r_knob))

        # Outer notched ring
        c.create_oval(cx - r_outer + 6, cy - r_outer + 6, cx + r_outer - 6, cy + r_outer - 6, fill="#0a0a0d", outline="#252530")
        
        # Notches around encoder
        for angle_deg in range(0, 360, 30):
            rad = math.radians(angle_deg)
            nx1 = cx + (r_knob + 2) * math.cos(rad)
            ny1 = cy + (r_knob + 2) * math.sin(rad)
            nx2 = cx + (r_knob + 5) * math.cos(rad)
            ny2 = cy + (r_knob + 5) * math.sin(rad)
            c.create_line(nx1, ny1, nx2, ny2, fill="#404050", width=1.5)

        # Center cap
        knob_bg = "#253827" if is_press_sel else ("#2c2c36" if is_press_hov else "#1e1e24")
        knob_border = "#44d62c" if is_press_sel else ("#666677" if is_press_hov else "#3a3a46")
        c.create_oval(cx - r_knob, cy - r_knob, cx + r_knob, cy + r_knob, fill=knob_bg, outline=knob_border, width=2 if is_press_sel else 1.2)

        # Center metallic knurl texture
        c.create_oval(cx - 16, cy - 16, cx + 16, cy + 16, fill="#15151a", outline="#2e2e38")
        c.create_text(cx, cy - 2, text="PUSH", fill="#44d62c" if is_press_sel else "#d0d0e0", font=("DejaVu Sans", 7, "bold"))

        # Action summaries below dial
        # Show what press does
        _, press_desc = self._get_slot_desc(press_slot)
        p_text = f"P: {press_desc}"
        if len(p_text) > 16:
            p_text = p_text[:14] + "…"
        c.create_text(cx, cy + 34, text=p_text, fill="#bfbfc8" if not is_press_sel else "#44d62c", font=("DejaVu Sans", 7))

    def _find_hit(self, x, y):
        for slot, (shape, coords) in self.hitboxes.items():
            if shape == "rect":
                x1, y1, x2, y2 = coords
                if x1 <= x <= x2 and y1 <= y <= y2:
                    return slot
            elif shape == "circle":
                cx, cy, r = coords
                if (x - cx) ** 2 + (y - cy) ** 2 <= r ** 2:
                    return slot
        return None

    def _on_motion(self, event):
        hit = self._find_hit(event.x, event.y)
        if hit != self.hovered_slot:
            self.hovered_slot = hit
            self.draw()
            if hit is not None:
                self.canvas.config(cursor="hand2")
            else:
                self.canvas.config(cursor="")

    def _on_leave(self, event):
        if self.hovered_slot is not None:
            self.hovered_slot = None
            self.draw()
            self.canvas.config(cursor="")

    def _on_click(self, event):
        hit = self._find_hit(event.x, event.y)
        if hit is not None:
            self.selected_slot = hit
            self.draw()
            if self.on_select_slot:
                self.on_select_slot(hit)
