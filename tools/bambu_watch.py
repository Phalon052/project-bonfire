#!/usr/bin/env python3
"""
Project Bonfire — print watch: a picture every few minutes while the P1S is
printing, judged by Claude, and a pop-up on this PC when something looks wrong.

    python tools/bambu_watch.py once        # one check right now, printed
    python tools/bambu_watch.py run         # keep watching (what start-up runs)
    python tools/bambu_watch.py install     # start with Windows, hidden
    python tools/bambu_watch.py uninstall
    python tools/bambu_watch.py status      # is it installed / running, last checks

How it runs: asleep while the printer is idle — a status check over Bambu
Cloud every `idle_poll_min` (cheap, no picture, no Claude). While it prints:
a camera picture every `interval_min`, sent with the one before it to a small
Claude model that answers OK / problem. On a problem it:

  1. tries to pause the print. The P1S firmware (2025+) refuses pause from
     anything but Bambu's own apps, so this is expected to fail — it's tried
     in case a firmware or Developer Mode change lets it through;
  2. pops up a window on this PC with what it saw — "Yes" opens the picture and
     Bambu Studio, where the Device tab can pause or stop the print;
  3. keeps the picture in tools/camera_snapshots/problems/.

Needs: ANTHROPIC_API_KEY in .env (the Claude API, billed separately from the
Claude app — about a tenth of a cent per check with Haiku), the Bambu Cloud
sign-in (tools/bambu_cloud.py login) and the camera on the home network.
Settings live under "camera_watch" in tools/bambu_config.json.
"""
import base64
import datetime
import json
import os
import runpy
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request

_HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(_HERE)
CONFIG_PATH = os.path.join(_HERE, "bambu_config.json")
SNAP_DIR = os.path.join(_HERE, "camera_snapshots")
PROBLEM_DIR = os.path.join(SNAP_DIR, "problems")
LOG_PATH = os.path.join(SNAP_DIR, "watch.log")
LOCK_PATH = os.path.join(SNAP_DIR, "watch.lock")
STARTUP_NAME = "Bonfire print watch.vbs"
API_URL = "https://api.anthropic.com/v1/messages"

DEFAULTS = {
    "enabled": True,
    "interval_min": 7,          # between pictures while printing (5-10 asked for)
    "idle_poll_min": 3,         # between status checks while idle
    "model": "claude-haiku-4-5",
    "act_on": 0.5,              # confidence at or above which a problem is acted on
    "try_pause": True,
    "popup": True,
    "skip_first_layers": 1,     # layer 1 is mostly the raft/brim going down
}

ACTIVE = ("printing", "preparing")

PROMPT = """You are checking a 3D print on a Bambu Lab P1S from its chamber camera.
Job: {job}. Progress: {progress}% (layer {layer} of {total}).
{compare}
Look for: spaghetti or loose strands; a part knocked over, loose or moved off
its spot; a layer shift; a big blob on the nozzle or part; nothing being
extruded (clog); the part lifting off the bed (warping); anything on the bed
that shouldn't be. The camera looks down from the front-left; the toolhead and
its cables are normal. Dark or blurry pictures are not a print problem.

Answer with JSON only, no other text:
{{"verdict": "ok" | "problem" | "unsure", "problem": "<short, plain words, empty if ok>",
  "confidence": <0.0-1.0 that there is a real problem>}}"""


# ── settings, log ────────────────────────────────────────────────────

def settings():
    try:
        with open(CONFIG_PATH, encoding="utf-8") as fh:
            cfg = json.load(fh).get("camera_watch") or {}
    except (OSError, ValueError):
        cfg = {}
    out = dict(DEFAULTS)
    out.update({k: v for k, v in cfg.items() if k in DEFAULTS})
    return out


