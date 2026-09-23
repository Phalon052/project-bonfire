#!/usr/bin/env python3
"""
Project Bonfire — monitoring modes for the print watch.

Each 3MF can carry a small sidecar next to it, `<name>.monitor.json`, saying
how closely that print should be watched. The watch finds it by the job name
the printer reports, so nothing has to be passed at print time.

    python tools/bambu_modes.py modes                       # the modes and what they're for
    python tools/bambu_modes.py set <project> <mode> [--every 8] [--why "..."]
    python tools/bambu_modes.py show <project>

Everything here is decisions, not doing: which mode a job is in, when the next
picture is due, and what the printer's own status says without a picture. The
watch (bambu_watch.py) does the looking.
"""
import datetime
import glob
import json
import os
import re
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
SIDECAR_SUFFIX = ".monitor.json"
ERROR_DIR_NAME = "Error Report"

# Settings every mode has. A mode sets some; the sidecar can override any.
BASE = {
    "mode": "default",
    "why": "",                    # a line for the log and the report
    "cadence_min": 8,             # between pictures, the steady rate
    "burst": None,                # {"every_s": 30, "cycles": 20} right after the start
    "windows": [],                # [{"from_layer"/"to_layer" or "from_pct"/"to_pct",
                                  #   "every_min": 2, "why": ""}]
    "free_checks": True,          # status-only checks (no picture, no tokens)
    "adaptive": True,             # tighten the cadence while the score is climbing
    "finish_shot": True,          # one picture 2 layers from the end, for the log
    "escalate": "session",        # session | api | off  — who confirms a detection
    "act_first": False,           # act on a detection before confirming it
    "alert_score": None,          # None: from camera_watch in bambu_config.json
    "spike_score": None,
    "max_false_positives": 3,
    "on_false_positive_limit": "log_only",   # log_only | stop
    "stop_on_prep_error": True,   # stop during set-up if the printer reports trouble
    "stall_min": 15,              # no new layer for this long while printing = stalled
    "prep_wait_s": 120,           # settle time after a job appears
    "prep_poll_s": 10,            # status checks during set-up
    "start_delay_s": 80,          # after printing starts, before the first picture
    "status_poll_s": 30,          # status checks while printing (free checks)
    "finish_shot_layers": 2,      # how far from the last layer the finish shot goes
}

MODES = {
    "default": {
        "cadence_min": 8,
        "what_for": "Medium parts with nothing unusual: no long overhangs, a solid "
                    "footprint, nothing that has to be caught in the first minutes.",
    },
    "early": {
        "cadence_min": 8,
        "burst": {"every_s": 30, "cycles": 20},
        "what_for": "Batches of small or thin parts, and wide flat parts. Watches the "
                    "first ten minutes closely, when one part breaking loose or a corner "
                    "lifting sets up every later failure, then backs off.",
    },
    "complex": {
        "cadence_min": 8,
        "burst": {"every_s": 30, "cycles": 10},
        "what_for": "Detailed or thin models: a close look at the start, plus your own "
                    "layer windows over the parts that are fiddly, and a light touch "
                    "over the rest. Give it windows.",
    },
    "tall": {
        "cadence_min": 8,
        "windows": [{"from_pct": 40, "every_min": 4, "why": "getting top-heavy"},
                    {"from_pct": 70, "every_min": 2, "why": "tall and easy to knock over"}],
        "what_for": "Anything much taller than its footprint, where the risk grows with "
                    "height instead of sitting at the start.",
    },
    "overnight": {
        "cadence_min": 10,
        "alert_score": 0.35,
        "act_first": True,
        "what_for": "Long prints with nobody in the room: fewer pictures, a lower bar "
                    "for calling it, and it acts first and explains afterwards.",
    },
    "quick": {
        "cadence_min": 2,
        "escalate": "off",
        "what_for": "Short prints — test pieces, calibration, a single small part. A "
                    "picture every couple of minutes and no confirmation step, because "
                    "the whole print is over in the time one confirmation takes.",
    },
    "watch_only": {
        "cadence_min": 8,
        "escalate": "off",
        "act_first": False,
        "alert": False,
        "what_for": "Records pictures and scores and never alerts. For tuning the "
                    "thresholds, and for prints you're standing next to.",
    },
}


class ModeError(Exception):
    """Something about a monitoring config, in words worth showing."""


