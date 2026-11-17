#!/usr/bin/env python3
"""sdpad - Linux config tool for SDINNOVATION "SIDE-KEYBOARD" macro pads.

Protocol from https://github.com/rickskelton/sd-macro-pad (docs/TECHNICAL_REFERENCE.md).
No dependencies: talks to the vendor HID interface through /dev/hidrawN.

Usage:
  sdpad.py info
  sdpad.py keys [--profile N]
  sdpad.py set <index> <combo> [--profile N]     e.g. set 0 ctrl+shift+a | media:volup | text keys: f13
  sdpad.py disable <index>
  sdpad.py profile <n>
  sdpad.py light                                  show lighting
  sdpad.py light <off|solid|breathing|press|tide|perkey> [--colour #rrggbb] [--brightness 0-4]
  sdpad.py colour <index> <#rrggbb>
Indices: keys 0..15 row by row from top-left; dials start at 16 (press, cw, ccw).
"""
import os, sys, glob, select, time, argparse

# Known USB IDs: (VID, PID)
# 6D7F:DCFE - common SDINNOVATION/SDCX family
# 0816:2473 - SDINNOVATION SIDE-KEYBOARD (alternate VID/PID)
SUPPORTED_DEVICES = {(0x6D7F, 0xDCFE), (0x0816, 0x2473)}
SUPPORTED_VIDS = {vid for vid, _ in SUPPORTED_DEVICES}



# ---------------------------------------------------------------- device
def _match_requested(vid, pid, req_vid=None, req_pid=None):
    """Return True if a USB VID/PID matches the user-requested filter (if provided)."""
    if req_vid is not None and vid != req_vid:
        return False
    if req_pid is not None and pid != req_pid:
        return False
    return True


def _open_hid_device(req_vid=None, req_pid=None):
    """Try to open the vendor config HID interface via hidapi.
    Prefers interface 2 / usage page 0xFF00 and supports optional VID/PID overrides.
    """
    try:
        import hid
        if req_vid is not None:
            for d in hid.enumerate(req_vid):
                if not _match_requested(d.get("vendor_id"), d.get("product_id"), req_vid, req_pid):
                    continue
                if d.get("interface_number") == 2 or d.get("usage_page") == 0xFF00:
                    dev = hid.device()
                    dev.open_path(d["path"])
                    return dev, "hidapi"
        for vid in sorted(SUPPORTED_VIDS):
            for d in hid.enumerate(vid):
                # Look for the vendor config interface: interface_number == 2, or usage_page == 0xFF00
                if d.get("interface_number") == 2 or d.get("usage_page") == 0xFF00:
                    dev = hid.device()
                    dev.open_path(d["path"])
                    return dev, "hidapi"
        # Fallback: scan all HID devices for a supported/requested VID/PID on a vendor-like interface
        for d in hid.enumerate():
            vid, pid = d.get("vendor_id"), d.get("product_id")
            if (vid, pid) in SUPPORTED_DEVICES or (req_vid is not None and _match_requested(vid, pid, req_vid, req_pid)):
                if d.get("interface_number") == 2 or d.get("usage_page") == 0xFF00:
                    dev = hid.device()
                    dev.open_path(d["path"])
                    return dev, "hidapi"
    except (ImportError, Exception):
        pass
    return None, None

def find_config_hidraw(req_vid=None, req_pid=None):
    """Return /dev/hidrawN of the vendor config interface (Linux native fallback).
    Matches supported/requested VID:PID devices and selects interface number 2.
    """
    if not sys.platform.startswith("linux"):
        return None
    for d in sorted(glob.glob("/sys/class/hidraw/hidraw*")):
        link = os.path.realpath(os.path.join(d, "device"))
        base = os.path.basename(link)  # e.g. 0003:0816:2473.001E
        try:
            _, vid, pid = base.split(".")[0].split(":")
            vid, pid = int(vid, 16), int(pid, 16)
        except ValueError:
            continue
        if not ((vid, pid) in SUPPORTED_DEVICES or (req_vid is not None and _match_requested(vid, pid, req_vid, req_pid))):
            continue
        iface = os.path.basename(os.path.dirname(link)).rsplit(".", 1)[-1]
        if iface == "2":
            return "/dev/" + os.path.basename(d)
    return None