def log(message):
    os.makedirs(SNAP_DIR, exist_ok=True)
    line = "%s  %s" % (datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), message)
    try:
        with open(LOG_PATH, "a", encoding="utf-8") as fh:
            fh.write(line + "\n")
        # keep the log short
        if os.path.getsize(LOG_PATH) > 400_000:
            with open(LOG_PATH, encoding="utf-8") as fh:
                tail = fh.readlines()[-2000:]
            with open(LOG_PATH, "w", encoding="utf-8") as fh:
                fh.writelines(tail)
    except OSError:
        pass
    if sys.stdout and not str(sys.executable).lower().endswith("pythonw.exe"):
        try:
            print(line)
        except Exception:
            pass


def _mod(name):
    return runpy.run_path(os.path.join(_HERE, name))


def api_key():
    _mod("env.py")["load"]()
    return os.environ.get("ANTHROPIC_API_KEY", "").strip()


# ── judging a picture ────────────────────────────────────────────────

def _image_block(path):
    with open(path, "rb") as fh:
        data = base64.b64encode(fh.read()).decode("ascii")
    return {"type": "image",
            "source": {"type": "base64", "media_type": "image/jpeg", "data": data}}


def parse_verdict(text):
    """The model's JSON answer, forgiving of code fences or words around it."""
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        return {"verdict": "unsure", "problem": "unreadable answer: %s" % text[:120],
                "confidence": 0.0}
    try:
        v = json.loads(text[start:end + 1])
    except ValueError:
        return {"verdict": "unsure", "problem": "unreadable answer: %s" % text[:120],
                "confidence": 0.0}
    verdict = str(v.get("verdict", "unsure")).lower()
    if verdict not in ("ok", "problem", "unsure"):
        verdict = "unsure"
    try:
        conf = max(0.0, min(1.0, float(v.get("confidence", 0))))
    except (TypeError, ValueError):
        conf = 0.0
    return {"verdict": verdict, "problem": str(v.get("problem") or ""),
            "confidence": conf}


