"""pad_canvas.py - High-fidelity realistic graphic rendering of the 9-key + 2-dial macro pad.

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
    """Custom graphical representation of the 9-key, 2-dial hardware pad."""
    def __init__(self, parent, on_select_slot=None, **kwargs):
        super().__init__(parent, bg="#0b0b0d", **kwargs)
        self.on_select_slot = on_select_slot
        self.selected_slot = None
        self.hovered_slot = None
        self.table = []
        self.key_colors = {}   # slot -> hex color "#rrggbb"
        self.rgb_mode = "palette" # "palette" or "perkey"

        self.canvas = tk.Canvas(self, width=460, height=480, bg="#0b0b0d", highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)

        self.canvas.bind("<Motion>", self._on_motion)
        self.canvas.bind("<Leave>", self._on_leave)
        self.canvas.bind("<Button-1>", self._on_click)

        # Geometry definition
        # Pad layout:
        # Top-left to bottom-right: 3x3 key matrix
        # Right side or top: 2 large rotary encoder dials with press center & side wings for CCW/CW
        self.hitboxes = {} # slot -> (type, (x1, y1, x2, y2) or center/radius)

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

    def draw(self):
        c = self.canvas
        c.delete("all")
        self.hitboxes.clear()

        # Canvas dims: width ~450, height ~470
        # 1. Draw pad shadow and chassis
        # Outer shadow
        round_polygon(c, 24, 24, 436, 456, radius=24, fill="#050507", outline="")
        round_polygon(c, 20, 20, 430, 450, radius=22, fill="#121216", outline="#2c2c36", width=2)
        
        # Inner beveled surface plate (brushed dark metal look)
        round_polygon(c, 26, 26, 424, 444, radius=18, fill="#18181e", outline="#25252e", width=1)
        
        # Subtle accent trim line at top
        c.create_line(50, 27, 400, 27, fill="#44d62c", width=1.5)

        # Brand badge plate
        round_polygon(c, 160, 36, 290, 58, radius=8, fill="#0f0f13", outline="#282832", width=1)
        c.create_text(225, 47, text="SD-9 PRO", fill="#626270", font=("DejaVu Sans", 8, "bold"))

        # Dials at the top right / top
        # Let's organize cleanly:
        # Top area: Dial 1 (Left) and Dial 2 (Right)
        # Below: 3x3 Key Matrix (Keys 1-9)
        # Dial 1: slot 16 (press), 18 (turn left / ccw), 17 (turn right / cw)
        # Dial 2: slot 19 (press), 21 (turn left / ccw), 20 (turn right / cw)
        
        self._draw_dial(dial_num=1, cx=115, cy=105, press_slot=16, left_slot=18, right_slot=17)
        self._draw_dial(dial_num=2, cx=335, cy=105, press_slot=19, left_slot=21, right_slot=20)

        # 3x3 Keys Matrix
        # start_x = 45, start_y = 165
        # key size = 110x78, spacing x=15, spacing y=12
        kx_start = 45
        ky_start = 165
        kw = 110
        kh = 80
        gap_x = 18
        gap_y = 12

        for row in range(3):
            for col in range(3):
                idx = row * 3 + col # slot 0..8
                x1 = kx_start + col * (kw + gap_x)
                y1 = ky_start + row * (kh + gap_y)
                x2 = x1 + kw
                y2 = y1 + kh
                self._draw_key(idx, x1, y1, x2, y2)

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
                if a in (1, 2, 4):
                    btn = {1: "Left", 2: "Right", 4: "Middle"}.get(a, "Click")
                    return ("MOUSE", f"{btn} Click")
                if c == 1:
                    return ("MOUSE", "Wheel Up")
                if c == 0xFF or c == -1:
                    return ("MOUSE", "Wheel Down")
                return ("MOUSE", "Mouse Action")
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

        # Key label (e.g. KEY 1, KEY 2)
        key_num_color = "#44d62c" if is_sel else "#888898"
        c.create_text(x1 + 10, y1 + 14, text=f"K{slot + 1}", fill=key_num_color, font=("DejaVu Sans", 9, "bold"), anchor="w")

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
