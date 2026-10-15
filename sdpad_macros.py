"""sdpad_macros.py - turns the pad's raw macro events into human-friendly steps and back.

Raw event (as stored on the pad): (delay_ms, is_down, kind, code)
    kind 2 = keyboard usage, kind 3 = mouse button mask, others kept as-is ("raw" steps)

Step dicts:
    {"t": "text",  "text": "hello", "gap": 10}
    {"t": "press", "mods": ["ctrl"], "key": "c", "gap": 10}     # chord: press + release
    {"t": "wait",  "ms": 500}
    {"t": "down",  "key": "lshift", "gap": 10}                   # hold a key down
    {"t": "up",    "key": "lshift", "gap": 10}                   # release a key
    {"t": "mouse", "btn": 1, "gap": 10}                          # click (1 left, 2 right, 4 middle)
    {"t": "raw",   "ev": (delay, down, kind, code)}              # anything we don't understand, kept intact
"""
from sdpad import KEYS, KEYS_REV

DEFAULT_GAP = 10          # ms between keystrokes for newly created steps
WAIT_THRESHOLD = 50       # a leading delay larger than this is shown as an explicit "Wait"
MOD_ORDER = ["ctrl", "shift", "alt", "gui"]
MOD_USAGE = {"ctrl": 0xE0, "shift": 0xE1, "alt": 0xE2, "gui": 0xE3}
MOD_NAMES = {0xE0: "lctrl", 0xE1: "lshift", 0xE2: "lalt", 0xE3: "lgui",
             0xE4: "rctrl", 0xE5: "rshift", 0xE6: "ralt", 0xE7: "rgui"}
MOD_NAMES_REV = {v: k for k, v in MOD_NAMES.items()}
MOUSE_NAMES = {1: "left", 2: "right", 4: "middle"}

# ---- characters <-> keys
_UNSHIFTED = {c: c for c in "abcdefghijklmnopqrstuvwxyz0123456789-=[]\\;'`,./"}
_UNSHIFTED.update({" ": "space", "\n": "enter", "\t": "tab"})
_SHIFTED = {c.upper(): c for c in "abcdefghijklmnopqrstuvwxyz"}
_SHIFTED.update(dict(zip("!@#$%^&*()", "1234567890")))
_SHIFTED.update(dict(zip('_+{}|:"~<>?', "-=[]\\;'`,./")))
CHAR_TO_KEY = {c: (False, k) for c, k in _UNSHIFTED.items()}
CHAR_TO_KEY.update({c: (True, k) for c, k in _SHIFTED.items()})
KEY_TO_CHAR = {v: c for c, v in CHAR_TO_KEY.items()}


KEYPAD = {0x54: "kp/", 0x55: "kp*", 0x56: "kp-", 0x57: "kp+", 0x58: "kpenter", 0x63: "kp.", 0x62: "kp0"}
KEYPAD.update({0x59 + i: f"kp{i + 1}" for i in range(9)})
KEYPAD_REV = {v: k for k, v in KEYPAD.items()}
ALL_KEY_NAMES = sorted(KEYS) + sorted(KEYPAD_REV)


def usage_to_name(code):
    return MOD_NAMES.get(code) or KEYPAD.get(code) or KEYS_REV.get(code) or f"usage:{code:02x}"


def name_to_usage(name):
    n = name.lower()
    if n in MOD_NAMES_REV:
        return MOD_NAMES_REV[n]
    if n in MOD_USAGE:
        return MOD_USAGE[n]
    if n in KEYS:
        return KEYS[n]
    if n in KEYPAD_REV:
        return KEYPAD_REV[n]
    if n.startswith("usage:"):
        return int(n[6:], 16)
    raise ValueError(f"Unknown key '{name}'")


def pretty_key(name):
    special = {"lctrl": "Left Ctrl", "rctrl": "Right Ctrl", "lshift": "Left Shift", "rshift": "Right Shift",
               "lalt": "Left Alt", "ralt": "Right Alt", "lgui": "Left Win", "rgui": "Right Win",
               "ctrl": "Ctrl", "shift": "Shift", "alt": "Alt", "gui": "Win", "enter": "Enter", "esc": "Esc",
               "pageup": "Page Up", "pagedown": "Page Down", "printscreen": "Print Screen",
               "capslock": "Caps Lock", "numlock": "Num Lock", "scrolllock": "Scroll Lock"}
    if name in special:
        return special[name]
    if name.startswith("kp"):
        return "Numpad " + ("Enter" if name == "kpenter" else name[2:])
    return name.upper() if len(name) == 1 else name.capitalize()


def can_type(text):
    return [c for c in text if c not in CHAR_TO_KEY]


# ---- events <-> bytes
def events_from_bytes(b):
    ev = []
    for i in range(0, len(b) - 3, 4):
        dl, dh, flags, code = b[i:i + 4]
        ev.append((dl | dh << 8, bool(flags & 0x40), flags & 7, code))
        if flags & 0x80:
            break
    return ev