def judge(picture, status, previous=None, model=None, key=None, _post=None):
    """Ask Claude about one picture (and the one before, when there is one)."""
    key = key or api_key()
    if not key:
        raise RuntimeError("No ANTHROPIC_API_KEY in .env — the watch needs it to "
                           "look at pictures.")
    compare = ("The first image is from the previous check; the second is now. "
               "Compare them." if previous else "")
    content = ([_image_block(previous)] if previous else []) + [_image_block(picture)]
    content.append({"type": "text", "text": PROMPT.format(
        job=status.get("job") or "unknown", progress=status.get("progress_pct"),
        layer=status.get("layer"), total=status.get("total_layers"),
        compare=compare)})
    body = {"model": model or DEFAULTS["model"], "max_tokens": 300,
            "messages": [{"role": "user", "content": content}]}
    if _post:
        reply = _post(body)
    else:
        req = urllib.request.Request(
            API_URL, data=json.dumps(body).encode("utf-8"), method="POST",
            headers={"x-api-key": key, "anthropic-version": "2023-06-01",
                     "content-type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                reply = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")[:300]
            raise RuntimeError("Claude API said %s: %s" % (exc.code, detail))
    text = "".join(b.get("text", "") for b in reply.get("content", [])
                   if b.get("type") == "text")
    return parse_verdict(text)


# ── acting on a problem ──────────────────────────────────────────────

def popup(title, message, picture=None):
    """A pop-up on this PC that doesn't hold up the watch. "Yes" opens the
    picture and Bambu Studio."""
    if os.name != "nt":
        log("POP-UP (not Windows, so logged only): %s — %s" % (title, message))
        return

    def show():
        import ctypes
        MB_YESNO, MB_ICONWARNING, MB_TOPMOST, MB_SETFOREGROUND = 0x4, 0x30, 0x40000, 0x10000
        answer = ctypes.windll.user32.MessageBoxW(
            None, message + "\n\nOpen the picture and Bambu Studio?", title,
            MB_YESNO | MB_ICONWARNING | MB_TOPMOST | MB_SETFOREGROUND)
        if answer == 6:                                         # IDYES
            try:
                if picture:
                    os.startfile(picture)                       # noqa: pylint
                exe = _mod("bambu_slice.py")["find_studio"]("")
                if exe:
                    subprocess.Popen([exe])
            except Exception as exc:
                log("couldn't open the picture/Studio: %s" % exc)
    threading.Thread(target=show, daemon=False).start()


def act(verdict, status, picture, cfg):
    """Pause (if the printer allows it), pop up, keep the picture."""
    os.makedirs(PROBLEM_DIR, exist_ok=True)
    kept = os.path.join(PROBLEM_DIR, os.path.basename(picture))
    try:
        with open(picture, "rb") as src, open(kept, "wb") as dst:
            dst.write(src.read())
    except OSError:
        kept = picture
    paused = False
    pause_note = ""
    if cfg["try_pause"]:
        try:
            r = _mod("bambu_print.py")["pause"](retry=True)
            paused = bool(r.get("ok"))
            pause_note = "paused" if paused else (r.get("error") or "not paused")
        except Exception as exc:
            pause_note = "pause failed: %s" % exc
    log("PROBLEM (%.0f%%): %s — %s" % (verdict["confidence"] * 100,
                                        verdict["problem"], pause_note))
    if cfg["popup"]:
        what = verdict["problem"] or "something looks wrong"
        head = ("Print PAUSED — " if paused else "Print problem — ") + (status.get("job") or "")
        body = ("%s\n\n%s%% done, layer %s of %s. Claude's confidence: %.0f%%.\n\n%s"
                % (what, status.get("progress_pct"), status.get("layer"),
                   status.get("total_layers"), verdict["confidence"] * 100,
                   "The print is paused." if paused else
                   "It could NOT be paused from here (the printer only takes pause "
                   "from Bambu's apps). Pause or stop it in Bambu Studio's Device "
                   "tab, Handy, or on the printer's screen."))
        popup(head, body, kept)
    return {"paused": paused, "pause_note": pause_note, "kept": kept}


# ── one check, and the loop ──────────────────────────────────────────

def check_once(state=None, cfg=None, _status=None, _snapshot=None, _judge=None, _act=None):
    """
    One pass. Returns {"state", "checked", "verdict"?, "next_in_s"}.
    `state` carries the previous picture and the current job between passes.
    """
    cfg = cfg or settings()
    state = state if state is not None else {}
    status = (_status or _mod("bambu_cloud.py")["printer_status"])()
    printer_state = status.get("state")
    idle_wait = 60 * float(cfg["idle_poll_min"])
    if printer_state not in ACTIVE:
        if state.get("job"):
            log("print ended (%s): %s" % (printer_state, state.get("job")))
        state.clear()
        return {"state": printer_state, "checked": False, "next_in_s": idle_wait}

    job = status.get("job")
    if state.get("job") != job:
        log("print started: %s" % job)
        state.clear()
        state["job"] = job
    layer = status.get("layer") or 0
    if printer_state == "preparing" or layer <= int(cfg["skip_first_layers"]):
        return {"state": printer_state, "checked": False, "next_in_s": 60.0}

    shot = (_snapshot or _mod("bambu_camera.py")["snapshot"])()
    picture = shot["file"]
    verdict = (_judge or judge)(picture, status, state.get("previous"), cfg["model"])
    if verdict["verdict"] == "unsure" and not state.get("rechecked"):
        state["rechecked"] = True               # look again in a minute
        log("unsure (%s) — looking again in a minute" % verdict["problem"])
        return {"state": printer_state, "checked": True, "verdict": verdict,
                "next_in_s": 60.0}
    state.pop("rechecked", None)
    acted = None
    if verdict["verdict"] in ("problem", "unsure") and verdict["confidence"] >= float(cfg["act_on"]):
        acted = (_act or act)(verdict, status, picture, cfg)
        # one alert per problem: wait longer before the next look
        wait = max(60 * float(cfg["interval_min"]), 900.0)
    else:
        log("ok — layer %s/%s, %s%%%s" % (layer, status.get("total_layers"),
                                           status.get("progress_pct"),
                                           (" (%s)" % verdict["problem"]) if verdict["problem"] else ""))
        wait = 60 * float(cfg["interval_min"])
    state["previous"] = picture
    return {"state": printer_state, "checked": True, "verdict": verdict,
            "acted": acted, "next_in_s": wait}


def _already_running():
    try:
        with open(LOCK_PATH, encoding="utf-8") as fh:
            pid = int(fh.read().strip() or 0)
    except (OSError, ValueError):
        return False
    if pid == os.getpid() or pid <= 0:
        return False
    if os.name == "nt":
        out = subprocess.run(["tasklist", "/FI", "PID eq %d" % pid, "/NH"],
                             capture_output=True, text=True).stdout
        return str(pid) in out
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def run_forever():
    os.makedirs(SNAP_DIR, exist_ok=True)
    if _already_running():
        log("another watch is already running — this one stops")
        return 0
    with open(LOCK_PATH, "w", encoding="utf-8") as fh:
        fh.write(str(os.getpid()))
    log("watch started")
    state = {}
    while True:
        cfg = settings()
        if not cfg["enabled"]:
            time.sleep(300)
            continue
        try:
            r = check_once(state, cfg)
            wait = r["next_in_s"]
        except Exception as exc:                 # network blips, sign-in expiry...
            log("check failed: %s" % exc)
            wait = 120.0
        time.sleep(max(30.0, wait))


# ── start with Windows ───────────────────────────────────────────────

def _startup_path():
    return os.path.join(os.environ.get("APPDATA", ""), "Microsoft", "Windows",
                        "Start Menu", "Programs", "Startup", STARTUP_NAME)


def install():
    if os.name != "nt":
        return "Start-up install is for Windows. Run `python tools/bambu_watch.py run` instead."
    pyw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
    if not os.path.isfile(pyw):
        pyw = sys.executable
    script = os.path.abspath(__file__)
    vbs = ('Set s = CreateObject("WScript.Shell")\r\n'
           's.Run """%s"" ""%s"" run", 0, False\r\n' % (pyw, script))
    with open(_startup_path(), "w", encoding="utf-8") as fh:
        fh.write(vbs)
    subprocess.Popen([pyw, script, "run"], cwd=ROOT,
                     creationflags=getattr(subprocess, "DETACHED_PROCESS", 0))
    return ("Installed: the watch starts hidden with Windows (%s) and is running "
            "now. Log: %s" % (_startup_path(), LOG_PATH))


def uninstall():
    path = _startup_path()
    removed = False
    if os.path.isfile(path):
        os.remove(path)
        removed = True
    try:
        with open(LOCK_PATH, encoding="utf-8") as fh:
            pid = int(fh.read().strip() or 0)
        if pid and os.name == "nt":
            subprocess.run(["taskkill", "/PID", str(pid), "/F"], capture_output=True)
    except (OSError, ValueError):
        pass
    return ("Removed from start-up and stopped." if removed
            else "It wasn't set to start with Windows; any running watch was stopped.")


def status_report():
    lines = ["installed at start-up: %s" % ("yes" if os.path.isfile(_startup_path()) else "no"),
             "running now: %s" % ("yes" if _already_running() else "no"),
             "API key in .env: %s" % ("yes" if api_key() else "NO — add ANTHROPIC_API_KEY"),
             "settings: %s" % json.dumps(settings())]
    try:
        with open(LOG_PATH, encoding="utf-8") as fh:
            tail = fh.readlines()[-8:]
        lines.append("last log lines:")
        lines += ["  " + t.rstrip() for t in tail]
    except OSError:
        lines.append("no log yet")
    return "\n".join(lines)


def _cli(argv):
    cmd = argv[1] if len(argv) > 1 else ""
    if cmd == "run":
        return run_forever()
    if cmd == "once":
        try:
            r = check_once({})
        except Exception as exc:
            print("Couldn't: %s" % exc)
            return 1
        print(json.dumps({k: v for k, v in r.items() if k != "acted"}, indent=2))
        return 0
    if cmd == "install":
        print(install())
        return 0
    if cmd == "uninstall":
        print(uninstall())
        return 0
    if cmd == "status":
        print(status_report())
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(_cli(sys.argv))
