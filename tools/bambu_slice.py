"""
Project Bonfire — Bambu Layer B: slicing.

Runs Bambu Studio's command-line slicer on a project 3MF, saves the sliced
`.gcode.3mf` beside it (04_bambu_basics.md section 7), and reads back what the
slice actually cost: print time, filament per slot, whether support was used,
and any warnings.

    import os, runpy
    bs = runpy.run_path(os.path.join(ROOT, "tools", "bambu_slice.py"))
    print(bs["format_slice_report"](bs["slice_file"](r"...\\3mf\\thing_1.3mf")))

Slicing is allowed without asking (04 section 7). Nothing here starts a print.

Two things worth knowing, both learned from BambuStudio's own source:

  * **`result.json` is the machine-readable answer, not stdout.** The CLI writes
    it on success *and* on failure, with the real return code, an error string,
    and the per-plate warning that catches "floating regions … enable support
    generation". Warnings like that never reach `slice_info.config`.
  * **Exit codes are negative, and a shell only keeps the low byte.** -104
    arrives as 152. They are converted back here, but `result.json`'s
    `return_code` is the unmodified one and is trusted first.

`--load-settings` is deliberately not used: the preset JSONs in Studio's system
folder are diffs against a non-instantiated parent, and the CLI can't always
resolve them (BambuStudio issue #2889). Everything is baked into the 3MF by
`bambu_3mf.py` instead, which is the reliable path.
"""
import glob
import json
import os
import re
import runpy
import shutil
import subprocess
import tempfile
import xml.etree.ElementTree as ET
import zipfile

SLICE_TIMEOUT_S = 900          # a big plate on a slow machine
DEBUG_LEVEL = 2                # 2 = warnings, which is where the useful ones are

# From BambuStudio src/libslic3r/Utils.hpp — only the ones worth explaining.
EXIT_CODES = {
    0: "success",
    -1: "Bambu Studio couldn't start (environment error).",
    -2: "The slicer rejected the arguments.",
    -3: "The slicer couldn't find the file.",
    -4: "The Bambu 3MF has to be the first file on the command line.",
    -5: "A preset file is broken or missing.",
    -6: "The model file couldn't be parsed.",
    -13: "Exporting the sliced 3MF failed.",
    -14: "The slicer ran out of memory.",
    -17: "The process preset isn't compatible with the printer preset.",
    -18: "The 3MF has values the slicer won't accept.",
    -21: "Arranging the plate failed.",
    -22: "Orienting failed.",
    -24: "The 3MF was written by a newer Bambu Studio than the one installed. "
         "Retry with allow_newer=True, or update Bambu Studio.",
    -50: "Nothing to slice — the plate is empty, or nothing is fully inside "
         "the print volume.",
    -51: "The slicer's own validation failed.",
    -52: "Something hangs over the edge of the bed.",
    -58: "Slicing took longer than the slicer's own limit.",
    -59: "Too many triangles.",
    -61: "The filament doesn't match the bed type.",
    -62: "Two filaments need temperatures too far apart to print together.",
    -63: "Objects collide in sequential (one-at-a-time) printing.",
    -64: "Objects collide.",
    -66: "A filament can't be mapped to any AMS slot.",
    -100: "Slicing failed.",
    -101: "The toolpaths conflict.",
    -102: "Some toolpath lands where the printer can't print.",
    -104: "Some toolpath falls outside the printable area.",
}

# The warnings that reach slice_info.config, in plain words. The set differs
# between Studio versions; an unknown one is shown as-is.
SLICE_WARNINGS = {
    # Studio 1.9: the bed is hotter than the filament's softening point
    # (PLA: bed 55 C, vitrification 45 C), which in a closed P1S can cook the
    # filament in the nozzle. Normal for every PLA print; the bed temperature
    # itself is a locked setting (04 section 2), so this is advice, not a fix.
    "bed_temperature_too_high_than_filament":
        "The bed runs hotter than this filament's softening point, which can "
        "clog the nozzle in a closed printer. Open the front door and/or take "
        "the top glass off for this print.",
    "the_actual_nozzle_hrc_smaller_than_the_required_nozzle_hrc":
        "This filament is more abrasive than the nozzle is rated for.",
    "not_support_traditional_timelapse":
        "Traditional timelapse isn't possible with this plate.",
    "not_generate_timelapse": "No timelapse will be generated.",
    "smooth_timelapse_without_prime_tower":
        "Smooth timelapse without a prime tower may leave marks.",
    "activate_long_retraction_when_cut":
        "Long retraction when cutting is on.",
}


