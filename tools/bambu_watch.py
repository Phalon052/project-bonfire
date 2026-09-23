#!/usr/bin/env python3
"""
Project Bonfire — print watch: a picture every few minutes while the P1S is
printing, judged by a failure detector, and a pop-up on this PC when
something looks wrong.

    python tools/bambu_watch.py once        # one check right now, printed
    python tools/bambu_watch.py run         # keep watching (what start-up runs)
    python tools/bambu_watch.py install     # start with Windows, hidden
    python tools/bambu_watch.py uninstall
    python tools/bambu_watch.py status      # installed / running / detector / last checks
    python tools/bambu_watch.py obico test  # score the newest snapshot
    python tools/bambu_watch.py obico up    # only for judge "obico_docker"
    python tools/bambu_watch.py obico down

The judge (`judge` in the settings):
  * "obico" (default) — Obico's open-source spaghetti detector, its model run
    right here with onnxruntime (tools/bambu_detect.py). Free, local, no key,
    no Docker. Each picture gets a failure score (the sum of its detections'
    confidence); a running average across pictures smooths out blips.
  * "obico_docker" — the same detector as Obico's own server, in Docker
    (tools/obico/docker-compose.yml), for PCs that can run Docker.
  * "claude" — a small Claude model through the Claude API (needs
    ANTHROPIC_API_KEY in .env, billed separately from the Claude app).

How it runs: asleep while the printer is idle — a status check over Bambu
Cloud every `idle_poll_min` (cheap, no picture). While it prints: a camera
picture every `interval_min`, judged as above. On a problem it:

  1. tries to pause the print. The P1S firmware (2025+) refuses pause from
     anything but Bambu's own apps, so this is expected to fail — it's tried
     in case a firmware or Developer Mode change lets it through;
  2. pops up a window on this PC with what it saw — "Yes" opens the picture and
     Bambu Studio, where the Device tab can pause or stop the print;
  3. keeps the picture in tools/camera_snapshots/problems/.

Needs: `python -m pip install onnxruntime numpy pillow` and
`python tools/bambu_detect.py setup` once (for "obico"), the Bambu Cloud sign-in
(tools/bambu_cloud.py login) and the camera on the home network. Settings live
under "camera_watch" in tools/bambu_config.json; the detector's address and
token in .env (OBICO_ML_URL, OBICO_ML_TOKEN).
"""
import base64
import datetime
import http.server
import json
import os
import runpy
import secrets
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

_HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(_HERE)
CONFIG_PATH = os.path.join(_HERE, "bambu_config.json")
SNAP_DIR = os.path.join(_HERE, "camera_snapshots")
PROBLEM_DIR = os.path.join(SNAP_DIR, "problems")
LOG_PATH = os.path.join(SNAP_DIR, "watch.log")
LOCK_PATH = os.path.join(SNAP_DIR, "watch.lock")
STATE_PATH = os.path.join(SNAP_DIR, "watch.state.json")   # last pass, for `status`
STARTUP_NAME = "Bonfire print watch.vbs"
API_URL = "https://api.anthropic.com/v1/messages"
OBICO_DIR = os.path.join(_HERE, "obico")
OBICO_COMPOSE = os.path.join(OBICO_DIR, "docker-compose.yml")
OBICO_DEFAULT_URL = "http://127.0.0.1:3333"

DEFAULTS = {
    "enabled": True,
    "judge": "obico",           # obico (local model) | obico_docker | claude (API)
    "interval_min": 8,          # fallback cadence when a project sets no mode
    "idle_poll_min": 3,         # between status checks while idle
    "model": "claude-haiku-4-5",
    "act_on": 0.5,              # confidence at or above which a problem is acted on
    "try_pause": True,
    "popup": True,
    # Pictures start once set-up is over (bed heating, nozzle cleaning, bed
    # levelling...: the printer's own stage says so), then every interval_min.
    "skip_first_layers": 0,
    # obico: a picture's score is the sum of its detections' confidence (as in
    # Obico's own server). Act when the running average reaches alert_score,
    # or one picture reaches spike_score (re-checked a minute later first).
    "alert_score": 0.45,
    "spike_score": 0.78,
    "smoothing": 0.5,           # weight of the newest picture in the average
    # where the detector container fetches pictures from this PC
    "serve_host": "host.docker.internal",
    "serve_bind": "127.0.0.1",
    # Stopping: the firmware refuses stop/pause from here, so the only way is
    # to press the button in Bambu Studio (tools/bambu_studio_ui.py, calibrated
    # once). Modes that act first use it; the others ask first.
    "stop_via_studio": True,
}

