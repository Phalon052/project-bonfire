#!/usr/bin/env python3
"""
Project Bonfire — Phase 4: running prints on the P1S.

    preview  →  (your yes)  →  start     pause / resume     stop (your yes)

    python tools/bambu_print.py preview <file.gcode.3mf> [plate]
    python tools/bambu_print.py start <file.gcode.3mf> <approval code> [plate]
        (on the studio / bambu_connect routes the code isn't needed — you
        press Print in that app)
    python tools/bambu_print.py pause | resume | stop --yes
    python tools/bambu_print.py route [lan_cloud|bambu_connect|studio]
    python tools/bambu_print.py retarget <makerworld.3mf>

The rules come from 04_bambu_basics.md section 7:

  * Starting a print needs a yes every time, after the preview. Stopping needs
    a yes. Pausing and resuming don't.
  * The yes is enforced here, not left to the chat app: `preview` hands out a
    one-time code, valid for ten minutes, for exactly that file and plate;
    `start` refuses without it. If the desktop app auto-approves tool calls,
    this is the only thing between a request and a moving print head. It can
    be turned off with `print_needs_approval: false` in tools/bambu_config.json.

How a print gets to the printer is the *route* (tools/bambu_config.json →
`print_route`):

  lan_cloud      (default) the file goes onto the printer's SD card over the
                 home network (bambu_lan.py), and Bambu Cloud starts it.
  bambu_connect  Bambu's own Bambu Connect app opens with the file; you click
                 Print → Send there. Bambu is moving network print starts
                 behind it (X1 first, P series "in future firmware"). If the
                 printer ever refuses a start for that reason, `start` switches
                 the route to this by itself and says so.
  studio         the file opens in Bambu Studio; you press Print.

Start options, per 04 and the 2026-09-19 decision: bed levelling on; flow
calibration, timelapse, vibration calibration and first-layer inspection off.

Also here: `retarget_to_p1s`, for 3MFs from MakerWorld that open set up for an
X1 — it swaps in the P1S's own machine settings (start/end G-code, nozzle,
limits, bed no-print area: 69 settings, from Bambu's own profiles) and leaves
the process and filament choices alone, the way Studio does when you switch
printers.
"""
import datetime
import hashlib
import json
import os
import re
import runpy
import secrets
import subprocess
import sys
import time
import urllib.parse
import webbrowser
import xml.etree.ElementTree as ET
import zipfile

_HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(_HERE)
CONFIG_PATH = os.path.join(_HERE, "bambu_config.json")
APPROVALS_FILE = os.path.join(_HERE, "bambu_print.local.json")

bc = runpy.run_path(os.path.join(_HERE, "bambu_cloud.py"))
bl = runpy.run_path(os.path.join(_HERE, "bambu_lan.py"))
bs = runpy.run_path(os.path.join(_HERE, "bambu_slice.py"))
b3 = runpy.run_path(os.path.join(_HERE, "bambu_3mf.py"))
bpre = runpy.run_path(os.path.join(_HERE, "bambu_presets.py"))

ROUTES = ("lan_cloud", "bambu_connect", "studio")
APPROVAL_MINUTES = 10
START_OPTIONS = {"bed_leveling": True, "flow_cali": False, "timelapse": False,
                 "vibration_cali": False, "layer_inspect": False}
IDLE_STATES = ("idle", "finished", "failed")
EXTERNAL_SPOOL = 254                    # Bambu's tray number for the spool holder


class PrintError(Exception):
    """A reason not to go ahead, in words worth showing."""


# ── configuration ────────────────────────────────────────────────────