# Warnings the user has decided not to see (04_bambu_basics.md section 8).
# They are still kept in the report data under "warnings", marked ignored;
# they just aren't printed.
IGNORED_WARNINGS = {
    # 2026-09-19: bed temperatures are set deliberately and have never been
    # changed; the PLA-in-a-closed-printer reminder isn't wanted.
    "bed_temperature_too_high_than_filament",
}


# ── finding the slicer ───────────────────────────────────────────────

def find_studio(configured=""):
    """Bambu Studio's executable, or "" if it isn't installed here."""
    for candidate in (configured, os.environ.get("BAMBU_STUDIO_PATH", "")):
        if candidate and os.path.isfile(candidate):
            return candidate
    guesses = [
        r"C:\Program Files\Bambu Studio\bambu-studio.exe",
        r"C:\Program Files (x86)\Bambu Studio\bambu-studio.exe",
        os.path.expanduser(r"~\AppData\Local\Programs\Bambu Studio\bambu-studio.exe"),
        "/Applications/BambuStudio.app/Contents/MacOS/BambuStudio",
        "/usr/bin/bambu-studio",
        "/usr/local/bin/bambu-studio",
    ]
    guesses += glob.glob(os.path.expanduser(
        r"~\AppData\Local\Programs\Bambu*Studio\bambu-studio.exe"))
    for g in guesses:
        if os.path.isfile(g):
            return g
    return shutil.which("bambu-studio") or ""


def _windows_file_version(exe):
    """The version stamped into a Windows .exe (what Explorer's Details tab
    shows), as 02.08.02.61. Needs no Studio run at all."""
    if os.name != "nt":
        return ""
    try:
        import ctypes
        from ctypes import wintypes
        ver = ctypes.WinDLL("version")
        size = ver.GetFileVersionInfoSizeW(exe, None)
        if not size:
            return ""
        buf = ctypes.create_string_buffer(size)
        if not ver.GetFileVersionInfoW(exe, 0, size, buf):
            return ""
        ptr, n = ctypes.c_void_p(), wintypes.UINT()
        if not ver.VerQueryValueW(buf, "\\", ctypes.byref(ptr), ctypes.byref(n)):
            return ""
        # VS_FIXEDFILEINFO: signature, struct version, then file version MS, LS
        ms, ls = ctypes.cast(ptr, ctypes.POINTER(wintypes.DWORD * 4)).contents[2:4]
        parts = (ms >> 16, ms & 0xFFFF, ls >> 16, ls & 0xFFFF)
        return ".".join("%02d" % p for p in parts) if any(parts) else ""
    except Exception:
        return ""


def studio_version(exe):
    """The installed version, or "" if it won't say."""
    v = _windows_file_version(exe)
    if v:
        return v
    try:
        out = subprocess.run([exe, "--info"], capture_output=True, text=True,
                             timeout=60)
        text = (out.stdout or "") + (out.stderr or "")
        m = (re.search(r"Version (\d{2}\.\d{2}\.\d{2}\.\d{2})", text)
             or re.search(r"(\d{2}\.\d{2}\.\d{2}\.\d{2})", text))
        return m.group(1) if m else ""
    except Exception:
        return ""


# Printer firmware from 2025 on only obeys start/stop commands that carry
# Bambu's signature. Studio 1.9.x predates that: its cloud send succeeds (the
# job lands in Handy's history as "printing") but the printer drops the start
# command and nothing happens. Seen here with 01.09.07.52 on 2026-09-19.
MIN_PRINTING_VERSION = "02.00.00.00"


def version_tuple(v):
    return tuple(int(x) for x in re.findall(r"\d+", v or "")[:4])


def studio_can_print(version):
    """True / False, or None when the version is unknown."""
    if not version:
        return None
    return version_tuple(version) >= version_tuple(MIN_PRINTING_VERSION)