class Pad:
    def __init__(self, path=None, vid=None, pid=None):
        self.hid_dev, self.mode = _open_hid_device(vid, pid)
        self.fd = None
        self.path = path
        self.vid, self.pid = vid, pid

        if not self.hid_dev:
            # Fallback to direct hidraw
            self.path = path or find_config_hidraw(vid, pid)
            if not self.path:
                msg = "Macro pad config interface not found (is it plugged in?)"
                if sys.platform.startswith("win"):
                    msg += "\nOn Windows, ensure 'pip install hid' or 'pip install hidapi' is installed."
                if vid is not None:
                    msg += f"\nRequested VID:PID {vid:04X}:{pid:04X}" if pid is not None else f"\nRequested VID {vid:04X}"
                sys.exit(msg)
            try:
                self.fd = os.open(self.path, os.O_RDWR | os.O_NONBLOCK)
                self.mode = "hidraw"
            except PermissionError:
                sys.exit(f"Permission denied on {self.path}. Install the udev rule:\n"
                         "  sudo cp 99-sdpad.rules /etc/udev/rules.d/ && "
                         "sudo udevadm control --reload && sudo udevadm trigger")
        else:
            self.path = "HIDAPI Device"

    def request(self, *payload, timeout=1.5):
        # Protocol frame: 0x06 prefix + command payload, padded to 64 bytes.
        frame = bytes([0x06, *payload])
        frame += bytes(64 - len(frame))

        # Key-table reads (cmd 0x08) are answered with 0x07 in this protocol family.
        want = 0x07 if payload[0] == 0x08 else payload[0]

        if self.mode == "hidapi":
            # hidapi expects report ID as first byte (0x00 for standard)
            self.hid_dev.write(b"\x00" + frame)
            end = time.time() + timeout
            while time.time() < end:
                reply = self.hid_dev.read(64, timeout_ms=int(timeout * 1000))
                if len(reply) > 1 and reply[0] == 0xAA and reply[1] == want:
                    return bytes(reply)
            raise TimeoutError(f"no reply to command {payload[0]:02X}")
        else:
            os.write(self.fd, frame)
            end = time.time() + timeout
            while time.time() < end:
                r, _, _ = select.select([self.fd], [], [], 0.1)
                if not r:
                    continue
                reply = os.read(self.fd, 64)
                if len(reply) > 1 and reply[0] == 0xAA and reply[1] == want:
                    return reply
            raise TimeoutError(f"no reply to command {payload[0]:02X}")

    # -- info
    def info(self):
        d = self.request(0x05)[5:]
        return dict(protocol=d[0] | d[1] << 8, pid=d[2] | d[3] << 8,
                    firmware=d[4] | d[5] << 8, profiles=d[10], active=d[11],
                    layers=d[12])

    def select_profile(self, n):
        self.request(0xFB, n)

    # -- key table
    def read_table(self, layer=0, entries=28):
        raw = b""
        off = 0
        while len(raw) < entries * 4:
            r = self.request(0x08, 0x3A, off & 0xFF, off >> 8, 0, layer)
            raw += bytes(r[8:8 + 56])
            off += 56
        return [tuple(raw[i * 4:i * 4 + 4]) for i in range(entries)]

    # -- per-key colours
    def read_colours(self, count=16):
        raw = b""
        off = 0
        while len(raw) < count * 3:
            r = self.request(0x13, 0x3A, off & 0xFF, off >> 8)
            raw += bytes(r[8:8 + 56])
            off += 56
        return [tuple(raw[i * 3:i * 3 + 3]) for i in range(count)]

    # -- macros (one 4096-byte table shared by all profiles)
    MACRO_SIZE = 4096

    def read_macro_table(self):
        table = b""
        while len(table) < self.MACRO_SIZE:
            n = min(56, self.MACRO_SIZE - len(table))
            r = self.request(0x0C, n, len(table) & 0xFF, len(table) >> 8)
            table += bytes(r[8:8 + n])
        return table

    def write_macro_table(self, table):
        assert len(table) == self.MACRO_SIZE
        last = max((i for i, b in enumerate(table) if b), default=0)
        used = max(64, last + 1)
        off = 0
        while off < used:
            chunk = table[off:min(off + 56, self.MACRO_SIZE)]
            self.request(0x0D, len(chunk), off & 0xFF, off >> 8, *chunk)
            off += len(chunk)

    def write_key(self, index, entry, layer=0):
        off = index * 4
        self.request(0x10, 0x07, off & 0xFF, off >> 8, 0, layer, 0, *entry)

    # -- lighting
    def read_light(self):
        return bytes(self.request(0x0A)[5:5 + 11])

    def write_light(self, b11):
        self.request(0x0B, 0x0B, 0, 0, *b11)

    def write_colour(self, index, rgb):
        off = index * 3
        self.request(0x14, 0x03, off & 0xFF, off >> 8, 0, 0, 0, *rgb)