# ── the sidecar next to a 3MF ────────────────────────────────────────

def sidecar_path(three_mf):
    return os.path.splitext(three_mf)[0] + SIDECAR_SUFFIX


def write_config(three_mf, mode="default", **over):
    """Save the sidecar for one 3MF. Only the keys given are written, so the
    mode's own settings stay live if they're ever tuned."""
    if mode not in MODES:
        raise ModeError("No monitoring mode called %r. There is: %s."
                        % (mode, ", ".join(sorted(MODES))))
    cfg = {"mode": mode}
    for key, value in over.items():
        if key not in BASE:
            raise ModeError("%r isn't a monitoring setting. There is: %s."
                            % (key, ", ".join(sorted(BASE))))
        if value is not None:
            cfg[key] = value
    path = sidecar_path(three_mf)
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(cfg, fh, indent=2)
        fh.write("\n")
    return {"ok": True, "file": path, "config": cfg, "plan": resolve(cfg)}


def load_config(three_mf):
    path = sidecar_path(three_mf)
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


def _stem_key(name):
    """A job name and a file name are the same print if this matches: no
    extension, no plate suffix, no punctuation, lower case."""
    stem = os.path.splitext(os.path.basename(str(name) or ""))[0]
    stem = re.sub(r"\.gcode$", "", stem, flags=re.I)
    stem = re.sub(r"[_ -]?plate[_ -]?\d+$", "", stem, flags=re.I)
    return re.sub(r"[^a-z0-9]+", "", stem.lower())


def _loose_key(name):
    """The same, with the 3MF's version number dropped, so a config set on
    `part_3.3mf` still covers `part_4.3mf` from the same project."""
    return re.sub(r"\d+$", "", _stem_key(name))


def find_config(job, library=None):
    """
    The sidecar for the job the printer is running, found by name. Returns
    {"config", "file", "three_mf", "project"} or None.
    """
    if not job:
        return None
    library = library or _library()
    want = _stem_key(job)
    if not want:
        return None
    loose_want = _loose_key(job)
    best = None
    for path in sorted(glob.glob(os.path.join(library, "*", "3mf", "*" + SIDECAR_SUFFIX))):
        stem = path[:-len(SIDECAR_SUFFIX)]
        key = _stem_key(stem)
        if not key:
            continue
        if key == want:
            best = path
            break
        near = (key in want or want in key
                or (loose_want and _loose_key(stem) == loose_want))
        if near and best is None:
            best = path                      # a near match, kept only if nothing better
    if not best:
        return None
    try:
        with open(best, encoding="utf-8") as fh:
            cfg = json.load(fh)
    except (OSError, ValueError) as exc:
        raise ModeError("Couldn't read %s (%s)." % (best, exc))
    three_mf = best[:-len(SIDECAR_SUFFIX)] + ".3mf"
    return {"config": cfg, "file": best, "three_mf": three_mf,
            "project": os.path.dirname(os.path.dirname(best))}


def _library():
    try:
        import runpy
        return runpy.run_path(os.path.join(_HERE, "paths.py"))["LIBRARY"]
    except Exception:
        return os.path.join(os.path.dirname(_HERE), "catalog", "model library")


def resolve(config=None, watch_settings=None):
    """One mode's settings, the sidecar's overrides on top, then the watch's
    own thresholds where the plan leaves them open."""
    config = dict(config or {})
    mode = config.get("mode", "default")
    if mode not in MODES:
        raise ModeError("No monitoring mode called %r. There is: %s."
                        % (mode, ", ".join(sorted(MODES))))
    plan = dict(BASE)
    plan["mode"] = mode
    plan.update({k: v for k, v in MODES[mode].items() if k != "what_for"})
    plan.update({k: v for k, v in config.items() if k in BASE or k == "alert"})
    for key in ("alert_score", "spike_score"):
        if plan.get(key) is None and watch_settings:
            plan[key] = watch_settings.get(key)
    plan.setdefault("alert", True)
    return plan


# ── when the next picture is due ─────────────────────────────────────