def installed_studio_version(exe=""):
    """The version, from `--info` or failing that Studio's own newest log."""
    v = studio_version(exe) if exe else ""
    if v:
        return v
    folder = studio_log_folder()
    logs = sorted(glob.glob(os.path.join(folder, "debug_*.log.0")),
                  key=os.path.getmtime) if folder else []
    if exe and os.path.isfile(exe):
        # A log written before Studio was last installed describes the old one.
        installed = os.path.getmtime(exe)
        logs = [l for l in logs if os.path.getmtime(l) >= installed]
    for log in reversed(logs[-3:]):
        try:
            with open(log, "r", encoding="utf-8", errors="replace") as fh:
                for _ in range(20):
                    m = re.search(r"BambuStudio Version (\d{2}\.\d{2}\.\d{2}\.\d{2})",
                                  fh.readline())
                    if m:
                        return m.group(1)
        except OSError:
            continue
    return ""


STUDIO_TOO_OLD = ("Bambu Studio %s is too old to start prints on this printer: "
                  "the send goes through (Handy's history shows it \"printing\") "
                  "but the printer ignores the start. Update Bambu Studio to the "
                  "latest release (Help → Check for updates, or bambulab.com/"
                  "download) and send again.")


def signed(code):
    """
    Negative exit codes arrive unsigned, and how depends on the OS:
    Unix keeps only the low byte (-104 -> 152); Windows keeps all 32 bits
    (-357 -> 4294966939).
    """
    if code is None:
        return None
    if code > 0x7FFFFFFF:
        return code - 0x100000000
    if 127 < code < 256 and os.name != "nt":
        return code - 256
    return code


# A Windows process that died from an exception, rather than exiting on
# purpose, reports an NTSTATUS code. These are the common ones.
NTSTATUS = {
    -1073741819: "Bambu Studio crashed (access violation, 0xC0000005).",
    -1073740791: "Bambu Studio crashed (stack buffer overrun, 0xC0000409).",
    -1073741571: "Bambu Studio crashed (stack overflow, 0xC00000FD).",
    -1073741515: "A DLL Bambu Studio needs is missing (0xC0000135).",
    -1073741510: "Bambu Studio was stopped (Ctrl+C / close, 0xC000013A).",
}


def studio_log_folder():
    """Where Bambu Studio writes its own logs — the place to look when the
    command line gives no reason."""
    for folder in (os.path.expandvars(r"%APPDATA%\BambuStudio\log"),
                   os.path.expanduser("~/Library/Application Support/BambuStudio/log"),
                   os.path.expanduser("~/.config/BambuStudio/log")):
        if os.path.isdir(folder):
            return folder
    return ""


def explain_code(code, result):
    """The best explanation available for a non-zero exit."""
    if result.get("error_string"):
        return result["error_string"]
    if code in EXIT_CODES:
        return EXIT_CODES[code]
    if code in NTSTATUS:
        return NTSTATUS[code]
    return ("Bambu Studio stopped with code %s and left no result.json, so it "
            "didn't finish through its own error handling — usually a crash "
            "inside the slicer. Its own log will say why." % code)


# ── naming the output ────────────────────────────────────────────────

def next_sliced_path(project_3mf):
    """
    `<name>_<n>.gcode.3mf` beside the project 3MF (04 section 7), never
    overwriting. `thing_2.3mf` gives `thing_2_1.gcode.3mf`, so it is always
    clear which project file a sliced file came from.
    """
    folder = os.path.dirname(os.path.abspath(project_3mf))
    stem = os.path.basename(project_3mf)
    for suffix in (".gcode.3mf", ".3mf"):
        if stem.lower().endswith(suffix):
            stem = stem[: -len(suffix)]
            break
    n = 1
    while os.path.exists(os.path.join(folder, "%s_%d.gcode.3mf" % (stem, n))):
        n += 1
    return os.path.join(folder, "%s_%d.gcode.3mf" % (stem, n))


# ── running the slicer ───────────────────────────────────────────────