REVIEW_DIR = os.path.join(SNAP_DIR, "review")

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


# ── the local detector (Obico ML API in Docker) ──────────────────────

def obico_config():
    """Detector address and token, from .env (defaults: this PC, no token)."""
    _mod("env.py")["load"]()
    return {"url": (os.environ.get("OBICO_ML_URL") or OBICO_DEFAULT_URL).rstrip("/"),
            "token": os.environ.get("OBICO_ML_TOKEN", "").strip()}


def obico_health(timeout=5):
    """True when the detector answers its health check."""
    try:
        with urllib.request.urlopen(obico_config()["url"] + "/hc/", timeout=timeout) as r:
            return r.status == 200
    except Exception:
        return False


class _OnePicture(http.server.BaseHTTPRequestHandler):
    """Serves one picture at one unguessable path, and nothing else."""
    picture = None
    path_token = None

    def do_GET(self):
        if self.path.split("?")[0] != "/" + self.path_token + ".jpg":
            self.send_error(404)
            return
        with open(self.picture, "rb") as fh:
            data = fh.read()
        self.send_response(200)
        self.send_header("Content-Type", "image/jpeg")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *a):
        pass


def obico_detect(picture, cfg=None, _get=None):
    """
    Obico's detections for one picture: [[label, confidence, [x, y, w, h]]...].
    The detector only takes a picture by URL, so the picture is served from
    this PC for the few seconds it takes, at a random one-time path.
    """
    cfg = cfg or settings()
    oc = obico_config()
    if _get:
        return _get(picture)
    token = secrets.token_urlsafe(16)
    handler = type("H", (_OnePicture,), {"picture": picture, "path_token": token})
    server = http.server.ThreadingHTTPServer((cfg["serve_bind"], 0), handler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        img_url = "http://%s:%d/%s.jpg" % (cfg["serve_host"], port, token)
        req = urllib.request.Request(oc["url"] + "/p/?img=" + urllib.parse.quote(img_url, safe=""))
        if oc["token"]:
            req.add_header("Authorization", "Bearer " + oc["token"])
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                reply = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            if exc.code == 401:
                raise RuntimeError("The detector refused the token — OBICO_ML_TOKEN in "
                                   ".env must match the one it was started with "
                                   "(`python tools/bambu_watch.py obico up` again).")
            raise RuntimeError("The detector said %s." % exc.code)
        except urllib.error.URLError as exc:
            raise RuntimeError("The detector isn't answering at %s (%s). Is Docker "
                               "Desktop running? `python tools/bambu_watch.py obico up`"
                               % (oc["url"], exc.reason))
    finally:
        server.shutdown()
        server.server_close()
    if reply.get("message") and not reply.get("detections"):
        raise RuntimeError("The detector couldn't read the picture: %s. If it couldn't "
                           "fetch it from this PC, set camera_watch.serve_bind to "
                           "\"0.0.0.0\" in tools/bambu_config.json (the picture is "
                           "still only served at a random one-time address)."
                           % reply["message"])
    return reply.get("detections") or []


def local_detect(picture):
    """Obico's model run right here (tools/bambu_detect.py) — no Docker."""
    det = _mod("bambu_detect.py")
    try:
        return det["detect"](picture)
    except det["DetectorError"] as exc:
        raise RuntimeError(str(exc))


def detector_ready():
    """(ready, why not) for the judge in use."""
    cfg = settings()
    if cfg["judge"] == "claude":
        return (bool(api_key()), "no ANTHROPIC_API_KEY in .env")
    if cfg["judge"] == "obico_docker":
        return (obico_health(), "the Docker detector isn't answering at %s"
                % obico_config()["url"])
    det = _mod("bambu_detect.py")
    try:
        for m in ("onnxruntime", "numpy", "PIL"):
            __import__(m)
    except ImportError:
        return (False, "run `python -m pip install onnxruntime numpy pillow`")
    if not os.path.isfile(det["MODEL_PATH"]):
        return (False, "run `python tools/bambu_detect.py setup` to download the model")
    return (True, "")


def obico_score(detections):
    """A picture's failure score, as Obico's server counts it: the sum of the
    detections' confidence."""
    return round(sum(float(d[1]) for d in detections if len(d) > 1), 3)


def judge_obico(picture, state, cfg, _detect=None):
    """Score the picture, keep a running average in `state`, and answer in
    the same shape as judge(): verdict / problem / confidence."""
    if _detect is None:
        if cfg.get("judge") == "obico_docker":
            _detect = lambda p: obico_detect(p, cfg)
        else:
            _detect = local_detect
    detections = _detect(picture)
    score = obico_score(detections)
    a = float(cfg["smoothing"])
    frames = state.get("frames", 0) + 1
    avg = score if frames == 1 else a * score + (1 - a) * state.get("avg", 0.0)
    state["frames"], state["avg"] = frames, round(avg, 3)
    what = ("%d spot%s that look like failure (score %.2f, running %.2f)"
            % (len(detections), "" if len(detections) == 1 else "s", score, avg)
            if detections else "")
    if score >= float(cfg["spike_score"]) or (frames >= 2 and avg >= float(cfg["alert_score"])):
        return {"verdict": "problem", "problem": what, "confidence": min(1.0, max(score, avg)),
                "score": score, "avg": avg, "decided": True}
    if score >= float(cfg["alert_score"]):
        return {"verdict": "unsure", "problem": what, "confidence": min(1.0, score),
                "score": score, "avg": avg, "decided": True}
    return {"verdict": "ok", "problem": what, "confidence": min(1.0, avg),
            "score": score, "avg": avg}


def _compose(*args, env_extra=None):
    env = dict(os.environ)
    oc = obico_config()
    env["OBICO_ML_TOKEN"] = oc["token"]
    env["OBICO_ML_PORT"] = str(urllib.parse.urlparse(oc["url"]).port or 3333)
    env.update(env_extra or {})
    cmd = ["docker", "compose", "-f", OBICO_COMPOSE, "-p", "bonfire-obico"] + list(args)
    try:
        return subprocess.run(cmd, env=env, text=True, capture_output=True, timeout=1800)
    except FileNotFoundError:
        raise RuntimeError("Docker isn't installed (or not on PATH). Install Docker "
                           "Desktop from docker.com, start it, then run this again.")


def obico_cli(action):
    if action == "up":
        print("Building and starting the detector — the first time downloads about "
              "1-2 GB and takes a few minutes...")
        r = _compose("up", "-d", "--build")
        if r.returncode:
            print(r.stdout[-2000:] + r.stderr[-2000:])
            return 1
        for _ in range(60):
            if obico_health():
                print("The detector is up at %s." % obico_config()["url"])
                return 0
            time.sleep(5)
        print("Started, but it isn't answering yet — give it a minute, then "
              "`python tools/bambu_watch.py obico status`.")
        return 1
    if action == "down":
        r = _compose("down")
        print((r.stdout + r.stderr).strip() or "Stopped.")
        return r.returncode
    if action == "status":
        print("detector at %s: %s" % (obico_config()["url"],
                                      "answering" if obico_health() else "NOT answering"))
        return 0
    if action == "test":
        shots = sorted(f for f in os.listdir(SNAP_DIR) if f.endswith(".jpg")) \
            if os.path.isdir(SNAP_DIR) else []
        if not shots:
            print("No snapshot yet: `python tools/bambu_camera.py snapshot` first.")
            return 1
        pic = os.path.join(SNAP_DIR, shots[-1])
        try:
            det = obico_detect(pic) if settings()["judge"] == "obico_docker" \
                else local_detect(pic)
        except RuntimeError as exc:
            print("Couldn't: %s" % exc)
            return 1
        print("%s: score %.2f, %d detection(s) %s"
              % (os.path.basename(pic), obico_score(det), len(det), json.dumps(det)))
        return 0
    print("obico up | down | status | test")
    return 2


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


def act(verdict, status, picture, cfg, plan=None):
    """Keep the picture, try to pause, pop up — and, for a mode that acts
    first (overnight), stop the print through Studio rather than ask."""
    os.makedirs(PROBLEM_DIR, exist_ok=True)
    kept = os.path.join(PROBLEM_DIR, os.path.basename(picture))
    try:
        with open(picture, "rb") as src, open(kept, "wb") as dst:
            dst.write(src.read())
    except OSError:
        kept = picture
    plan = plan or {}
    stopped = None
    if plan.get("act_first"):
        stopped = studio_stop(verdict.get("problem") or "detector", cfg)
    paused = False
    pause_note = ""
    if cfg["try_pause"] and not (stopped or {}).get("ok"):
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
        head = ("Print STOPPED — " if (stopped or {}).get("ok") else
                "Print PAUSED — " if paused else "Print problem — ") + (status.get("job") or "")
        body = ("%s\n\n%s%% done, layer %s of %s. Claude's confidence: %.0f%%.\n\n%s"
                % (what, status.get("progress_pct"), status.get("layer"),
                   status.get("total_layers"), verdict["confidence"] * 100,
                   "The print is paused." if paused else
                   "It could NOT be paused from here (the printer only takes pause "
                   "from Bambu's apps). Pause or stop it in Bambu Studio's Device "
                   "tab, Handy, or on the printer's screen."))
        popup(head, body, kept)
    return {"paused": paused, "pause_note": pause_note, "kept": kept, "stopped": stopped}



# ── modes: which plan this print is on ───────────────────────────────

def modes():
    return _mod("bambu_modes.py")


def plan_for(job, cfg, state):
    """The monitoring plan for the running job: the project's sidecar if it has
    one, else the default mode. Worked out once per print."""
    if state.get("plan") is not None and state.get("plan_job") == job:
        return state["plan"]
    bm = modes()
    found = None
    try:
        found = bm["find_config"](job)
    except Exception as exc:
        log("couldn't read the monitoring config (%s) — using the default mode" % exc)
    try:
        plan = bm["resolve"]((found or {}).get("config"), cfg)
    except Exception as exc:
        log("monitoring config not usable (%s) — using the default mode" % exc)
        plan = bm["resolve"](None, cfg)
    state["plan"], state["plan_job"] = plan, job
    state["project"] = (found or {}).get("project")
    state["three_mf"] = (found or {}).get("three_mf")
    log("mode %s — a picture every %g min%s%s"
        % (plan["mode"], plan["cadence_min"],
           (", bursts of %gs x %d first" % (plan["burst"]["every_s"], plan["burst"]["cycles"]))
           if plan.get("burst") else "",
           (" (%s)" % plan["why"]) if plan.get("why") else ""))
    return plan


def report(state, entry):
    """Add an entry to this print's report in the project (if we know it)."""
    if not state.get("project"):
        return None
    bm = modes()
    path = state.get("report_path")
    if not path:
        path = bm["report_path"](state["project"], state.get("job") or "print")
        state["report_path"] = path
    try:
        _path, index = bm["write_report"](path, dict(entry, job=state.get("job"),
                                                     mode=(state.get("plan") or {}).get("mode"),
                                                     three_mf=state.get("three_mf")))
        state["report_index"] = index
        return path
    except OSError as exc:
        log("couldn't write the error report: %s" % exc)
        return None


def studio_stop(reason="", cfg=None):
    """Stop the print by pressing Studio's own Stop button."""
    cfg = cfg or settings()
    if not cfg.get("stop_via_studio", True):
        return {"ok": False, "note": "stopping through Studio is switched off"}
    try:
        r = _mod("bambu_studio_ui.py")["stop"]()
    except Exception as exc:
        r = {"ok": False, "note": str(exc)}
    log("STOP (%s): %s" % (reason, r.get("note") or r))
    return r


# ── a detection somebody should look at ──────────────────────────────

def ask_for_review(verdict, status, picture, state, plan):
    """Keep the picture and a short question for the next Claude session."""
    os.makedirs(REVIEW_DIR, exist_ok=True)
    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    kept = os.path.join(REVIEW_DIR, "review_%s.jpg" % stamp)
    try:
        with open(picture, "rb") as src, open(kept, "wb") as dst:
            dst.write(src.read())
    except OSError:
        kept = picture
    ask = {"at": datetime.datetime.now().isoformat(timespec="seconds"),
           "picture": kept, "answered": False,
           "question": "The detector flagged %s. Is it real?"
                       % (verdict.get("problem") or "a possible print failure"),
           "score": verdict.get("score"), "detections": verdict.get("detections"),
           "job": state.get("job"), "mode": plan.get("mode"),
           "layer": status.get("layer"), "total_layers": status.get("total_layers"),
           "progress_pct": status.get("progress_pct"),
           "report": state.get("report_path"), "entry": state.get("report_index")}
    path = os.path.join(REVIEW_DIR, "review_%s.json" % stamp)
    try:
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(ask, fh, indent=2)
    except OSError as exc:
        log("couldn't write the review request: %s" % exc)
        return None
    return path


def pending_reviews():
    try:
        files = sorted(f for f in os.listdir(REVIEW_DIR) if f.endswith(".json"))
    except OSError:
        return []
    out = []
    for name in files:
        try:
            with open(os.path.join(REVIEW_DIR, name), encoding="utf-8") as fh:
                ask = json.load(fh)
        except (OSError, ValueError):
            continue
        if not ask.get("answered"):
            ask["file"] = os.path.join(REVIEW_DIR, name)
            out.append(ask)
    return out


def answer_review(real, note="", path=None):
    """
    Answer the oldest open review. real=False marks it a false positive in the
    project's report; real=True stops the print.
    """
    asks = pending_reviews()
    ask = None
    if path:
        ask = next((a for a in asks if a["file"] == path), None)
    elif asks:
        ask = asks[0]
    if not ask:
        return {"ok": False, "error": "Nothing is waiting to be looked at."}
    ask["answered"] = True
    ask["real"] = bool(real)
    ask["note"] = note
    try:
        with open(ask["file"], "w", encoding="utf-8") as fh:
            json.dump(ask, fh, indent=2)
    except OSError:
        pass
    out = {"ok": True, "picture": ask.get("picture"), "real": bool(real)}
    if not real and ask.get("report"):
        try:
            out["false_positives"] = modes()["mark_false_positive"](
                ask["report"], ask.get("entry", -1), note)
        except Exception as exc:
            out["note"] = "couldn't flag it in the report (%s)" % exc
    if real:
        out["stop"] = studio_stop("confirmed by review")
    log("review answered: %s%s" % ("a real problem" if real else "false positive",
                                   (" — %s" % note) if note else ""))
    return out


# ── one check, and the loop ──────────────────────────────────────────

def false_positives(state):
    """How many of this print's flags have been looked at and called wrong."""
    path = state.get("report_path")
    if not path:
        return 0
    try:
        with open(path, encoding="utf-8") as fh:
            doc = json.load(fh)
    except (OSError, ValueError):
        return 0
    return sum(1 for e in doc.get("entries") or [] if e.get("false_positive"))


def check_once(state=None, cfg=None, _status=None, _snapshot=None, _judge=None,
               _act=None, _now=None):
    """
    One pass. Returns {"state", "checked", "verdict"?, "next_in_s"}.
    `state` carries the job, its plan and the last picture between passes.

    A print goes through three phases: set-up (status only, every few seconds,
    no pictures — trouble here stops the print before a gram is wasted), the
    first minute or so of printing, and then pictures at the plan's cadence.
    """
    cfg = cfg or settings()
    state = state if state is not None else {}
    bm = modes()
    now = (_now or (lambda: datetime.datetime.now().timestamp()))()
    status = (_status or _mod("bambu_cloud.py")["printer_status"])()
    printer_state = status.get("state")
    if printer_state not in ACTIVE:
        if state.get("job"):
            log("print ended (%s): %s" % (printer_state, state.get("job")))
        state.clear()
        return {"state": printer_state, "checked": False,
                "next_in_s": 60 * float(cfg["idle_poll_min"])}

    job = status.get("job")
    layer = status.get("layer") or 0
    stage = status.get("stage_id")
    setting_up = printer_state == "preparing" or (stage not in (None, 0)) or layer < 1
    if state.get("job") != job:
        state.clear()
        state.update({"job": job, "job_seen_at": now, "pictures": 0, "last_picture_at": 0})
        # A watch started in the middle of a print doesn't wait for a start it missed.
        state["phase"] = "prep" if setting_up else ("starting" if layer <= 2 else "printing")
        if state["phase"] == "starting":
            state["printing_since"] = now
        log("print started: %s" % job)
    plan = plan_for(job, cfg, state)

    if state.get("phase") == "prep" and not setting_up:
        state["phase"], state["printing_since"] = "starting", now
        log("printing — first picture in %gs" % plan["start_delay_s"])
    elif state.get("phase") == "starting" and not setting_up:
        pass
    if setting_up and stage and state.get("stage") != stage:
        state["stage"] = stage
        log("%s" % (status.get("stage") or "setting up"))

    # What the printer says about itself, every pass, without a picture.
    for trouble in bm["free_check"](plan, status, state, now):
        key = trouble["what"]
        if key in (state.get("told") or []):
            continue
        state.setdefault("told", []).append(key)
        log("PRINTER SAYS: %s — %s" % (key, trouble["detail"]))
        report(state, {"kind": "printer", "what": key, "detail": trouble["detail"],
                       "layer": layer, "phase": state.get("phase")})
        if trouble["serious"] and plan["stop_on_prep_error"] and state.get("phase") == "prep":
            stopped = studio_stop(key, cfg)
            report(state, {"kind": "stopped", "what": key, "result": stopped})
            if cfg["popup"]:
                popup("Print stopped before it started — %s" % (job or ""),
                      "%s\n\n%s\n\n%s" % (key, trouble["detail"],
                                            stopped.get("note") or ""))
        elif trouble["serious"] and plan.get("alert", True) and cfg["popup"]:
            popup("Printer problem — %s" % (job or ""),
                  "%s\n\n%s\n\nLayer %s of %s." % (key, trouble["detail"], layer,
                                                      status.get("total_layers")))

    if state.get("rechecked") and state.get("phase") == "printing":
        decided = {"action": "picture", "next_in_s": 0.0, "why": "another look"}
    else:
        decided = bm["plan_next"](plan, state, status, now, state.get("last_score"))
    if decided["action"] != "picture":
        return {"state": printer_state, "checked": False, "phase": state.get("phase"),
                "why": decided["why"], "next_in_s": max(5.0, decided["next_in_s"])}

    if state.get("phase") != "printing":
        state["phase"] = "printing"
    finish = decided["why"] == "finish shot"
    shot = (_snapshot or _mod("bambu_camera.py")["snapshot"])()
    picture = shot["file"]
    state["pictures"] = int(state.get("pictures") or 0) + 1
    state["last_picture_at"] = now
    if finish:
        state["finish_done"] = True
        log("finish shot — layer %s of %s: %s" % (layer, status.get("total_layers"), picture))
        return {"state": printer_state, "checked": True, "finish_shot": picture,
                "phase": "printing", "next_in_s": 60.0}

    if _judge:
        verdict = _judge(picture, status, state.get("previous"), cfg["model"])
    elif cfg["judge"] == "claude":
        verdict = judge(picture, status, state.get("previous"), cfg["model"])
    else:
        verdict = judge_obico(picture, state, dict(cfg, alert_score=plan["alert_score"],
                                                   spike_score=plan["spike_score"]))
    state["last_score"] = verdict.get("score")
    state["previous"] = picture
    if verdict["verdict"] == "unsure" and not state.get("rechecked"):
        state["rechecked"] = True               # look again in a minute
        log("unsure (%s) — looking again in a minute" % verdict["problem"])
        return {"state": printer_state, "checked": True, "verdict": verdict,
                "phase": "printing", "next_in_s": 60.0}
    state.pop("rechecked", None)

    flagged = verdict["verdict"] in ("problem", "unsure") and (
        verdict.get("decided") or verdict["confidence"] >= float(cfg["act_on"]))
    if not flagged:
        log("ok — layer %s/%s, %s%% (%s)" % (layer, status.get("total_layers"),
                                             status.get("progress_pct"), decided["why"]))
        return {"state": printer_state, "checked": True, "verdict": verdict,
                "phase": "printing", "next_in_s": max(30.0, 60.0 * float(plan["cadence_min"]))}

    if not plan.get("alert", True) or state.get("muted"):
        log("flagged (%s) — logged only, this print isn't alerting" % verdict["problem"])
        return {"state": printer_state, "checked": True, "verdict": verdict,
                "phase": "printing", "next_in_s": 60.0 * float(plan["cadence_min"])}

    fps = false_positives(state)
    if fps >= int(plan["max_false_positives"]):
        if plan["on_false_positive_limit"] == "stop":
            stopped = studio_stop("%d false positives on this print" % fps, cfg)
            report(state, {"kind": "stopped", "what": "false positives", "result": stopped})
            return {"state": printer_state, "checked": True, "verdict": verdict,
                    "acted": {"stopped": stopped}, "phase": "printing", "next_in_s": 600.0}
        if not state.get("muted"):
            state["muted"] = True
            log("%d false positives on this print — logged only from here on" % fps)
        return {"state": printer_state, "checked": True, "verdict": verdict,
                "phase": "printing", "next_in_s": 60.0 * float(plan["cadence_min"])}
    report(state, {"kind": "detector", "what": verdict.get("problem") or "possible failure",
                   "score": verdict.get("score"), "confidence": verdict.get("confidence"),
                   "picture": picture, "layer": layer,
                   "progress_pct": status.get("progress_pct")})
    acted = (_act or act)(verdict, status, picture, cfg, plan)
    if plan["escalate"] != "off" and not plan["act_first"]:
        acted = dict(acted or {}, review=ask_for_review(verdict, status, picture, state, plan))
    state["flags"] = int(state.get("flags") or 0) + 1
    return {"state": printer_state, "checked": True, "verdict": verdict, "acted": acted,
            "phase": "printing", "next_in_s": max(60.0 * float(plan["cadence_min"]), 900.0)}


def _lock_pid():
    try:
        with open(LOCK_PATH, encoding="utf-8") as fh:
            return int(fh.read().strip() or 0)
    except (OSError, ValueError):
        return 0


def _already_running():
    pid = _lock_pid()
    if pid == os.getpid() or pid <= 0:
        return False
    if os.name == "nt":
        out = subprocess.run(["tasklist", "/FI", "PID eq %d" % pid, "/NH"],
                             capture_output=True, text=True,
                             creationflags=0x08000000).stdout    # no console flash
        return str(pid) in out
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _write_state(data):
    try:
        with open(STATE_PATH, "w", encoding="utf-8") as fh:
            json.dump(data, fh)
    except OSError:
        pass


def _read_state():
    try:
        with open(STATE_PATH, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {}


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
            # Load this file again each pass, so an update to the watch takes
            # effect without restarting it (falls back to the running copy).
            try:
                fresh = _mod("bambu_watch.py")
                once, cfg = fresh["check_once"], fresh["settings"]()
            except Exception:
                once = check_once
            r = once(state, cfg)
            wait = r["next_in_s"]
            last = {"printer": r.get("state"), "checked": r.get("checked")}
        except Exception as exc:                 # network blips, sign-in expiry...
            log("check failed: %s" % exc)
            wait = 120.0
            last = {"error": str(exc)[:200]}
        _write_state(dict(last, at=datetime.datetime.now().isoformat(timespec="seconds"),
                          next_in_s=int(wait), pid=os.getpid()))
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
    before = _lock_pid()
    subprocess.Popen([pyw, script, "run"], cwd=ROOT,
                     creationflags=getattr(subprocess, "DETACHED_PROCESS", 0))
    for _ in range(40):                          # wait for it to take the lock
        time.sleep(0.25)
        if _lock_pid() not in (0, before) and _already_running():
            break
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
    cfg = settings()
    lines = ["installed at start-up: %s" % ("yes" if os.path.isfile(_startup_path()) else "no"),
             "running now: %s" % ("yes" if _already_running() else "no"),
             "judge: %s" % cfg["judge"]]
    ready, why = detector_ready()
    lines.append("judge ready: %s" % ("yes" if ready else "NO — " + why))
    last = _read_state()
    if last.get("at"):
        if last.get("error"):
            what = "failed: " + last["error"]
        else:
            what = "printer %s%s" % (last.get("printer"),
                                     ", picture checked" if last.get("checked") else "")
        lines.append("last pass: %s — %s; next in about %d min"
                     % (last["at"].replace("T", " "), what, max(1, last.get("next_in_s", 0) // 60)))
    lines.append("settings: %s" % json.dumps(cfg))
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
    if cmd == "obico":
        return obico_cli(argv[2] if len(argv) > 2 else "")
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(_cli(sys.argv))