def read_config():
    try:
        with open(CONFIG_PATH, encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return {}


def write_config(cfg):
    with open(CONFIG_PATH, "w", encoding="utf-8") as fh:
        json.dump(cfg, fh, indent=2)


def route():
    r = read_config().get("print_route", "lan_cloud")
    return r if r in ROUTES else "lan_cloud"


def set_route(new_route, why=""):
    if new_route not in ROUTES:
        raise PrintError("Route must be one of: %s" % ", ".join(ROUTES))
    cfg = read_config()
    old = cfg.get("print_route", "lan_cloud")
    cfg["print_route"] = new_route
    if why:
        cfg["print_route_changed"] = {
            "from": old, "to": new_route, "why": why,
            "when": datetime.datetime.now().isoformat(timespec="seconds")}
    write_config(cfg)
    return {"ok": True, "route": new_route, "was": old}


def needs_approval():
    return bool(read_config().get("print_needs_approval", True))


# ── what's in a sliced file ──────────────────────────────────────────

def file_sha1(path):
    h = hashlib.sha1()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def project_filaments(path):
    """Every filament slot the project defines: 1-based id, type, colour."""
    try:
        s = b3["read_project_settings"](path)
    except Exception:
        return []
    types = s.get("filament_type") or []
    colours = s.get("filament_colour") or []
    names = s.get("filament_settings_id") or []
    return [{"id": i + 1,
             "type": types[i] if i < len(types) else "",
             "colour": (colours[i] if i < len(colours) else "").upper(),
             "preset": names[i] if i < len(names) else ""}
            for i in range(max(len(types), len(colours)))]


# ── matching the project's filaments to what's loaded ────────────────

def _rgb(hexcolour):
    h = (hexcolour or "").lstrip("#")[:6]
    try:
        return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))
    except ValueError:
        return None


def _type_matches(want, have):
    """Exact material only. Bambu reports types as PLA, PETG, PLA-CF, PETG-CF…
    and a loose match would feed carbon-fibre filament to a PLA job (or the
    other way round)."""
    want = (want or "").strip().upper()
    have = (have or "").strip().upper()
    return bool(want) and want == have


def map_filaments(used, loaded, overrides=None):
    """
    Pick an AMS slot for each filament the plate uses (04 section 4: read
    what's loaded each time). Same material and same colour first; same
    material in another colour next, with a note; nothing at all means the
    material isn't loaded, and the print doesn't start.

    used:   [{"id", "type", "colour"}] — from the slice
    loaded: parse_ams() output from bambu_cloud
    overrides: {filament id: slot number} from the person, taking precedence
    """
    overrides = overrides or {}
    trays = [t for t in loaded if t.get("loaded")]
    result, missing, notes = {}, [], []
    for f in used:
        fid = f["id"]
        if fid in overrides:
            slot = overrides[fid]
            tray = next((t for t in trays if str(t["slot"]) == str(slot)), None)
            if not tray:
                missing.append("filament %d: slot %s was asked for, but it's "
                               "empty" % (fid, slot))
                continue
            result[fid] = tray
            if not _type_matches(f["type"], tray["type"]):
                notes.append("filament %d is %s but slot %s holds %s — as asked"
                             % (fid, f["type"], slot, tray["type"]))
            continue
        same = [t for t in trays if _type_matches(f["type"], t["type"])]
        if not same:
            missing.append("filament %d (%s %s) isn't loaded"
                           % (fid, f["type"], f["colour"]))
            continue
        exact = [t for t in same if t["colour"].upper() == f["colour"].upper()]
        if exact:
            result[fid] = exact[0]
            continue
        want = _rgb(f["colour"])
        if want:
            same.sort(key=lambda t: sum((a - b) ** 2 for a, b in
                                        zip(want, _rgb(t["colour"]) or want)))
        result[fid] = same[0]
        notes.append("filament %d is %s %s in the project; slot %s has %s %s"
                     % (fid, f["type"], f["colour"], same[0]["slot"],
                        same[0]["type"], same[0]["colour"]))
    return {"slots": result, "missing": missing, "notes": notes}


def ams_mapping(n_filaments, slots):
    """The printer's `ams_mapping`: one entry per project filament, holding the
    AMS tray number (AMS 1 slot 1 = 0 … slot 4 = 3, AMS 2 slot 1 = 4 …), the
    spool holder as 254, or -1 for a filament this plate doesn't use."""
    out = [-1] * max(n_filaments, max(slots) if slots else 0)
    for fid, tray in slots.items():
        out[fid - 1] = EXTERNAL_SPOOL if tray["slot"] == "external" \
            else int(tray["slot"]) - 1
    return out


# ── the preview, and the one-time code ───────────────────────────────