def slice_file(project_3mf, plate=0, out_path=None, studio_exe="",
               timeout=SLICE_TIMEOUT_S, allow_newer=False, extra_args=None):
    """
    Slice a Bambu project 3MF.

    plate: 0 for every plate, or a 1-based plate number.
    Returns a report dict; `ok` says whether it sliced.
    """
    project_3mf = os.path.abspath(project_3mf)
    if not os.path.isfile(project_3mf):
        return {"ok": False, "error": "No file at %s" % project_3mf}

    exe = find_studio(studio_exe)
    if not exe:
        return {"ok": False, "error":
                "Bambu Studio isn't installed here, or isn't where I looked. "
                "Set BAMBU_STUDIO_PATH in .env, or studio_exe in "
                "tools/bambu_config.json.",
                "needs": "bambu-studio.exe"}

    out_path = os.path.abspath(out_path or next_sliced_path(project_3mf))
    os.makedirs(os.path.dirname(out_path), exist_ok=True)

    run = _run_studio(exe, ["--slice", str(int(plate))], project_3mf, out_path,
                      timeout, allow_newer, extra_args, "slicing")
    if "error" in run and "proc" not in run:
        return {"ok": False, "error": run["error"], "command": run["command"]}
    proc, result, code, work = run["proc"], run["result"], run["code"], run["work"]
    args = run["command"]

    report = {
        "ok": code == 0 and os.path.isfile(out_path),
        "return_code": code,
        "project_3mf": project_3mf,
        "file": out_path if os.path.isfile(out_path) else None,
        "slicer": exe,
        "command": args,
    }
    if code != 0:
        report["error"] = explain_code(code, result)
        said = _studio_errors(proc)
        if said and not result.get("error_string"):
            report["error"] = "%s Bambu Studio said: %s" % (
                EXIT_CODES.get(code, "Slicing failed."), " / ".join(said))
        if code == -24 and not allow_newer:
            report["retry_hint"] = "Retry with allow_newer=True."
        _attach_diagnostics(report, proc, result, work)
    elif not os.path.isfile(out_path):
        report["ok"] = False
        report["error"] = ("Bambu Studio reported success but wrote no file to "
                           "%s." % out_path)

    warnings = []
    for p in result.get("sliced_plates", []) or []:
        msg = (p.get("warning_message") or "").strip()
        if msg:
            warnings.append(msg)
    if warnings:
        report["slicer_warnings"] = warnings

    if report["ok"]:
        report.update(read_slice_info(out_path))
        shutil.rmtree(work, ignore_errors=True)
    return report


def _studio_errors(proc):
    """Studio's own [error] lines. Version 1.9 doesn't always write
    result.json on a slicing failure, but it does print these."""
    out = []
    for line in ((proc.stdout or "") + "\n" + (proc.stderr or "")).splitlines():
        if "[error]" in line:
            msg = line.split("[error]", 1)[1].strip()
            if msg and msg not in out:
                out.append(msg)
    return out


def _attach_diagnostics(report, proc, result, work):
    """Everything worth having when a run fails: the ends of stdout and
    stderr (the CLI prints "<function> found error" to stdout), whether
    result.json existed, the scratch folder — kept, not deleted — and where
    Studio's own log is."""
    for name in ("stdout", "stderr"):
        lines = (getattr(proc, name, "") or "").strip().splitlines()
        if lines:
            report["%s_tail" % name] = lines[-12:]
    report["result_json_written"] = bool(result)
    if result:
        report["result_json"] = {
            "return_code": result.get("return_code"),
            "error_string": result.get("error_string"),
            "warnings": [p.get("warning_message") for p in
                         result.get("sliced_plates", []) or []
                         if p.get("warning_message")],
        }
    report["scratch_folder"] = work
    log = studio_log_folder()
    if log:
        report["studio_log_folder"] = log


def _run_studio(exe, action_args, project_3mf, out_path, timeout,
                allow_newer, extra_args, doing):
    """
    Run the CLI with a scratch --outputdir and bring the exported 3MF back to
    out_path.

    The CLI joins --outputdir onto the --export-3mf name *even when that name
    is an absolute path* (BambuStudio.cpp: `export_3mf_file = outfile_dir +
    "/" + export_3mf_file`). So the export is given a bare file name, lands in
    the scratch folder beside result.json, and is moved into place afterwards.
    """
    work = tempfile.mkdtemp(prefix="bonfire_studio_")
    name = os.path.basename(out_path)
    args = [exe] + list(action_args) + [
        "--debug", str(DEBUG_LEVEL), "--outputdir", work, "--export-3mf", name]
    if allow_newer:
        args.append("--allow-newer-file")
    args += list(extra_args or [])
    args.append(project_3mf)                 # the BBL 3MF must come last

    try:
        proc = subprocess.run(args, capture_output=True, text=True,
                              timeout=timeout, cwd=work)
    except subprocess.TimeoutExpired:
        shutil.rmtree(work, ignore_errors=True)
        return {"error": "Bambu Studio didn't finish %s within %d seconds."
                         % (doing, timeout), "command": args}
    except OSError as exc:
        shutil.rmtree(work, ignore_errors=True)
        return {"error": "Couldn't run Bambu Studio: %s" % exc, "command": args}

    result = read_result_json(work)
    code = result.get("return_code")
    if code is None:
        code = signed(proc.returncode)

    # Where the export can land, most likely first.
    for candidate in (os.path.join(work, name), out_path):
        if os.path.isfile(candidate):
            if os.path.abspath(candidate) != os.path.abspath(out_path):
                shutil.move(candidate, out_path)
            break
    return {"proc": proc, "result": result, "code": code, "work": work,
            "command": args}