def _window_cadence(plan, status):
    """The tightest window that covers where the print is now, in minutes."""
    layer = status.get("layer") or 0
    total = status.get("total_layers") or 0
    pct = status.get("progress_pct")
    if pct is None and total:
        pct = 100.0 * layer / total
    best = None
    for w in plan.get("windows") or []:
        if "from_layer" in w and layer < w["from_layer"]:
            continue
        if "to_layer" in w and layer > w["to_layer"]:
            continue
        if "from_pct" in w and (pct is None or pct < w["from_pct"]):
            continue
        if "to_pct" in w and (pct is None or pct > w["to_pct"]):
            continue
        every = float(w.get("every_min") or plan["cadence_min"])
        if best is None or every < best[0]:
            best = (every, w.get("why") or "a window of this print")
    return best


def plan_next(plan, st, status, now=None, score=None):
    """
    What the watch should do right now, as pure arithmetic.

    `st` is the watch's state for this print and carries: phase, job_seen_at,
    printing_since, pictures, last_picture_at, finish_done.
    Returns {"action": "wait" | "picture" | "free_check", "next_in_s", "why"}.
    """
    now = now if now is not None else _now()
    phase = st.get("phase") or "prep"
    if phase == "prep":
        waited = now - float(st.get("job_seen_at") or now)
        if waited < float(plan["prep_wait_s"]):
            return {"action": "wait", "next_in_s": float(plan["prep_poll_s"]),
                    "why": "the printer is downloading and setting up"}
        return {"action": "free_check", "next_in_s": float(plan["prep_poll_s"]),
                "why": "set-up: status checks only, no pictures yet"}
    if phase == "starting":
        since = now - float(st.get("printing_since") or now)
        left = float(plan["start_delay_s"]) - since
        if left > 0:
            return {"action": "wait", "next_in_s": min(left, float(plan["status_poll_s"])),
                    "why": "first layers going down"}
        return {"action": "picture", "next_in_s": 0.0, "why": "first look"}

    poll = float(plan["status_poll_s"])
    layer = status.get("layer") or 0
    total = status.get("total_layers") or 0
    if (plan["finish_shot"] and not st.get("finish_done") and total
            and layer >= total - int(plan["finish_shot_layers"])):
        return {"action": "picture", "next_in_s": 0.0, "why": "finish shot"}

    burst = plan.get("burst")
    why = "every %g min" % plan["cadence_min"]
    every_s = 60.0 * float(plan["cadence_min"])
    if burst and int(st.get("pictures") or 0) < int(burst.get("cycles", 0)):
        every_s = float(burst.get("every_s", 30))
        why = "early watch, %d of %d" % (int(st.get("pictures") or 0) + 1,
                                         int(burst.get("cycles", 0)))
    else:
        win = _window_cadence(plan, status)
        if win and 60.0 * win[0] < every_s:
            every_s, why = 60.0 * win[0], win[1]
    if plan["adaptive"] and score is not None and plan.get("alert_score"):
        rising = score >= 0.5 * float(plan["alert_score"]) and score > float(st.get("last_score") or 0)
        if rising:
            every_s = max(60.0, every_s / 2.0)
            why += ", tightened (score climbing)"
    since_shot = now - float(st.get("last_picture_at") or 0)
    if since_shot >= every_s:
        return {"action": "picture", "next_in_s": 0.0, "why": why}
    return {"action": "free_check", "next_in_s": min(poll, every_s - since_shot), "why": why}


def _now():
    return datetime.datetime.now().timestamp()


# ── what the status alone says (no picture, no tokens) ───────────────

def free_check(plan, status, st, now=None):
    """
    Trouble the printer reports itself. Returns a list of
    {"what", "detail", "serious"} — serious means don't wait for a picture.
    """
    now = now if now is not None else _now()
    out = []
    if not plan.get("free_checks", True):
        return out
    for err in status.get("errors") or []:
        out.append({"what": "printer error %s" % err.get("code"),
                    "detail": err.get("help") or "", "serious": True})
    if status.get("print_error"):
        out.append({"what": "print error %s" % status["print_error"],
                    "detail": "the printer flagged the job itself", "serious": True})
    layer = status.get("layer") or 0
    if status.get("state") == "printing" and (status.get("stage_id") in (None, 0)):
        if layer and layer != st.get("last_layer"):
            st["last_layer"], st["last_layer_at"] = layer, now
        elif layer and st.get("last_layer_at") is not None:
            stalled_min = (now - float(st["last_layer_at"])) / 60.0
            if stalled_min >= float(plan["stall_min"]):
                out.append({"what": "no new layer in %d minutes" % int(stalled_min),
                            "detail": "still on layer %s of %s — a clog or a stopped "
                                      "extruder looks like this, and the camera can't "
                                      "see it" % (layer, status.get("total_layers")),
                            "serious": True})
        nozzle, target = status.get("nozzle_c"), status.get("nozzle_target_c")
        if nozzle is not None and target and float(target) > 100 and float(nozzle) < float(target) - 40:
            out.append({"what": "nozzle %g°C, well below its %g°C target"
                                % (float(nozzle), float(target)),
                        "detail": "heating fault or a thermal runaway cut-off",
                        "serious": True})
    return out