def events_to_bytes(ev):
    out = bytearray()
    for n, (delay, down, kind, code) in enumerate(ev):
        delay = max(0, min(65535, int(delay)))
        flags = kind | (0x40 if down else 0) | (0x80 if n == len(ev) - 1 else 0)
        out += bytes([delay & 0xFF, delay >> 8, flags, code])
    return bytes(out)


def read_macro_events(table):
    """-> {slot: [events]} for every populated slot of a 4096-byte macro table."""
    res = {}
    for slot in range(32):
        start = table[2 * slot] | table[2 * slot + 1] << 8
        if 64 <= start < len(table) - 3:
            res[slot] = events_from_bytes(table[start:])
    return res


def build_table(slot_events):
    """{slot: [events]} -> 4096-byte table (empty slots 0xFFFF)."""
    table = bytearray(4096)
    table[0:64] = b"\xff" * 64
    off = 64
    for slot, ev in sorted(slot_events.items()):
        if not ev:
            continue
        data = events_to_bytes(ev)
        if off + len(data) > 4096:
            raise ValueError("Macro memory is full")
        table[2 * slot] = off & 0xFF
        table[2 * slot + 1] = off >> 8
        table[off:off + len(data)] = data
        off += len(data)
    return bytes(table)


# ---- steps -> events
def compile_steps(steps):
    ev = []
    pending = 0

    def add(down, kind, code, delay):
        nonlocal pending
        ev.append((delay + pending, down, kind, code))
        pending = 0

    for s in steps:
        t = s["t"]
        g = s.get("gap", DEFAULT_GAP)
        if t == "wait":
            pending += int(s["ms"])
        elif t == "raw":
            d, down, kind, code = s["ev"]
            add(down, kind, code, d)
        elif t == "down":
            add(True, 2, name_to_usage(s["key"]), g)
        elif t == "up":
            add(False, 2, name_to_usage(s["key"]), g)
        elif t == "keys":
            for k in s["keys"]:
                add(True, 2, name_to_usage(k), g)
                add(False, 2, name_to_usage(k), g)
        elif t == "mouse":
            add(True, 3, s["btn"], g)
            add(False, 3, s["btn"], g)
        elif t == "press":
            mods = [MOD_USAGE[m] for m in MOD_ORDER if m in s["mods"]]
            key = name_to_usage(s["key"])
            for m in mods:
                add(True, 2, m, g)
            add(True, 2, key, g)
            add(False, 2, key, g)
            for m in reversed(mods):
                add(False, 2, m, g)
        elif t == "text":
            for ch in s["text"]:
                shift, key = CHAR_TO_KEY[ch]
                k = KEYS[key]
                if shift:
                    add(True, 2, MOD_USAGE["shift"], g)
                add(True, 2, k, g)
                add(False, 2, k, g)
                if shift:
                    add(False, 2, MOD_USAGE["shift"], g)
    if pending:
        raise ValueError("A macro can't end with a Wait - add an action after it, or delete the Wait")
    return ev


# ---- events -> steps
def _chord(ev, i):
    """Try to read a press-and-release chord starting at i. -> (mods, key, gap, first_delay, next_i) or None"""
    n = len(ev)

    def is_down(j):
        return j < n and ev[j][1] and ev[j][2] == 2

    j, mods = i, []
    while is_down(j) and 0xE0 <= ev[j][3] <= 0xE3:
        mods.append(ev[j][3])
        j += 1
    key = None
    if is_down(j) and not 0xE0 <= ev[j][3] <= 0xE7:
        key = ev[j][3]
        j += 1
    elif mods:
        key = mods.pop()      # the last "modifier" is the key itself
    else:
        return None
    if len(set(mods)) != len(mods) or key in mods:
        return None
    need = set(mods) | {key}
    ups = ev[j:j + len(need)]
    if len(ups) != len(need) or any(u[1] or u[2] != 2 for u in ups) or {u[3] for u in ups} != need:
        return None
    end = j + len(need)
    inner = {e[0] for e in ev[i + 1:end]}
    if len(inner) > 1:
        return None
    gap = inner.pop() if inner else min(ev[i][0], WAIT_THRESHOLD)
    if gap > WAIT_THRESHOLD:
        return None          # a long hold is not a quick press
    return mods, key, gap, ev[i][0], end