def studio_arrange(project_3mf, out_path=None, studio_exe="",
                   allow_rotations=True, timeout=300, allow_newer=False):
    """
    Lay out the plate with Bambu Studio's own Arrange — the button in the GUI —
    and save the result as a project 3MF. Nothing is sliced.

    Orientation is left exactly as it is (`--orient 0`), so the way-up chosen
    by 04 section 3 survives; Arrange only moves parts around the plate and,
    with allow_rotations, turns them about the vertical axis.

    Studio's command line always uses its default object spacing (it sets
    min_obj_distance to 0 and spaces by brim width), so there is no spacing
    option here. Use bambu.arrange_plate for a custom spacing.
    """
    project_3mf = os.path.abspath(project_3mf)
    if not os.path.isfile(project_3mf):
        return {"ok": False, "error": "No file at %s" % project_3mf}
    exe = find_studio(studio_exe)
    if not exe:
        return {"ok": False, "error": "Bambu Studio isn't installed here.",
                "needs": "bambu-studio.exe"}

    in_place = out_path is None or \
        os.path.abspath(out_path) == project_3mf
    target = os.path.abspath(out_path or project_3mf)
    temp_out = target + ".arranging" if in_place else target

    action = ["--arrange", "1", "--orient", "0"]
    if not allow_rotations:
        action += ["--allow-rotations", "0"]
    run = _run_studio(exe, action, project_3mf, temp_out, timeout,
                      allow_newer, None, "arranging")
    if "proc" not in run:
        return {"ok": False, "error": run["error"], "command": run["command"]}
    code, result, work = run["code"], run["result"], run["work"]

    if code != 0 or not os.path.isfile(temp_out):
        if os.path.isfile(temp_out) and in_place:
            os.remove(temp_out)
        error = explain_code(code, result)
        if code == 0:
            error = "Bambu Studio reported success but wrote no file."
        out = {"ok": False, "return_code": code, "error": error,
               "command": run["command"]}
        _attach_diagnostics(out, run["proc"], result, work)
        return out

    shutil.rmtree(work, ignore_errors=True)
    lost = settings_lost(project_3mf, temp_out)
    if in_place:
        os.replace(temp_out, target)
    return {"ok": True, "file": target, "return_code": code,
            "settings_lost": lost, "command": run["command"]}


PER_PART_KEYS = ("enable_support", "support_type",
                 "support_on_build_plate_only", "raft_layers", "extruder")


def _object_settings(path_3mf):
    """{object name: {key: value}} from Metadata/model_settings.config."""
    try:
        with zipfile.ZipFile(path_3mf) as z:
            root = ET.fromstring(z.read("Metadata/model_settings.config"))
    except Exception:
        return {}
    out = {}
    for obj in root.findall("object"):
        meta = {m.get("key"): m.get("value") for m in obj.findall("metadata")
                if m.get("key")}
        name = os.path.splitext(meta.get("name", ""))[0]
        out[name] = {k: meta[k] for k in PER_PART_KEYS if k in meta}
    return out


def settings_lost(before_3mf, after_3mf):
    """
    Per-part settings (supports, raft, AMS slot) that were in the file before
    Studio rewrote it and aren't after. Studio round-trips a project it loaded
    exactly as a GUI save would, so this should come back empty — it is here
    so that if a Studio update ever changes that, it's reported rather than
    silently printing without the raft.
    """
    before, after = _object_settings(before_3mf), _object_settings(after_3mf)
    lost = []
    for name, keys in before.items():
        now = after.get(name, {})
        for key, value in keys.items():
            if now.get(key) != value:
                lost.append("%s %s (was %s, now %s)"
                            % (name, key, value, now.get(key, "unset")))
    return lost