# ---------------------------------------------------------------- key names
MODS = {"ctrl": 1, "control": 1, "shift": 2, "alt": 4, "option": 4, "gui": 8, "win": 8, "super": 8, "cmd": 8, "command": 8,
        "rctrl": 0x10, "rcontrol": 0x10, "rshift": 0x20, "ralt": 0x40, "roption": 0x40, "rgui": 0x80, "rcommand": 0x80}
KEYS = {}
for i, c in enumerate("abcdefghijklmnopqrstuvwxyz"):
    KEYS[c] = 0x04 + i
for i, c in enumerate("1234567890"):
    KEYS[c] = 0x1E + i
KEYS.update({"enter": 0x28, "esc": 0x29, "backspace": 0x2A, "tab": 0x2B, "space": 0x2C,
             "-": 0x2D, "=": 0x2E, "[": 0x2F, "]": 0x30, "\\": 0x31, ";": 0x33,
             "'": 0x34, "`": 0x35, ",": 0x36, ".": 0x37, "/": 0x38, "capslock": 0x39,
             "printscreen": 0x46, "scrolllock": 0x47, "pause": 0x48, "insert": 0x49,
             "home": 0x4A, "pageup": 0x4B, "delete": 0x4C, "end": 0x4D, "pagedown": 0x4E,
             "right": 0x4F, "left": 0x50, "down": 0x51, "up": 0x52, "numlock": 0x53,
             # keypad / numpad
             "kp/": 0x54, "kp*": 0x55, "kp-": 0x56, "kp+": 0x57, "kpenter": 0x58,
             "kp1": 0x59, "kp2": 0x5A, "kp3": 0x5B, "kp4": 0x5C, "kp5": 0x5D,
             "kp6": 0x5E, "kp7": 0x5F, "kp8": 0x60, "kp9": 0x61, "kp0": 0x62,
             "kp.": 0x63, "kp=": 0x67, "kp,": 0x85, "kp=as400": 0x86,
             "kp00": 0xB0, "kp000": 0xB1, "kpthousands": 0xB2, "kpdecimal_sep": 0xB3,
             "kpcurrency": 0xB4, "kpcurrency_sub": 0xB5, "kp(": 0xB6, "kp)": 0xB7,
             "kp{": 0xB8, "kp}": 0xB9, "kptab": 0xBA, "kpbackspace": 0xBB,
             "kpa": 0xBC, "kpb": 0xBD, "kpc": 0xBE, "kpd": 0xBF, "kpe": 0xC0, "kpf": 0xC1,
             "kpxor": 0xC2, "kp^": 0xC3, "kp%": 0xC4, "kp<": 0xC5, "kp>": 0xC6,
             "kp&": 0xC7, "kp&&": 0xC8, "kp|": 0xC9, "kp||": 0xCA, "kp:": 0xCB,
             "kp#": 0xCC, "kpspace": 0xCD, "kp@": 0xCE, "kp!": 0xCF,
             "kpmem_store": 0xD0, "kpmem_recall": 0xD1, "kpmem_clear": 0xD2,
             "kpmem_add": 0xD3, "kpmem_sub": 0xD4, "kpmem_mul": 0xD5, "kpmem_div": 0xD6,
             "kp+/-": 0xD7, "kpclear": 0xD8, "kpclear_entry": 0xD9,
             "kpbinary": 0xDA, "kpoctal": 0xDB, "kpdecimal": 0xDC, "kphex": 0xDD,
             # locking keys
             "locking_caps": 0x82, "locking_num": 0x83, "locking_scroll": 0x84,
             "menu": 0x65})