# ── the error report in the project ──────────────────────────────────

def report_path(project_root, job, when=None):
    when = when or datetime.datetime.now()
    stem = re.sub(r"[^A-Za-z0-9_.-]+", "_", os.path.splitext(os.path.basename(job or "print"))[0])
    folder = os.path.join(project_root, ERROR_DIR_NAME)
    return os.path.join(folder, "%s_%s.json" % (when.strftime("%Y%m%d_%H%M%S"), stem))


def write_report(path, entry):
    """Append one entry to a print's report, creating it the first time.
    Returns (path, index of the entry)."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    try:
        with open(path, encoding="utf-8") as fh:
            doc = json.load(fh)
    except (OSError, ValueError):
        doc = {"entries": []}
    entry = dict(entry)
    entry.setdefault("at", datetime.datetime.now().isoformat(timespec="seconds"))
    entry.setdefault("false_positive", False)
    doc.setdefault("entries", []).append(entry)
    for key in ("job", "mode", "three_mf"):
        if key in entry and key not in doc:
            doc[key] = entry[key]
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, indent=2)
        fh.write("\n")
    return path, len(doc["entries"]) - 1


def mark_false_positive(path, index=-1, note=""):
    """Flip an entry's false_positive flag. Returns how many are flagged."""
    with open(path, encoding="utf-8") as fh:
        doc = json.load(fh)
    entries = doc.get("entries") or []
    if not entries:
        raise ModeError("%s has no entries." % path)
    entries[index]["false_positive"] = True
    if note:
        entries[index]["note"] = note
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, indent=2)
        fh.write("\n")
    return sum(1 for e in entries if e.get("false_positive"))


# ── CLI ──────────────────────────────────────────────────────────────

def _project_3mf(project):
    import runpy
    bp = runpy.run_path(os.path.join(_HERE, "paths.py"))
    folder = bp["resolve_project"](project)
    if isinstance(folder, dict):
        folder = folder.get("folder") or folder.get("root")
    if not folder:
        raise ModeError("No project matching %r." % project)
    root = folder if os.path.isdir(folder) else os.path.join(bp["LIBRARY"], folder)
    shots = sorted(glob.glob(os.path.join(root, "3mf", "*.3mf")))
    if not shots:
        raise ModeError("No 3MF in %s yet — build one first." % root)
    return shots[-1]


def _cli(argv):
    try:
        cmd = argv[1] if len(argv) > 1 else ""
        if cmd == "modes":
            for name, spec in MODES.items():
                print("%-11s every %g min%s\n            %s"
                      % (name, spec.get("cadence_min", BASE["cadence_min"]),
                         (", bursts of %gs x %d at the start"
                          % (spec["burst"]["every_s"], spec["burst"]["cycles"]))
                         if spec.get("burst") else "",
                         spec["what_for"]))
            return 0
        if cmd == "set" and len(argv) > 3:
            three = _project_3mf(argv[2])
            over = {}
            if "--every" in argv:
                over["cadence_min"] = float(argv[argv.index("--every") + 1])
            if "--why" in argv:
                over["why"] = argv[argv.index("--why") + 1]
            r = write_config(three, argv[3], **over)
            print("Saved %s — mode %s, a picture every %g min."
                  % (r["file"], r["plan"]["mode"], r["plan"]["cadence_min"]))
            return 0
        if cmd == "show" and len(argv) > 2:
            three = _project_3mf(argv[2])
            cfg = load_config(three)
            print(json.dumps({"three_mf": three, "config": cfg,
                              "plan": resolve(cfg or {})}, indent=2))
            return 0
    except ModeError as exc:
        print("Couldn't: %s" % exc)
        return 1
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(_cli(sys.argv))
