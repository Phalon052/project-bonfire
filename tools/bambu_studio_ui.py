#!/usr/bin/env python3
"""
Project Bonfire — press Bambu Studio's own Stop button, from a script.

The P1S firmware refuses unsigned stop and pause commands (err 84033543), so
the only way to stop a print from this PC is to press the button in an app the
printer trusts. This drives Bambu Studio's window: it finds the button by
matching a small picture of it, moves the real mouse there and clicks, then
checks the printer actually stopped.

It is deliberately dumb and careful. It only ever clicks buttons you pointed
at yourself during setup, it refuses if it can't see one clearly, and it says
what it did.

    python tools/bambu_studio_ui.py calibrate stop     # point at Studio's Stop button
    python tools/bambu_studio_ui.py calibrate confirm  # ...and the confirm button
    python tools/bambu_studio_ui.py test               # find the buttons, click nothing
    python tools/bambu_studio_ui.py stop               # really stop the print

Windows only. Needs: python -m pip install opencv-python numpy pillow
"""
import ctypes
import json
import os
import sys
import time

_HERE = os.path.dirname(os.path.abspath(__file__))
UI_DIR = os.path.join(_HERE, "studio_ui")
BUTTONS = {"stop": "Studio's Stop button, on the Device tab while a print is running",
           "confirm": "the button that confirms it (Yes / Confirm / Stop)"}
MATCH_MIN = 0.80              # below this, we don't believe we found the button
GRAB_PAD = 26                 # how much around the pointer is saved as the button
WINDOW_HINTS = ("bambu studio", "bambu-studio")


class UiError(Exception):
    """Something about driving Studio, in words worth showing."""


def _need_windows():
    if os.name != "nt":
        raise UiError("Driving Bambu Studio only works on the Windows PC it runs on.")


def _cv():
    try:
        import cv2
        import numpy
        from PIL import ImageGrab
    except ImportError:
        raise UiError("This needs OpenCV and Pillow: run "
                      "`python -m pip install opencv-python numpy pillow`.")
    return cv2, numpy, ImageGrab


# ── the Studio window ────────────────────────────────────────────────

def find_window(hints=WINDOW_HINTS):
    """(hwnd, title) of Bambu Studio's main window, or raise."""
    _need_windows()
    user32 = ctypes.windll.user32
    found = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
    def each(hwnd, _):
        if not user32.IsWindowVisible(hwnd):
            return True
        n = user32.GetWindowTextLengthW(hwnd)
        if n:
            buf = ctypes.create_unicode_buffer(n + 1)
            user32.GetWindowTextW(hwnd, buf, n + 1)
            title = buf.value
            if any(h in title.lower() for h in hints):
                found.append((hwnd, title))
        return True

    user32.EnumWindows(each, None)
    if not found:
        raise UiError("Bambu Studio isn't open on this PC, so its Stop button can't "
                      "be pressed. Stop the print in Studio, Handy or on the screen.")
    found.sort(key=lambda w: len(w[1]), reverse=True)
    return found[0]


def window_box(hwnd):
    import ctypes.wintypes as wt
    rect = wt.RECT()
    ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(rect))
    return (rect.left, rect.top, rect.right, rect.bottom)


def raise_window(hwnd):
    user32 = ctypes.windll.user32
    user32.ShowWindow(hwnd, 9)            # SW_RESTORE
    user32.SetForegroundWindow(hwnd)
    time.sleep(0.6)


def grab(box):
    cv2, np, ImageGrab = _cv()
    img = ImageGrab.grab(bbox=box, all_screens=True)
    return cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)


# ── the buttons you pointed at ───────────────────────────────────────

def button_path(name):
    return os.path.join(UI_DIR, "%s_button.png" % name)


def calibrate(name, countdown=6, _grab=None, _cursor=None):
    """
    Save a little picture of one button. Point the mouse at it and wait —
    whatever is under the pointer when the countdown ends is the button.
    """
    if name not in BUTTONS:
        raise UiError("Buttons to point at: %s." % ", ".join(BUTTONS))
    _need_windows() if _grab is None else None
    hwnd, title = (None, "") if _grab else find_window()
    if hwnd:
        raise_window(hwnd)
    print("Point the mouse at %s and hold still." % BUTTONS[name])
    for left in range(countdown, 0, -1):
        print("  %d..." % left, end="\r", flush=True)
        time.sleep(1)
    x, y = (_cursor or _cursor_pos)()
    box = (x - 3 * GRAB_PAD, y - GRAB_PAD, x + 3 * GRAB_PAD, y + GRAB_PAD)
    shot = (_grab or grab)(box)
    os.makedirs(UI_DIR, exist_ok=True)
    cv2, _np, _ = _cv()
    cv2.imwrite(button_path(name), shot)
    meta_write(name, {"saved_at": time.strftime("%Y-%m-%d %H:%M:%S"), "window": title,
                      "pointer": [x, y], "size": [box[2] - box[0], box[3] - box[1]]})
    return {"ok": True, "file": button_path(name), "at": [x, y],
            "note": "Check %s looks like the button and nothing else." % button_path(name)}


def _cursor_pos():
    import ctypes.wintypes as wt
    pt = wt.POINT()
    ctypes.windll.user32.GetCursorPos(ctypes.byref(pt))
    return pt.x, pt.y