for i in range(12):
    KEYS[f"f{i + 1}"] = 0x3A + i
for i in range(12):
    KEYS[f"f{i + 13}"] = 0x68 + i
# Additional HID keyboard usages
KEYS.update({
    "execute": 0x74, "help": 0x75, "menu2": 0x76, "select": 0x77,
    "stop": 0x78, "stop_kb": 0x78, "again": 0x79, "undo": 0x7A, "cut": 0x7B,
    "copy": 0x7C, "paste": 0x7D, "find": 0x7E, "kbmute": 0x7F,
    "volup_kb": 0x80, "voldown_kb": 0x81,  # keyboard volume (page 0x07), distinct from consumer media
})
CONSUMER = {"play": 0xCD, "next": 0xB5, "prev": 0xB6, "stop": 0xB7, "mute": 0xE2,
            "volup": 0xE9, "voldown": 0xEA, "brightup": 0x6F, "brightdown": 0x70,
            "multimedia": 0x0183, "mail": 0x018A, "calculator": 0x0192, "mypc": 0x0194,
            "web-search": 0x0221, "web-home": 0x0223, "web-backward": 0x0224,
            "web-forward": 0x0225, "web-stop": 0x0226, "web-refresh": 0x0227,
            "web-favorites": 0x022A}
KEYS_REV = {v: k for k, v in KEYS.items()}
# prefer clearer disambiguated names
KEYS_REV[0x78] = "stop_kb"
CONS_REV = {v: k for k, v in CONSUMER.items()}