def _load_approvals():
    try:
        with open(APPROVALS_FILE, encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return {}


def _save_approvals(data):
    now = time.time()
    data = {k: v for k, v in data.items() if v.get("expires", 0) > now}
    with open(APPROVALS_FILE, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2)


def issue_code(path, plate, mapping):
    data = _load_approvals()
    code = secrets.token_hex(3).upper()             # six characters
    data[code] = {"file": os.path.abspath(path), "sha1": file_sha1(path),
                  "plate": plate, "mapping": mapping,
                  "expires": time.time() + APPROVAL_MINUTES * 60}
    _save_approvals(data)
    return code


def redeem_code(code, path, plate):
    """One use only, same file (unchanged since the preview), same plate."""
    data = _load_approvals()
    entry = data.pop((code or "").strip().upper(), None)
    _save_approvals(data)
    if not entry:
        raise PrintError("That approval code isn't valid — it may have expired "
                         "(%d minutes) or been used. Run the preview again."
                         % APPROVAL_MINUTES)
    if entry.get("expires", 0) <= time.time():
        raise PrintError("That approval code expired (codes last %d minutes). "
                         "Run the preview again." % APPROVAL_MINUTES)
    if entry["file"] != os.path.abspath(path) or entry["plate"] != plate:
        raise PrintError("That approval was for %s plate %s, not this."
                         % (os.path.basename(entry["file"]), entry["plate"]))
    if entry["sha1"] != file_sha1(path):
        raise PrintError("The file has changed since the preview. Run the "
                         "preview again.")
    return entry


def preview(path, plate=1, slots=None, status=None):
    """
    Everything to decide on before a print starts: file, plate, time, grams,
    which AMS slot feeds each filament, and whether the printer is free. With
    approval on, it ends with a one-time code for `start`.

    slots: optional "1:3,2:4" — filament 1 from AMS slot 3, filament 2 from 4.
    """
    path = os.path.abspath(path)
    if not os.path.isfile(path):
        raise PrintError("No file at %s" % path)
    info = bs["read_slice_info"](path)
    if not info.get("sliced"):
        raise PrintError("%s isn't sliced — slice it first (slice_3mf)."
                         % os.path.basename(path))
    plates = {p["plate"]: p for p in info["plates"]}
    if plate not in plates:
        raise PrintError("Plate %s isn't in this file; it has plate(s) %s."
                         % (plate, ", ".join(str(k) for k in sorted(plates))))
    p = plates[plate]
    defined = {f["id"]: f for f in project_filaments(path)}
    used = [{"id": f["slot"], "type": f["type"] or defined.get(f["slot"], {}).get("type", ""),
             "colour": (f["colour"] or defined.get(f["slot"], {}).get("colour", "")).upper(),
             "grams": f["used_g"]} for f in p["filaments"]]

    st = status or bc["printer_status"]()
    overrides = _parse_slots(slots)
    m = map_filaments(used, st.get("ams", []), overrides)

    problems = list(m["missing"])
    if st.get("state") not in IDLE_STATES:
        problems.append("the printer is %s — it has to be idle, finished or "
                        "failed to start something new" % st.get("state"))
    if p.get("outside_plate"):
        problems.append("some toolpath falls outside the printable area")
    for w in p.get("warnings", []):
        if not w.get("ignored") and w.get("level", 0) >= 2:
            problems.append(w["message"])
    if st.get("errors"):
        problems.append("the printer is reporting HMS errors: %s"
                        % ", ".join(e["code"] for e in st["errors"]))

    use_ams = any(t["slot"] != "external" for t in m["slots"].values())
    mapping = ams_mapping(len(defined) or len(used), m["slots"])
    out = {
        "ok": not problems,
        "file": path, "plate": plate, "plates_in_file": sorted(plates),
        "print_time": p.get("print_time"), "print_seconds": p.get("print_seconds"),
        "filament_g": p.get("filament_g"),
        "filaments": [{"filament": f["id"], "type": f["type"], "colour": f["colour"],
                       "grams": f["grams"],
                       "slot": (m["slots"].get(f["id"]) or {}).get("slot")}
                      for f in used],
        "use_ams": use_ams, "ams_mapping": mapping,
        "printer": st.get("printer"), "printer_state": st.get("state"),
        "route": route(), "start_options": dict(START_OPTIONS),
        "notes": m["notes"], "problems": problems,
    }
    if st.get("commands_need_signing") and out["route"] == "lan_cloud":
        out["notes"].append(
            "this printer's firmware reports that it wants signed commands; a "
            "start over the cloud may be refused — if it is, the route "
            "switches to Bambu Connect by itself")
    if out["ok"] and needs_approval() and out["route"] == "lan_cloud":
        out["approval_code"] = issue_code(path, plate, mapping)
        out["approval_expires_min"] = APPROVAL_MINUTES
    return out


def _parse_slots(text):
    """'1:3,2:4' -> {1: '3', 2: '4'}; 'ext' or 'external' for the spool holder."""
    out = {}
    for part in (text or "").replace(" ", "").split(","):
        if ":" in part:
            f, s = part.split(":", 1)
            try:
                out[int(f)] = "external" if s.lower().startswith("ext") else s
            except ValueError:
                raise PrintError("Couldn't read slot choice %r — use e.g. 1:3" % part)
    return out


def format_preview(pv):
    lines = ["%s — plate %s of %s" % (os.path.basename(pv["file"]), pv["plate"],
                                        len(pv["plates_in_file"]))]
    lines.append("  %s, %.1f g, on %s (%s)"
                 % (pv.get("print_time") or "time unknown", pv.get("filament_g") or 0,
                    pv.get("printer") or "the printer", pv.get("printer_state")))
    for f in pv["filaments"]:
        lines.append("  filament %s: %s %s, %.1f g ← %s"
                     % (f["filament"], f["type"], f["colour"], f["grams"] or 0,
                        "AMS slot %s" % f["slot"] if f["slot"] not in (None, "external")
                        else ("spool holder" if f["slot"] == "external" else "NOT LOADED")))
    lines.append("  bed levelling on; flow calibration and timelapse off")
    lines.append("  route: %s" % {"lan_cloud": "upload over the home network, start "
                                  "over Bambu Cloud",
                                  "bambu_connect": "opens in Bambu Connect for you "
                                  "to send",
                                  "studio": "opens in Bambu Studio for you to "
                                  "print"}[pv["route"]])
    for n in pv["notes"]:
        lines.append("  note: " + n)
    for p in pv["problems"]:
        lines.append("  ✗ " + p)
    if pv.get("approval_code"):
        lines.append("")
        lines.append("  Say yes to start. Approval code %s (one use, %d minutes)."
                     % (pv["approval_code"], pv["approval_expires_min"]))
    return "\n".join(lines)


# ── starting, pausing, resuming, stopping ────────────────────────────

AUTH_WORDS = ("verif", "auth", "sign", "permission", "not allowed", "forbid",
              "bambu connect")
# "MQTT Command verification failed" — the printer's firmware only accepts
# print commands signed by Bambu's own software (Studio, Handy, Bambu Connect).
# Seen on this P1S on 2026-09-19 in answer to project_file; the printer sent
# only this code, no result and no reason. Hex 0x05024007.
VERIFY_FAILED_CODES = {84033543}


def looks_like_authorization(echo, fun_hex=None):
    echo = echo or {}
    try:
        if int(echo.get("err_code") or 0) in VERIFY_FAILED_CODES:
            return True
    except (TypeError, ValueError):
        pass
    reason = " ".join(str(v) for v in echo.values()).lower()
    if any(w in reason for w in AUTH_WORDS):
        return True
    try:
        return bool(int(str(fun_hex), 16) & 0x20000000) if fun_hex else False
    except ValueError:
        return False


def bambu_connect_installed():
    """Is Bambu Connect there to hand files to? Its link handler is registered
    with Windows when it's installed."""
    if os.name == "nt":
        try:
            import winreg
            for root in (winreg.HKEY_CURRENT_USER, winreg.HKEY_CLASSES_ROOT):
                try:
                    key = r"Software\Classes\bambu-connect" \
                        if root == winreg.HKEY_CURRENT_USER else "bambu-connect"
                    winreg.CloseKey(winreg.OpenKey(root, key))
                    return True
                except OSError:
                    continue
        except ImportError:
            pass
        for p in (os.path.expandvars(r"%LOCALAPPDATA%\Programs\Bambu Connect"),
                  r"C:\Program Files\Bambu Connect"):
            if os.path.isdir(p):
                return True
        return False
    return os.path.isdir("/Applications/Bambu Connect.app")


def fallback_route():
    """Where starts go once the printer refuses network starts: Bambu Connect
    if it's installed, otherwise Bambu Studio — both are signed by Bambu, so
    their Print buttons still work."""
    return "bambu_connect" if bambu_connect_installed() else "studio"


def studio_warning():
    """Why pressing Print in the installed Studio won't start anything, or ""."""
    v = bs["installed_studio_version"](bs["find_studio"](read_config().get("studio_exe", "")))
    return bs["STUDIO_TOO_OLD"] % v if bs["studio_can_print"](v) is False else ""


def start(path, plate=1, approval_code="", slots=None, _send=None, _upload=None,
          _status=None):
    """
    Start a sliced file. On the default route: re-check the printer, upload
    the file over the home network, and start it through Bambu Cloud.
    Needs the approval code from the preview when approval is on.
    """
    path = os.path.abspath(path)
    r = route()
    if r == "bambu_connect":
        return open_bambu_connect(path)
    if r == "studio":
        out = bs["open_in_studio"](path)
        out["route"] = "studio"
        warn = studio_warning()
        if warn:
            out["warning"] = warn
        return out

    if needs_approval():
        entry = redeem_code(approval_code, path, plate)
        mapping = entry["mapping"]
    else:
        mapping = None

    st = (_status or bc["printer_status"])()
    if st.get("state") not in IDLE_STATES:
        raise PrintError("Not starting: the printer is %s." % st.get("state"))
    if mapping is None:
        pv = preview(path, plate, slots, status=st)
        if pv["problems"]:
            raise PrintError("Not starting: " + "; ".join(pv["problems"]))
        mapping = pv["ams_mapping"]

    up = (_upload or bl["upload"])(path, serial=st.get("serial") or "")
    name = up["name"]
    use_ams = any(v not in (-1, EXTERNAL_SPOOL) for v in mapping)
    payload = bc["command_payload"](
        "project_file",
        param="Metadata/plate_%d.gcode" % plate,
        url="file:///sdcard/%s" % name,
        subtask_name=os.path.splitext(name)[0],
        bed_type="auto",
        use_ams=use_ams,
        ams_mapping=mapping if use_ams else [],
        profile_id="0", project_id="0", subtask_id="0", task_id="0",
        **START_OPTIONS)
    sent = (_send or bc["send_command"])(payload, serial=st.get("serial") or "",
                                         wait_s=12)
    echo = sent.get("echo") or {}
    started = echo.get("result") == "success" or sent.get("state") in (
        "PREPARE", "RUNNING", "SLICING")
    out = {"ok": started, "route": "lan_cloud", "uploaded_as": name,
           "printer_ip": up["ip"], "echo": echo, "state": sent.get("state"),
           "ams_mapping": mapping}
    # An echo carrying an err_code is an answer — a refusal — even with no
    # result or reason in it.
    refused = echo.get("result") == "fail" or bool(echo.get("err_code"))

    if not started and (refused or looks_like_authorization(echo, sent.get("fun"))):
        if looks_like_authorization(echo, sent.get("fun")):
            new = fallback_route()
            if echo.get("err_code"):
                why = ("err_code %s — MQTT command verification failed"
                       % echo.get("err_code"))
            else:
                why = echo.get("reason") or "authorization"
            set_route(new, "the printer refused a network start (%s)" % why)
            out["route_switched"] = new
            where = {"bambu_connect": "Bambu Connect",
                     "studio": "Bambu Studio"}[new]
            out["error"] = ("The printer refused to start over the network "
                            "(MQTT command verification failed) — Bambu's "
                            "authorization lockdown has reached this P1S's "
                            "firmware. Prints now start from %s, which Bambu "
                            "signs; it has been opened with this file — press "
                            "Print there. The route is saved, so the next start "
                            "goes straight there." % where)
            out["opened"] = open_bambu_connect(path) if new == "bambu_connect" \
                else bs["open_in_studio"](path)
            if new == "studio" and studio_warning():
                out["warning"] = studio_warning()
        else:
            out["error"] = "The printer said no: %s" % (echo.get("reason") or echo)
    elif not started:
        out["error"] = ("No answer from the printer within 12 s. The file is on "
                        "its SD card as %s; check the printer's screen before "
                        "trying again." % name)
    return out


CONTROL_ELSEWHERE = ("Use Bambu Studio's Device tab, Handy, or the printer's "
                     "screen.")


def _control(command, serial="", retry=False):
    """
    Send pause / resume / stop over the cloud. Once the printer has refused
    one (its firmware wants commands signed by Bambu's own apps), later calls
    don't send anything — they say where to do it instead, straight away.
    retry=True sends anyway, to see whether a firmware change lifted it.
    """
    cfg = read_config()
    refused = cfg.get("control_refused")
    if refused and not retry:
        return {"ok": False, "command": command, "sent": False,
                "refused_since": refused.get("when"),
                "error": ("Not sent: this printer refuses %s from the tools "
                          "(MQTT command verification failed, first seen %s). "
                          "%s" % (command, refused.get("when", "earlier"),
                                  CONTROL_ELSEWHERE))}
    sent = bc["send_command"](bc["command_payload"](command), serial=serial)
    echo = sent.get("echo") or {}
    ok = not echo.get("err_code") and (echo.get("result") == "success" or (
        command == "pause" and sent.get("state") == "PAUSE") or (
        command == "resume" and sent.get("state") == "RUNNING") or (
        command == "stop" and sent.get("state") in ("IDLE", "FAILED", "FINISH")))
    out = {"ok": ok, "command": command, "sent": True, "echo": echo,
           "state": sent.get("state")}
    if ok and refused:
        cfg.pop("control_refused", None)            # the lockdown lifted
        write_config(cfg)
    if not ok:
        out["error"] = ("The printer didn't confirm %s (%s). Check its screen."
                        % (command, echo.get("reason") or "no answer"))
        if looks_like_authorization(echo, sent.get("fun")):
            out["error"] = ("The printer refused %s (MQTT command verification "
                            "failed) — this firmware only takes control commands "
                            "signed by Bambu's own apps. %s"
                            % (command, CONTROL_ELSEWHERE))
            cfg["control_refused"] = {
                "when": datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
                "command": command,
                "err_code": echo.get("err_code")}
            write_config(cfg)
    return out


def pause(serial="", retry=False):
    """Pause the running print. No approval needed (04 section 7)."""
    return _control("pause", serial, retry)


def resume(serial="", retry=False):
    """Resume a paused print. No approval needed."""
    return _control("resume", serial, retry)


def stop(confirm=False, serial="", retry=False):
    """Stop the print for good — it can't be resumed. Needs a yes (04 section
    7): pass confirm=True only after the person said yes to stopping it."""
    if needs_approval() and not confirm:
        raise PrintError("Stopping a print needs a yes first (04 section 7). "
                         "It can't be undone.")
    return _control("stop", serial, retry)


# ── the other routes ─────────────────────────────────────────────────

def bambu_connect_url(path, name=None):
    """Bambu Connect's documented hand-off link."""
    return "bambu-connect://import-file?path=%s&name=%s&version=1.0.0" % (
        urllib.parse.quote(os.path.abspath(path), safe=""),
        urllib.parse.quote(name or os.path.splitext(os.path.basename(path))[0]
                           .replace(".gcode", ""), safe=""))


def open_bambu_connect(path):
    url = bambu_connect_url(path)
    try:
        if os.name == "nt":
            os.startfile(url)                      # noqa — Windows only
        elif sys.platform == "darwin":
            subprocess.Popen(["open", url])
        else:
            webbrowser.open(url)
    except OSError as exc:
        return {"ok": False, "route": "bambu_connect", "url": url,
                "error": "Couldn't open Bambu Connect (%s). Is it installed?" % exc}
    return {"ok": True, "route": "bambu_connect", "url": url,
            "note": "Bambu Connect is open with the file: pick the plate, then "
                    "Print → Send. Nothing has started until you do."}


# ── MakerWorld files set up for an X1 ────────────────────────────────

# Every setting that belongs to the printer rather than the process or the
# filament: the union of the keys in Bambu's own machine profiles for the P1S
# and X1 Carbon (0.4 nozzle) and everything they inherit, BambuStudio
# v01.09.07.52, resources/profiles/BBL/machine.
MACHINE_KEYS = (
    "auxiliary_fan", "bed_exclude_area", "best_object_pos", "change_filament_gcode",
    "deretraction_speed", "enable_long_retraction_when_cut",
    "extruder_clearance_height_to_lid", "extruder_clearance_height_to_rod",
    "extruder_clearance_max_radius", "extruder_clearance_radius", "extruder_colour",
    "extruder_offset", "gcode_flavor", "layer_change_gcode",
    "long_retractions_when_cut", "machine_end_gcode", "machine_load_filament_time",
    "machine_max_acceleration_e", "machine_max_acceleration_extruding",
    "machine_max_acceleration_retracting", "machine_max_acceleration_travel",
    "machine_max_acceleration_x", "machine_max_acceleration_y",
    "machine_max_acceleration_z", "machine_max_jerk_e", "machine_max_jerk_x",
    "machine_max_jerk_y", "machine_max_jerk_z", "machine_max_speed_e",
    "machine_max_speed_x", "machine_max_speed_y", "machine_max_speed_z",
    "machine_min_extruding_rate", "machine_min_travel_rate", "machine_pause_gcode",
    "machine_start_gcode", "machine_unload_filament_time", "max_layer_height",
    "min_layer_height", "nozzle_diameter", "nozzle_height", "nozzle_type",
    "nozzle_volume", "printable_area", "printable_height", "printer_model",
    "printer_settings_id", "printer_structure", "printer_technology",
    "printer_variant", "retract_before_wipe", "retract_length_toolchange",
    "retract_lift_below", "retract_restart_extra", "retract_restart_extra_toolchange",
    "retract_when_changing_layer", "retraction_distances_when_cut",
    "retraction_length", "retraction_minimum_travel", "retraction_speed",
    "scan_first_layer", "silent_mode", "single_extruder_multi_material",
    "support_air_filtration", "support_chamber_temp_control",
    "upward_compatible_machine", "wipe", "z_hop", "z_hop_types",
)
ABRASIVE = ("CF", "GF", "-CF", "-GF", "PAHT")
SLICED_ENTRY = re.compile(r"^Metadata/(plate_\d+\.gcode(\.md5)?|slice_info\.config|"
                          r"_rels/model_settings\.config\.rels)$")


def retarget_to_p1s(path, out_path=None, template=None):
    """
    Re-target a 3MF set up for another Bambu printer (usually an X1, from
    MakerWorld) to the P1S. Writes a new file beside it; the original is not
    touched. If the file was already sliced, the sliced G-code is removed —
    it was made for the other printer — and it needs slicing again.
    """
    path = os.path.abspath(path)
    if not os.path.isfile(path):
        raise PrintError("No file at %s" % path)
    template = template or bpre["template_path"](ROOT)
    if not os.path.isfile(template):
        raise PrintError("Re-targeting needs tools/bambu_template.3mf — the "
                         "P1S settings are copied from it.")
    p1s = b3["read_project_settings"](template)
    if p1s.get("printer_model") != bpre["PRINTER_MODEL"]:
        raise PrintError("tools/bambu_template.3mf is set up for %r, not the P1S."
                         % p1s.get("printer_model"))
    try:
        src = b3["read_project_settings"](path)
    except Exception as exc:
        raise PrintError("%s isn't a Bambu project file (%s)." % (
            os.path.basename(path), exc))

    was = {"printer": src.get("printer_settings_id") or src.get("printer_model"),
           "model": src.get("printer_model")}
    if src.get("printer_model") == bpre["PRINTER_MODEL"] and \
            src.get("printer_settings_id") == p1s.get("printer_settings_id"):
        return {"ok": True, "changed": False, "file": path,
                "note": "Already set up for the P1S — nothing to do."}

    new = dict(src)
    changed = []
    for key in MACHINE_KEYS:
        if key in p1s and new.get(key) != p1s[key]:
            changed.append(key)
            new[key] = p1s[key]
    for key in ("inherits_group", "different_settings_to_system"):
        vals = new.get(key)
        if isinstance(vals, list) and vals:
            vals = list(vals)
            vals[-1] = ""                           # the printer's entry
            new[key] = vals

    notes = []
    proc = new.get("print_settings_id", "")
    if proc and "@BBL X1C" not in proc and "@BBL P1S" not in proc:
        notes.append("process preset %r may not be meant for the P1S; check it "
                     "in Studio" % proc)
    if re.search(r"\b0\.[268] nozzle", proc):
        notes.append("process preset %r is for a different nozzle size" % proc)
    fils = new.get("filament_settings_id") or []
    x1_only = [f for f in fils if "@BBL X1" in f and "@BBL X1C" not in f]
    if x1_only:
        notes.append("filament preset(s) %s are X1-specific; pick the P1S ones in "
                     "Studio if they differ" % ", ".join(sorted(set(x1_only))))
    types = [t.upper() for t in (new.get("filament_type") or [])]
    if any(any(a in t for a in ABRASIVE) for t in types) and \
            "stainless" in str(p1s.get("nozzle_type", "")):
        notes.append("the file uses abrasive filament (%s) and the P1S has a "
                     "stainless-steel nozzle — it will wear it; a hardened nozzle "
                     "is recommended" % ", ".join(sorted(set(types))))
    ver = b3["read_application"](path)
    notes_version = ""
    tver = b3["read_application"](template)
    if ver and tver and ver.split("-")[-1][:5] > tver.split("-")[-1][:5]:
        notes_version = ("it was saved by %s, newer than your Studio (%s); "
                         "slicing it needs allow_newer" % (ver, tver))
        notes.append(notes_version)

    if not out_path:
        stem = os.path.splitext(path)[0]
        if stem.lower().endswith(".gcode"):
            stem = stem[:-6]
        n, out_path = 1, stem + "_P1S.3mf"
        while os.path.exists(out_path):
            n += 1
            out_path = "%s_P1S_%d.3mf" % (stem, n)

    removed = []
    # Studio writes slice_info.config into unsliced projects too; plate G-code
    # is the real sign a file was sliced.
    with zipfile.ZipFile(path) as zin:
        was_sliced = any(re.match(r"^Metadata/plate_\d+\.gcode$", n)
                         for n in zin.namelist())
    with zipfile.ZipFile(path) as zin, zipfile.ZipFile(
            out_path, "w", zipfile.ZIP_DEFLATED) as zout:
        for info in zin.infolist():
            name = info.filename
            if was_sliced and SLICED_ENTRY.match(name):
                removed.append(name)
                continue
            data = zin.read(name)
            if name == "Metadata/project_settings.config":
                data = json.dumps(new, indent=4).encode("utf-8")
            elif name == "Metadata/model_settings.config" and was_sliced:
                data = re.sub(rb'\s*<metadata key="(gcode_file|pattern_bbox_file)" '
                              rb'value="[^"]*"/>', b"", data)
            zout.writestr(info, data)
    if removed:
        notes.append("it was sliced for the other printer; that G-code was "
                     "removed — slice this file again before printing")
    return {"ok": True, "changed": True, "file": out_path, "was": was,
            "now": p1s.get("printer_settings_id"),
            "machine_settings_replaced": len(changed),
            "start_gcode_replaced": "machine_start_gcode" in changed,
            "sliced_parts_removed": removed, "notes": notes,
            "needs_allow_newer": bool(notes_version)}


def format_retarget(r):
    if not r.get("changed"):
        return r.get("note", "Nothing to do.")
    lines = ["Re-targeted to the P1S: %s" % os.path.basename(r["file"]),
             "  was %s, now %s" % (r["was"]["printer"], r["now"]),
             "  %d printer settings replaced%s" % (
                 r["machine_settings_replaced"],
                 ", including the start G-code" if r["start_gcode_replaced"] else "")]
    for n in r["notes"]:
        lines.append("  note: " + n)
    return "\n".join(lines)


def _cli(argv):
    cmd = argv[1] if len(argv) > 1 else ""
    try:
        if cmd == "preview" and len(argv) > 2:
            plate = int(argv[3]) if len(argv) > 3 else 1
            print(format_preview(preview(argv[2], plate)))
        elif cmd == "retarget" and len(argv) > 2:
            print(format_retarget(retarget_to_p1s(argv[2])))
        elif cmd == "route":
            if len(argv) > 2:
                print(set_route(argv[2], "set by hand"))
            else:
                print(route())
        elif cmd == "start" and len(argv) == 3 and route() != "lan_cloud":
            # Studio / Bambu Connect: you press Print there — no code needed.
            print(json.dumps(start(argv[2], 1, ""), indent=2))
        elif cmd == "start" and len(argv) <= 3:
            print("Usage: start <file.gcode.3mf> <approval code from the preview> "
                  "[plate]")
            return 2
        elif cmd == "start" and len(argv) > 3:
            plate = int(argv[4]) if len(argv) > 4 else 1
            r = start(argv[2], plate, argv[3])
            print(json.dumps(r, indent=2))
        elif cmd == "stop":
            if "--yes" not in argv:
                print("Stopping can't be undone. Run `stop --yes` to stop the print.")
                return 1
            print(json.dumps(stop(confirm=True, retry="--retry" in argv), indent=2))
        elif cmd in ("pause", "resume"):
            retry = "--retry" in argv
            print(json.dumps(pause(retry=retry) if cmd == "pause"
                             else resume(retry=retry), indent=2))
        else:
            print(__doc__)
            return 2
    except (PrintError, bc["CloudError"], bl["LanError"]) as exc:
        print("Couldn't: %s" % exc)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(_cli(sys.argv))