def read_result_json(folder):
    """
    The CLI's own machine-readable summary. It carries the *unmodified* return
    code and the per-plate warning that says a part has floating regions and
    wants support turned on — which never reaches slice_info.config.
    """
    for name in ("result.json",):
        path = os.path.join(folder, name)
        if os.path.isfile(path):
            try:
                with open(path, encoding="utf-8") as fh:
                    return json.load(fh)
            except Exception:
                return {}
    return {}


# ── reading the slice back ───────────────────────────────────────────

def read_slice_info(gcode_3mf):
    """
    Metadata/slice_info.config out of a sliced 3MF. It is XML despite the
    extension (project_settings.config in the same archive is JSON).

    Note that `<filament id>` is 1-based and sparse — only filaments that
    actually extruded appear — so slots are read by id, never by position.
    """
    try:
        with zipfile.ZipFile(gcode_3mf) as z:
            if "Metadata/slice_info.config" not in z.namelist():
                return {"sliced": False,
                        "note": "No slice_info.config — this file isn't sliced."}
            root = ET.fromstring(z.read("Metadata/slice_info.config"))
    except Exception as exc:
        return {"sliced": False, "note": "Couldn't read the slice info: %s" % exc}

    header = {h.get("key"): h.get("value") for h in root.iter("header_item")}
    plates = []
    for plate in root.findall("plate"):
        meta = {m.get("key"): m.get("value") for m in plate.findall("metadata")}
        seconds = _int(meta.get("prediction"))
        filaments = []
        for f in plate.findall("filament"):
            filaments.append({
                "slot": _int(f.get("id")),
                "type": f.get("type") or "",
                "colour": f.get("color") or "",
                "filament_id": f.get("tray_info_idx") or "",
                "used_g": _float(f.get("used_g")),
                "used_m": _float(f.get("used_m")),
                "for_object": f.get("used_for_object") != "false",
                "for_support": f.get("used_for_support") == "true",
            })
        warnings = []
        for w in plate.findall("warning"):
            msg = w.get("msg") or ""
            warnings.append({
                "message": SLICE_WARNINGS.get(msg, msg),
                "raw": msg,
                "level": _int(w.get("level")) or 0,
                "ignored": msg in IGNORED_WARNINGS,
            })
        plates.append({
            "plate": _int(meta.get("index")) or len(plates) + 1,
            "print_seconds": seconds,
            "print_time": _duration(seconds),
            "filament_g": _float(meta.get("weight")),
            "filaments": filaments,
            "support_used": meta.get("support_used") == "true",
            "outside_plate": meta.get("outside") == "true",
            "printer_model_id": meta.get("printer_model_id") or "",
            "nozzle_diameters": meta.get("nozzle_diameters") or "",
            "objects": [{"name": o.get("name"),
                         "id": o.get("identify_id"),
                         "skipped": o.get("skipped") == "true"}
                        for o in plate.findall("object")],
            "warnings": warnings,
        })

    return {
        "sliced": bool(plates),
        "sliced_by": header.get("OrcaSlicer-Version") and "OrcaSlicer"
                     or "Bambu Studio",
        "slicer_version": header.get("X-BBL-Client-Version", ""),
        "plates": plates,
        "total_seconds": sum(p["print_seconds"] or 0 for p in plates),
        "total_print_time": _duration(
            sum(p["print_seconds"] or 0 for p in plates)),
        "total_filament_g": round(
            sum(p["filament_g"] or 0.0 for p in plates), 2),
    }


def _int(value):
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def _float(value):
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None