def parse_action(s):
    """Parse a CLI/GUI action string into a 4-byte key entry tuple (type,c1,c2,c3).
    Supports named actions, mouse/media/macro forms, raw hex, and key combos.
    """
    s = s.strip().lower()
    if s in ("none", "disabled"):
        return (0x13, 0, 0, 0)
    kbctl_map = {
        "light_switch": 0x00, "lightswitch": 0x00, "light-switch": 0x00,
        "light_effect": 0x01, "lighteffect": 0x01, "light-effect": 0x01,
        "kb_brightness_down": 0x02, "kb_brightness-": 0x02, "kbbrightnessdown": 0x02,
        "brightness_down": 0x02, "brightness-": 0x02, "brightnessdown": 0x02,
        "kb_brightness_up": 0x03, "kb_brightness+": 0x03, "kbbrightnessup": 0x03,
        "brightness_up": 0x03, "brightness+": 0x03, "brightnessup": 0x03,
        "color_switch": 0x04, "colorswitch": 0x04, "color-switch": 0x04,
        "light_speed_up": 0x05, "light_speed+": 0x05, "lightspeedup": 0x05,
        "light_speed_down": 0x06, "light_speed-": 0x06, "lightspeeddown": 0x06,
        "profile_switch": 0x13, "profile:switch": 0x13, "profileswitch": 0x13, "profile-switch": 0x13,
        "light_direction": 0x14, "lightdirection": 0x14, "light-direction": 0x14,
        "keyboard_lock": 0x19, "keyboardlock": 0x19, "keyboard-lock": 0x19, "keylock": 0x19,
    }
    if s in kbctl_map:
        return (0x1F, kbctl_map[s], 0, 0)
    if s in ("power",):
        return (0x40, 0x01, 0, 0)
    if s in ("sleep",):
        return (0x40, 0x02, 0, 0)
    if s in ("wakeup", "wake"):
        return (0x40, 0x04, 0, 0)
    if s.startswith("mousemove:") or s.startswith("mousemove:") or s.startswith("cursor:"):
        # mousemove:up:N,down:N,left:N,right:N  (values 0-255, positive)
        if s.startswith("mousemove:"):
            spec = s[10:]
        elif s.startswith("mousemove:"):
            spec = s[10:]
        else:
            spec = s[7:]
        a = b = c = 0
        if spec and spec != "0":
            for part in spec.split(","):
                part = part.strip()
                if ":" not in part:
                    continue
                k, v = part.split(":", 1)
                n = int(v, 0) & 0xFF
                if k == "up":
                    a |= 0x08
                    c = n
                elif k == "down":
                    a &= ~0x08
                    c = n
                elif k == "left":
                    a |= 0x80
                    b = n
                elif k == "right":
                    a &= ~0x80
                    b = n
        return (0x11, a, b, c)
    if s.startswith("media:"):
        name = s[6:]
        aliases = {"home": "web-home", "webhome": "web-home", "web_home": "web-home",
                   "websearch": "web-search", "web_search": "web-search",
                   "webbackward": "web-backward", "web_backward": "web-backward", "web-back": "web-backward",
                   "webforward": "web-forward", "web_forward": "web-forward",
                   "webstop": "web-stop", "web_stop": "web-stop",
                   "webrefresh": "web-refresh", "web_refresh": "web-refresh",
                   "webfavorites": "web-favorites", "web_favorites": "web-favorites"}
        name = aliases.get(name, name)
        u = CONSUMER[name]
        return (0x30, u & 0xFF, u >> 8, 0)
    if s.startswith("macro:"):
        parts = s[6:].split(":")
        idx = int(parts[0])
        rep = int(parts[1]) if len(parts) > 1 and parts[1] != "" else 1
        mode = int(parts[2]) if len(parts) > 2 and parts[2] != "" else 0
        return (0x60, idx & 0xFF, rep & 0xFF, mode & 0xFF)
    if s.startswith("mouse:"):
        m = {"left": (1, 0), "right": (2, 0), "middle": (4, 0), "wheelup": (0, 1),
             "wheeldown": (0, 0xFF), "back": (8, 0), "backward": (8, 0), "backwards": (8, 0),
             "forward": (16, 0)}[s[6:]]
        return (0x10, m[0], 0, m[1])
    if s.startswith("raw:"):
        b = bytes.fromhex(s[4:].replace(" ", "").replace("-", ""))
        if len(b) != 4:
            raise ValueError("raw: needs exactly 4 bytes")
        return tuple(b)
    h = s.replace(" ", "").replace("-", "")
    if len(h) == 8:
        try:
            b = bytes.fromhex(h)
            return tuple(b)
        except ValueError:
            pass
    # Keystroke/combo: consume leading modifiers, remainder is the key name (may contain '+', e.g. kp+)
    mods, key = 0, 0
    rest = s
    while True:
        matched = False
        for mod in sorted(MODS, key=len, reverse=True):
            if rest == mod or rest.startswith(mod + "+"):
                mods |= MODS[mod]
                rest = rest[len(mod):]
                if rest.startswith("+"):
                    rest = rest[1:]
                matched = True
                break
        if not matched:
            break
    if rest in KEYS:
        key = KEYS[rest]
    elif rest == "":
        key = 0
    else:
        sys.exit(f"Unknown key '{rest}'")
    return (0x20, mods, key, 0)