def meta_write(name, data):
    os.makedirs(UI_DIR, exist_ok=True)
    path = os.path.join(UI_DIR, "buttons.json")
    try:
        with open(path, encoding="utf-8") as fh:
            doc = json.load(fh)
    except (OSError, ValueError):
        doc = {}
    doc[name] = data
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, indent=2)


def locate(name, screen=None, box=None, _read=None):
    """
    Where the button is on screen, as (x, y, score). Raises if it isn't there
    or isn't clear enough.
    """
    cv2, np, _ = _cv()
    path = button_path(name)
    template = (_read or cv2.imread)(path)
    if template is None:
        raise UiError("No picture of %s yet. Run "
                      "`python tools/bambu_studio_ui.py calibrate %s` once." % (name, name))
    if screen is None:
        hwnd, _title = find_window()
        box = window_box(hwnd)
        screen = grab(box)
    if (screen.shape[0] < template.shape[0]) or (screen.shape[1] < template.shape[1]):
        raise UiError("Studio's window is smaller than the saved %s button — is it "
                      "minimised?" % name)
    if float(np.asarray(template, np.float32).std()) < 5.0:
        raise UiError("The saved picture of %s is nearly blank, so it would match "
                      "anywhere. Calibrate it again with the pointer on the button."
                      % name)
    res = cv2.matchTemplate(screen, template, cv2.TM_CCOEFF_NORMED)
    _minv, score, _minl, loc = cv2.minMaxLoc(res)
    if not np.isfinite(score) or score < MATCH_MIN:
        raise UiError("Couldn't find %s in Studio's window (best match %.0f%%). Is the "
                      "Device tab open with the print running? If Studio's look changed, "
                      "calibrate it again." % (name, score * 100))
    near = np.abs(np.indices(res.shape)[0] - loc[1]) + np.abs(np.indices(res.shape)[1] - loc[0])
    others = res[(near > max(template.shape[:2]) // 2) & np.isfinite(res)]
    if others.size and float(others.max()) > score - 0.03:
        raise UiError("Found more than one thing in Studio's window that looks like "
                      "%s, so nothing was clicked. Calibrate it again on a part of the "
                      "button that is unlike anything else on screen." % name)
    x = (box[0] if box else 0) + loc[0] + template.shape[1] // 2
    y = (box[1] if box else 0) + loc[1] + template.shape[0] // 2
    return int(x), int(y), float(score)


# ── clicking ─────────────────────────────────────────────────────────

def click(x, y):
    _need_windows()
    user32 = ctypes.windll.user32
    user32.SetCursorPos(int(x), int(y))
    time.sleep(0.15)
    user32.mouse_event(0x0002, 0, 0, 0, 0)        # left down
    time.sleep(0.05)
    user32.mouse_event(0x0004, 0, 0, 0, 0)        # left up
    time.sleep(0.4)


def test():
    """Find the window and both buttons, click nothing."""
    hwnd, title = find_window()
    raise_window(hwnd)
    box = window_box(hwnd)
    screen = grab(box)
    out = {"ok": True, "window": title, "box": list(box), "buttons": {}}
    for name in BUTTONS:
        try:
            x, y, score = locate(name, screen, box)
            out["buttons"][name] = {"at": [x, y], "match": round(score, 3)}
        except UiError as exc:
            out["ok"] = False
            out["buttons"][name] = {"error": str(exc)}
    return out


def stop(confirm=True, verify=True, _status=None):
    """
    Press Stop in Studio, then the confirmation, then check the printer stopped.
    Returns {"ok", "clicked", "state", "note"}.
    """
    hwnd, title = find_window()
    raise_window(hwnd)
    box = window_box(hwnd)
    x, y, score = locate("stop", grab(box), box)
    click(x, y)
    clicked = ["stop"]
    if confirm:
        time.sleep(0.8)
        try:
            cx, cy, _ = locate("confirm", grab(window_box(hwnd)), window_box(hwnd))
            click(cx, cy)
            clicked.append("confirm")
        except UiError as exc:
            return {"ok": False, "clicked": clicked, "note":
                    "Pressed Stop, but couldn't find the confirmation (%s). Finish it "
                    "in Studio." % exc}
    if not verify:
        return {"ok": True, "clicked": clicked, "match": round(score, 3), "window": title}
    status_fn = _status
    if status_fn is None:
        import runpy
        status_fn = runpy.run_path(os.path.join(_HERE, "bambu_cloud.py"))["printer_status"]
    state = ""
    for _ in range(6):
        time.sleep(5)
        try:
            state = (status_fn() or {}).get("state", "")
        except Exception as exc:
            state = "unknown (%s)" % exc
            break
        if state not in ("printing", "preparing"):
            return {"ok": True, "clicked": clicked, "state": state,
                    "note": "The printer reports %s." % state}
    return {"ok": False, "clicked": clicked, "state": state,
            "note": "Clicked Stop but the printer still says %s. Stop it by hand." % state}


def _cli(argv):
    try:
        cmd = argv[1] if len(argv) > 1 else ""
        if cmd == "calibrate" and len(argv) > 2:
            print(json.dumps(calibrate(argv[2]), indent=2))
            return 0
        if cmd == "test":
            print(json.dumps(test(), indent=2))
            return 0
        if cmd == "stop":
            print(json.dumps(stop(), indent=2))
            return 0
    except UiError as exc:
        print("Couldn't: %s" % exc)
        return 1
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(_cli(sys.argv))
