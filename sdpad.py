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

VID, PIDS = 0x6D7F, {0xDCFE}
PIDS_KNOWN_FAMILY = range(0x6D7B, 0x6D84)  # sibling vendor IDs



# ---------------------------------------------------------------- device
def _open_hid_device():
    """Try to open device using hidapi (works on Windows, macOS, and Linux with hidapi)."""
    try:
        import hid
        for vid in list(PIDS_KNOWN_FAMILY) + [VID]:
            for d in hid.enumerate(vid):
                # Look for the vendor config interface: interface_number == 2, or usage_page == 0xFF00
                if d.get("interface_number") == 2 or d.get("usage_page") == 0xFF00:
                    dev = hid.device()
                    dev.open_path(d["path"])
                    return dev, "hidapi"
        # Fallback search by PID if interface not listed
        for d in hid.enumerate():
            if d.get("vendor_id") in (list(PIDS_KNOWN_FAMILY) + [VID]) and 0xDC00 <= (d.get("product_id") or 0) <= 0xDCFF:
                if d.get("interface_number") == 2 or d.get("usage_page") == 0xFF00:
                    dev = hid.device()
                    dev.open_path(d["path"])
                    return dev, "hidapi"
    except (ImportError, Exception):
        pass
    return None, None

def find_config_hidraw():
    """Return /dev/hidrawN of the 64-byte vendor interface (Linux native fallback)."""
    if not sys.platform.startswith("linux"):
        return None
    for d in sorted(glob.glob("/sys/class/hidraw/hidraw*")):
        link = os.path.realpath(os.path.join(d, "device"))
        base = os.path.basename(link)  # 0003:6D7F:DCFE.0009
        try:
            _, vid, pid = base.split(".")[0].split(":")
            vid, pid = int(vid, 16), int(pid, 16)
        except ValueError:
            continue
        if vid in PIDS_KNOWN_FAMILY or vid == VID:
            if not (0xDC00 <= pid <= 0xDCFF):
                continue
            iface = os.path.basename(os.path.dirname(link)).rsplit(".", 1)[-1]
            if iface == "2":
                return "/dev/" + os.path.basename(d)
    return None


class Pad:
    def __init__(self, path=None):
        self.hid_dev, self.mode = _open_hid_device()
        self.fd = None
        self.path = path

        if not self.hid_dev:
            # Fallback to direct hidraw
            self.path = path or find_config_hidraw()
            if not self.path:
                msg = "Macro pad config interface not found (is it plugged in?)"
                if sys.platform.startswith("win"):
                    msg += "\nOn Windows, ensure 'pip install hid' or 'pip install hidapi' is installed."
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
        frame = bytes([0x06, *payload])
        frame += bytes(64 - len(frame))

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
MODS = {"ctrl": 1, "shift": 2, "alt": 4, "gui": 8, "win": 8, "super": 8, "cmd": 8,
        "rctrl": 0x10, "rshift": 0x20, "ralt": 0x40, "rgui": 0x80}
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
             "menu": 0x65})
for i in range(12):
    KEYS[f"f{i + 1}"] = 0x3A + i
for i in range(12):
    KEYS[f"f{i + 13}"] = 0x68 + i
CONSUMER = {"play": 0xCD, "next": 0xB5, "prev": 0xB6, "stop": 0xB7, "mute": 0xE2,
            "volup": 0xE9, "voldown": 0xEA, "brightup": 0x6F, "brightdown": 0x70}
KEYS_REV = {v: k for k, v in KEYS.items()}
CONS_REV = {v: k for k, v in CONSUMER.items()}


def parse_action(s):
    s = s.strip().lower()
    if s in ("none", "disabled"):
        return (0x13, 0, 0, 0)
    if s.startswith("media:"):
        u = CONSUMER[s[6:]]
        return (0x30, u & 0xFF, u >> 8, 0)
    if s.startswith("macro:"):
        return (0x60, int(s[6:]), 1, 0)
    if s.startswith("mouse:"):
        m = {"left": (1, 0), "right": (2, 0), "middle": (4, 0), "wheelup": (0, 1),
             "wheeldown": (0, 0xFF)}[s[6:]]
        return (0x10, m[0], 0, m[1])
    mods, key = 0, 0
    for part in s.split("+"):
        if part in MODS:
            mods |= MODS[part]
        elif part in KEYS:
            key = KEYS[part]
        else:
            sys.exit(f"Unknown key '{part}'")
    return (0x20, mods, key, 0)


def describe(e):
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
        return f"mouse buttons={a:02X} wheel={c if c < 128 else c - 256}"
    return f"type {t:02X}: {a:02X} {b:02X} {c:02X}"


def label(i):
    if i < 16:
        return f"key {i}"
    d, k = divmod(i - 16, 3)
    return f"dial {d + 1} {['press', 'clockwise', 'anticlockwise'][k]}"


# ---------------------------------------------------------------- CLI
LIGHT_MODES = ["off", "solid", "breathing", "press", "tide", "perkey"]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("cmd", choices=["info", "keys", "set", "disable", "profile", "light", "colour", "raw"])
    ap.add_argument("args", nargs="*")
    ap.add_argument("--profile", type=int)
    ap.add_argument("--colour")
    ap.add_argument("--brightness", type=int)
    a = ap.parse_args()
    pad = Pad()

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