def describe(e):
    """Describe a 4-byte key entry as a human/CLI-friendly string."""
    t, a, b, c = e
    if t == 0x20:
        names = [n for n, v in (("ctrl", 1), ("shift", 2), ("alt", 4), ("gui", 8)) if a & v]
        if b:
            names.append(KEYS_REV.get(b, f"usage:{b:02X}"))
        return "+".join(names) or "(empty key)"
    if t == 0x30:
        u = a | b << 8
        return "media:" + CONS_REV.get(u, f"{u:04X}")
    if t == 0x13:
        return "disabled"
    if t == 0x60:
        return f"macro {a} (x{b}, mode {c})"
    if t == 0x10:
        if c == 0 and a in (1, 2, 4, 8, 16):
            name = {1: "left", 2: "right", 4: "middle", 8: "back", 16: "forward"}[a]
            return "mouse:" + name
        if c == 1 and a == 0:
            return "mouse:wheelup"
        if c == 0xFF and a == 0:
            return "mouse:wheeldown"
        return f"mouse buttons={a:02X} wheel={c if c < 128 else c - 256}"
    if t == 0x1F:
        names = {
            0x00: "light_switch",
            0x01: "light_effect",
            0x02: "kb_brightness_down",
            0x03: "kb_brightness_up",
            0x04: "color_switch",
            0x05: "light_speed_up",
            0x06: "light_speed_down",
            0x13: "profile_switch",
            0x14: "light_direction",
            0x19: "keyboard_lock",
        }
        if a in names:
            return names[a]
    if t == 0x40 and a == 0x01:
        return "power"
    if t == 0x40 and a == 0x02:
        return "sleep"
    if t == 0x40 and a == 0x04:
        return "wakeup"
    if t == 0x11:
        # Mouse-move encoding (device-specific): b0 flags direction (0x08 up, 0x80 left),
        # b1 = horizontal amount, b2 = vertical amount (positive steps).
        parts = []
        if a & 0x08 and c:
            parts.append(f"up:{c}")
        elif c:
            parts.append(f"down:{c}")
        if a & 0x80 and b:
            parts.append(f"left:{b}")
        elif b:
            parts.append(f"right:{b}")
        return "mousemove:" + ",".join(parts) if parts else "mousemove:0"
    return f"type {t:02X}: {a:02X} {b:02X} {c:02X}"


def label(i):
    if i < 16:
        return f"key {i}"
    d, k = divmod(i - 16, 3)
    return f"dial {d + 1} {['press', 'clockwise', 'anticlockwise'][k]}"


def action_to_cli(e):
    """Return a parse_action-compatible CLI string for entry e (best-effort)."""
    t, a, b, c = e
    try:
        d = describe(e)
    except Exception:
        d = None
    # Known parseable forms
    if t == 0x13:
        return "none"
    if t == 0x20:
        parts = [n for n, v in (("ctrl", 1), ("shift", 2), ("alt", 4), ("gui", 8)) if a & v]
        if b:
            parts.append(KEYS_REV.get(b, f"raw:{bytes(e).hex()}"))
        if not parts:
            return "raw:" + bytes(e).hex()
        # all parts must be parseable key/mod names
        ok = True
        for p in parts:
            if p.startswith("raw:"):
                ok = False
        if ok:
            return "+".join(parts)
        return "raw:" + bytes(e).hex()
    if t == 0x30:
        u = a | b << 8
        name = CONS_REV.get(u)
        return f"media:{name}" if name else "raw:" + bytes(e).hex()
    if t == 0x10:
        if c == 0 and a in (1, 2, 4, 8, 16):
            return "mouse:" + {1:"left",2:"right",4:"middle",8:"back",16:"forward"}[a]
        if a == 0 and c == 1:
            return "mouse:wheelup"
        if a == 0 and c == 0xFF:
            return "mouse:wheeldown"
        return "raw:" + bytes(e).hex()
    if t == 0x11:
        return d if d and d.startswith("mousemove:") else "raw:" + bytes(e).hex()
    if t == 0x60:
        return f"macro:{a}:{b}:{c}"
    if t in (0x1F, 0x40) and d in ("profile_switch","keyboard_lock","light_switch","light_effect","brightness_down","brightness_up","color_switch","light_speed_up","light_speed_down","light_direction","power","sleep","wakeup","kb_brightness_down","kb_brightness_up"):
        return d
    # fallback: raw hex is always parseable with extended parse_action
    return "raw:" + bytes(e).hex()