def _duration(seconds):
    if not seconds:
        return ""
    seconds = int(seconds)
    h, m = divmod(seconds // 60, 60)
    if h and m:
        return "%dh %dm" % (h, m)
    if h:
        return "%dh" % h
    return "%dm" % max(1, m)


# ── the plate picture ────────────────────────────────────────────────

PLATE_IMAGES = {
    "plate": "Metadata/plate_%d.png",
    "small": "Metadata/plate_%d_small.png",
    "no_light": "Metadata/plate_no_light_%d.png",
    "top": "Metadata/top_%d.png",
}


def plate_preview(path_3mf, plate=1, out_path=None, kind="plate"):
    """Pull a plate picture out of a 3MF so it can be looked at."""
    entry = PLATE_IMAGES.get(kind, PLATE_IMAGES["plate"]) % int(plate)
    with zipfile.ZipFile(path_3mf) as z:
        if entry not in z.namelist():
            available = [n for n in z.namelist() if n.endswith(".png")]
            return {"ok": False,
                    "error": "%s isn't in this 3MF." % entry,
                    "available": available}
        data = z.read(entry)
    if not out_path:
        out_path = os.path.join(os.path.dirname(os.path.abspath(path_3mf)),
                                os.path.basename(entry))
    with open(out_path, "wb") as fh:
        fh.write(data)
    return {"ok": True, "file": out_path, "bytes": len(data)}


def open_in_studio(path, studio_exe=""):
    """Open a file in the Bambu Studio window for a human to look at. Always
    allowed — it prints nothing by itself."""
    exe = find_studio(studio_exe)
    if not exe:
        return {"ok": False, "error": "Bambu Studio isn't installed here."}
    if not os.path.isfile(path):
        return {"ok": False, "error": "No file at %s" % path}
    try:
        subprocess.Popen([exe, os.path.abspath(path)])
    except OSError as exc:
        return {"ok": False, "error": "Couldn't open Bambu Studio: %s" % exc}
    return {"ok": True, "opened": os.path.abspath(path),
            "note": "Opened in Bambu Studio. Nothing has been sent to the "
                    "printer."}


# ── the report in words ──────────────────────────────────────────────

def format_slice_report(report):
    if not report.get("ok"):
        lines = ["Slicing failed: %s" % report.get("error", "unknown problem")]
        if report.get("retry_hint"):
            lines.append("  " + report["retry_hint"])
        for w in report.get("slicer_warnings", []):
            lines.append("  " + w)
        for name in ("stdout_tail", "stderr_tail"):
            for line in report.get(name, []):
                lines.append("  | " + line)
        if "result_json_written" in report and not report["result_json_written"]:
            lines.append("  (no result.json was written)")
        rj = report.get("result_json")
        if rj:
            lines.append("  result.json: code %s, %s"
                         % (rj.get("return_code"), rj.get("error_string") or "no message"))
        if report.get("studio_log_folder"):
            lines.append("  Studio's log: %s" % report["studio_log_folder"])
        if report.get("scratch_folder"):
            lines.append("  Kept for a look: %s" % report["scratch_folder"])
        return "\n".join(lines)

    lines = ["Sliced %s" % os.path.basename(report["file"])]
    if report.get("slicer_version"):
        lines.append("  %s %s" % (report.get("sliced_by", "Bambu Studio"),
                                  report["slicer_version"]))
    for p in report.get("plates", []):
        lines.append("")
        lines.append("  Plate %d: %s, %.1f g"
                     % (p["plate"], p["print_time"] or "time unknown",
                        p["filament_g"] or 0.0))
        for f in p["filaments"]:
            role = []
            if f["for_support"]:
                role.append("support")
            if not f["for_object"]:
                role.append("not used for the part")
            lines.append("    slot %s: %s %s — %.1f g, %.1f m%s"
                         % (f["slot"], f["type"], f["colour"],
                            f["used_g"] or 0.0, f["used_m"] or 0.0,
                            (" (%s)" % ", ".join(role)) if role else ""))
        if p["support_used"]:
            lines.append("    support was generated")
        if p["outside_plate"]:
            lines.append("    ! Some toolpath falls outside the printable "
                         "area — this will not print correctly.")
        for w in p["warnings"]:
            if not w.get("ignored"):
                lines.append("    ! " + w["message"])
    for w in report.get("slicer_warnings", []):
        lines.append("")
        lines.append("  ! " + w)
    if report.get("plates"):
        try:
            pr = runpy.run_path(os.path.join(
                os.path.dirname(os.path.abspath(__file__)), "pricing.py"))
            priced = pr["price_plates"](report["plates"])
            report["price"] = priced
            lines.append("")
            lines.append(pr["format_price"](priced))
        except Exception as exc:
            lines.append("")
            lines.append("  ! Couldn't work out the price: %s" % exc)
    return "\n".join(lines)