def _decompile_strict(ev):
    steps = []
    i, n = 0, len(ev)

    def lead_wait(first_delay, gap):
        if first_delay > WAIT_THRESHOLD and first_delay > gap:
            steps.append({"t": "wait", "ms": first_delay - gap})

    while i < n:
        d, down, kind, code = ev[i]
        if kind == 2 and down:
            c = _chord(ev, i)
            if c:
                mods, key, gap, first, nxt = c
                lead_wait(first, gap)
                name = usage_to_name(key)
                ok_mods = all(m == MOD_USAGE["shift"] for m in mods)
                shifted = bool(mods)
                ch = KEY_TO_CHAR.get((shifted, name)) if ok_mods else None
                if ch is not None:
                    if steps and steps[-1]["t"] == "text" and steps[-1]["gap"] == gap:
                        steps[-1]["text"] += ch
                    else:
                        steps.append({"t": "text", "text": ch, "gap": gap})
                else:
                    steps.append({"t": "press", "mods": [m for m in MOD_ORDER if MOD_USAGE[m] in mods],
                                  "key": name, "gap": gap})
                i = nxt
                continue
        if kind == 3 and down and i + 1 < n and ev[i + 1][2] == 3 and not ev[i + 1][1] \
                and ev[i + 1][3] == code and ev[i + 1][0] == (d if d <= WAIT_THRESHOLD else ev[i + 1][0]) \
                and code in MOUSE_NAMES:
            gap = ev[i + 1][0]
            lead_wait(d, gap)
            steps.append({"t": "mouse", "btn": code, "gap": gap})
            i += 2
            continue
        if kind == 2:
            gap = d if d <= WAIT_THRESHOLD else DEFAULT_GAP
            lead_wait(d, gap)
            steps.append({"t": "down" if down else "up", "key": usage_to_name(code), "gap": gap})
        else:
            steps.append({"t": "raw", "ev": (d, down, kind, code)})
        i += 1
    return steps


def describe_step(s):
    t = s["t"]
    if t == "text":
        shown = s["text"].replace("\n", "⏎").replace("\t", "⇥")
        return f"Type  “{shown}”"
    if t == "press":
        return "Press  " + " + ".join([pretty_key(m) for m in s["mods"]] + [pretty_key(s["key"])])
    if t == "keys":
        return "Press  " + ", ".join(pretty_key(k) for k in s["keys"])
    if t == "wait":
        ms = s["ms"]
        return f"Wait  {ms / 1000:g} s" if ms >= 1000 else f"Wait  {ms} ms"
    if t == "down":
        return f"Hold down  {pretty_key(s['key'])}"
    if t == "up":
        return f"Release  {pretty_key(s['key'])}"
    if t == "mouse":
        return f"Click  {MOUSE_NAMES.get(s['btn'], s['btn'])} mouse button"
    d, down, kind, code = s["ev"]
    return f"(advanced) event kind {kind} code {code:02X} {'down' if down else 'up'}"


def _decompile_clean(ev):
    """Understands overlapped typing (next key down before the last is released). None if it can't."""
    from collections import Counter
    small = [e[0] for e in ev if e[0] <= WAIT_THRESHOLD]
    gap = Counter(small).most_common(1)[0][0] if small else DEFAULT_GAP
    steps, mods, held = [], [], set()
    used = set()

    def maybe_wait(d):
        if d > WAIT_THRESHOLD and d > gap:
            steps.append({"t": "wait", "ms": d - gap})

    for d, down, kind, code in ev:
        if kind != 2:
            return None
        is_mod = 0xE0 <= code <= 0xE7
        if is_mod:
            if down:
                if code in mods:
                    return None
                maybe_wait(d)
                mods.append(code)
            else:
                if d > WAIT_THRESHOLD or code not in mods:
                    return None
                mods.remove(code)
                if code not in used:
                    steps.append({"t": "press", "mods": [], "key": usage_to_name(code), "gap": gap})
                used.discard(code)
        elif down:
            if code in held or any(m > 0xE3 for m in mods):
                return None
            maybe_wait(d)
            held.add(code)
            used.update(mods)
            name = usage_to_name(code)
            shifted = MOD_USAGE["shift"] in mods
            others = [m for m in mods if m != MOD_USAGE["shift"]]
            ch = KEY_TO_CHAR.get((shifted, name)) if not others else None
            if ch is not None:
                if steps and steps[-1]["t"] == "text" and steps[-1]["gap"] == gap:
                    steps[-1]["text"] += ch
                else:
                    steps.append({"t": "text", "text": ch, "gap": gap})
            else:
                steps.append({"t": "press", "mods": [m for m in MOD_ORDER if MOD_USAGE[m] in mods],
                              "key": name, "gap": gap})
        else:
            if d > WAIT_THRESHOLD or code not in held:
                return None
            held.discard(code)
    if mods or held:
        return None
    # tidy: a lone Enter/Tab is a key press, not "text"; runs of plain key presses become one step
    out = []
    for st in steps:
        if st["t"] == "text" and st["text"] in ("\n", "\t"):
            st = {"t": "press", "mods": [], "key": CHAR_TO_KEY[st["text"]][1], "gap": st["gap"]}
        if st["t"] == "press" and not st["mods"] and out:
            prev = out[-1]
            if prev["t"] == "keys" and prev["gap"] == st["gap"]:
                prev["keys"].append(st["key"])
                continue
            if prev["t"] == "press" and not prev["mods"] and prev["gap"] == st["gap"]:
                out[-1] = {"t": "keys", "keys": [prev["key"], st["key"]], "gap": st["gap"]}
                continue
        out.append(st)
    return out


def decompile(ev):
    return _decompile_clean(ev) or _decompile_strict(ev)