# ---------------------------------------------------------------- CLI
LIGHT_MODES = ["off", "solid", "breathing", "press", "tide", "perkey"]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("cmd", choices=["info", "keys", "set", "disable", "profile", "light", "colour", "raw"])
    ap.add_argument("args", nargs="*")
    ap.add_argument("--profile", type=int)
    ap.add_argument("--colour")
    ap.add_argument("--brightness", type=int)
    ap.add_argument("--vid", type=lambda x: int(x, 0), help="USB vendor ID (e.g. 0x0816) for unlisted devices")
    ap.add_argument("--pid", type=lambda x: int(x, 0), help="USB product ID (e.g. 0x2473) for unlisted devices")
    a = ap.parse_args()
    pad = Pad(vid=a.vid, pid=a.pid)

    if a.profile is not None and a.cmd in ("keys", "set", "disable"):
        pad.select_profile(a.profile - 1)  # user-facing 1-based
        time.sleep(0.2)

    if a.cmd == "info":
        for k, v in pad.info().items():
            print(f"{k:10} {v:#06x}" if k == "pid" else f"{k:10} {v}")
    elif a.cmd == "keys":
        info = pad.info()
        print(f"Profile {info['active'] + 1} of {info['profiles']}")
        for i, e in enumerate(pad.read_table()):
            print(f"{i:3}  {label(i):22} {bytes(e).hex(' ')}   {describe(e)}")
    elif a.cmd == "set":
        idx, act = int(a.args[0]), parse_action(a.args[1])
        pad.write_key(idx, act)
        print(f"{label(idx)} -> {describe(act)}")
    elif a.cmd == "disable":
        pad.write_key(int(a.args[0]), parse_action("none"))
    elif a.cmd == "profile":
        pad.select_profile(int(a.args[0]) - 1)
    elif a.cmd == "colour":
        h = a.args[1].lstrip("#")
        pad.write_colour(int(a.args[0]), bytes.fromhex(h))
    elif a.cmd == "raw":
        print(bytes(pad.request(*bytes.fromhex("".join(a.args)))).hex(" "))
    elif a.cmd == "light":
        cur = bytearray(pad.read_light())
        if not a.args and a.colour is None and a.brightness is None:
            print("raw:", cur.hex(" "))
            print(f"mode={LIGHT_MODES[cur[2]] if cur[2] < 6 else cur[2]} brightness={cur[3]} "
                  f"speed={cur[4]} dir={cur[5]} colourflag={cur[6]} HSV={cur[8]},{cur[9]},{cur[10]}")
            return
        if a.args:
            cur[2] = LIGHT_MODES.index(a.args[0])
        if a.brightness is not None:
            cur[3] = a.brightness
        if a.colour:
            import colorsys
            r, g, b = (int(a.colour.lstrip('#')[i:i + 2], 16) / 255 for i in (0, 2, 4))
            h, s, v = colorsys.rgb_to_hsv(r, g, b)
            cur[6], cur[8], cur[9], cur[10] = 1, int(h * 255), int(s * 255), int(v * 255)
        pad.write_light(bytes(cur))
        print("ok")


if __name__ == "__main__":
    main()
