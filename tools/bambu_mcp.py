#!/usr/bin/env python3
"""
Project Bonfire — Bambu MCP server (Layers A, B and C).

Exposes the tools in `bambu.py` and `bambu_slice.py` over MCP so Claude can
inspect models, decide supports and rafts, orient parts, pack the plate, build
a real Bambu Studio project 3MF, and slice it — all inside the rules in
`04_bambu_basics.md`.

It also runs the P1S: status over Bambu Cloud, files onto the printer over the
home network, and start / pause / resume / stop. Starting and stopping need the
person's yes (04_bambu_basics.md section 7) — enforced by a one-time code from
print_preview, not by the chat app. It never signs in: the password is only
ever typed in a terminal (`python tools/bambu_cloud.py login`).

Install and run:

    python -m pip install "mcp[cli]<2"
    python tools/bambu_mcp.py

Register it in the Claude desktop app alongside the Blender MCP:

    "bambu": {
      "command": "<full path to python.exe>",
      "args": ["C:\\\\Users\\\\<you>\\\\Desktop\\\\Project Bonfire\\\\tools\\\\bambu_mcp.py"],
      "env": {"BONFIRE_HOME": "C:\\\\Users\\\\<you>\\\\Desktop\\\\Project Bonfire"}
    }

The core logic stays importable without the server, the same way paths.py and
inventory.py are, so it still works through runpy inside Blender:

    bb = runpy.run_path(os.path.join(ROOT, "tools", "bambu.py"))
"""
import glob
import json
import os
import runpy
import sys

# ── find Project Bonfire, the same way the /bf- commands do ──────────


def bonfire_root():
    here = os.path.dirname(os.path.abspath(__file__))
    home = os.path.expanduser("~")
    candidates = [os.environ.get("BONFIRE_HOME", ""), os.path.dirname(here)]
    candidates.append(os.path.join(home, "Desktop", "Project Bonfire"))
    candidates += glob.glob(os.path.join(home, "OneDrive*", "Desktop",
                                         "Project Bonfire"))
    for c in candidates:
        if c and os.path.isfile(os.path.join(c, "PROJECT_INSTRUCTIONS.md")) \
               and os.path.isfile(os.path.join(c, "tools", "bambu.py")):
            return c
    raise FileNotFoundError(
        "Project Bonfire not found; set the BONFIRE_HOME environment variable "
        "to its path")


ROOT = bonfire_root()
TOOLS = os.path.join(ROOT, "tools")
bb = runpy.run_path(os.path.join(TOOLS, "bambu.py"))
b3 = runpy.run_path(os.path.join(TOOLS, "bambu_3mf.py"))
bpre = runpy.run_path(os.path.join(TOOLS, "bambu_presets.py"))
bsl = runpy.run_path(os.path.join(TOOLS, "bambu_slice.py"))
bcl = runpy.run_path(os.path.join(TOOLS, "bambu_cloud.py"))
blan = runpy.run_path(os.path.join(TOOLS, "bambu_lan.py"))
bpr = runpy.run_path(os.path.join(TOOLS, "bambu_print.py"))
bp = runpy.run_path(os.path.join(TOOLS, "paths.py"))

CONFIG_PATH = os.path.join(TOOLS, "bambu_config.json")

DEFAULT_CONFIG = {
    "studio_exe": "",
    "presets": {
        "machine": bpre["MACHINE_PRESET"],
        "process": bpre["PROCESS_PRESET"],
    },
    "arrange_spacing_mm": bb["DEFAULT_SPACING_MM"],
    "raft_layers": bb["RAFT_LAYERS_ON"],
    "optimize_for": "strength",
    "print_needs_approval": True,
    "save_sliced_file": True,
    "connection": "cloud",
}


def read_config():
    cfg = dict(DEFAULT_CONFIG)
    if os.path.isfile(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, encoding="utf-8") as fh:
                cfg.update(json.load(fh))
        except Exception:
            pass
    return cfg


def write_config(cfg):
    with open(CONFIG_PATH, "w", encoding="utf-8") as fh:
        json.dump(cfg, fh, indent=2)
    return cfg


# ── the server ───────────────────────────────────────────────────────

try:
    from mcp.server.fastmcp import FastMCP            # MCP SDK 1.x
except ImportError:                                   # pragma: no cover
    try:                                              # 2.x renamed it
        from mcp.server.mcpserver import MCPServer as FastMCP
    except ImportError:
        sys.stderr.write(
            "The MCP SDK isn't installed. Run:  python -m pip install \"mcp[cli]<2\"\n")
        raise

mcp = FastMCP("bonfire-bambu")


def _ok(value):
    """Everything goes back as JSON so Claude gets structure, not prose."""
    return json.dumps(value, indent=2, default=str)


def _fail(message, **extra):
    out = {"ok": False, "error": message}
    out.update(extra)
    return _ok(out)


@mcp.tool()
def bambu_get_rules() -> str:
    """The printing rules currently in force: what may be changed without
    asking, what is locked, and what needs approval every time. Read this at
    the start of any print task. Source: 04_bambu_basics.md."""
    return _ok(bb["get_rules"]())


@mcp.tool()
def bambu_setup_check() -> str:
    """Check the setup: Bambu Studio's location and version, whether the preset
    template exists, and whether the P1S system presets are installed. Reports
    what is missing and how to fix it."""
    cfg = read_config()
    report = {"bonfire_root": ROOT, "config_file": CONFIG_PATH, "missing": []}

    exe = bsl["find_studio"](cfg.get("studio_exe", ""))
    report["studio_exe"] = exe or None
    if exe:
        version = bsl["installed_studio_version"](exe)
        report["studio_version"] = version or "(wouldn't say)"
        if bsl["studio_can_print"](version) is False:
            report["missing"].append(bsl["STUDIO_TOO_OLD"] % version)
    if not exe:
        report["missing"].append(
            "Bambu Studio wasn't found. Set studio_exe in tools/bambu_config.json "
            "or BAMBU_STUDIO_PATH in .env. Slicing (Layer B) needs it; building "
            "a 3MF does not.")

    template = bpre["template_path"](ROOT)
    report["preset_template"] = template if os.path.isfile(template) else None
    if not report["preset_template"]:
        report["missing"].append(
            "No tools/bambu_template.3mf. Save any project from Bambu Studio "
            "there, with the P1S presets selected, and every setting this "
            "project doesn't touch will match Bambu's defaults exactly. "
            "Without it the presets are built from scratch — workable, but not "
            "identical.")
    else:
        try:
            settings = b3["read_project_settings"](template)
            report["template_printer"] = settings.get("printer_model")
            report["template_process"] = settings.get("print_settings_id")
            report["template_filaments"] = settings.get("filament_settings_id")
            report["template_keys"] = len(settings)
            if settings.get("printer_model") != bpre["PRINTER_MODEL"]:
                report["missing"].append(
                    "The template was saved for %r, not %r. Save it again with "
                    "the P1S selected."
                    % (settings.get("printer_model"), bpre["PRINTER_MODEL"]))
        except Exception as exc:
            report["missing"].append("The template couldn't be read: %s" % exc)

    presets = _system_presets()
    report["system_preset_folder"] = presets.get("folder")
    for kind, name in (("machine", bpre["MACHINE_PRESET"]),
                       ("process", bpre["PROCESS_PRESET"])):
        found = name in presets.get(kind, [])
        report["%s_preset_found" % kind] = found
        if presets.get("folder") and not found:
            report["missing"].append(
                "The %s preset %r isn't in Bambu Studio's system folder." % (kind, name))

    report["ok"] = not report["missing"]
    return _ok(report)


def _system_presets():
    """What's in Bambu Studio's installed system preset folder, if it's there."""
    roots = [os.path.expandvars(r"%APPDATA%\BambuStudio\system\BBL"),
             os.path.expanduser("~/Library/Application Support/BambuStudio/system/BBL"),
             os.path.expanduser("~/.config/BambuStudio/system/BBL")]
    for root in roots:
        if os.path.isdir(root):
            out = {"folder": root}
            for kind in ("machine", "process", "filament"):
                folder = os.path.join(root, kind)
                out[kind] = sorted(
                    os.path.splitext(f)[0] for f in os.listdir(folder)
                    if f.endswith(".json")) if os.path.isdir(folder) else []
            return out
    return {"folder": None, "machine": [], "process": [], "filament": []}


@mcp.tool()
def bambu_list_presets(kind: str = "process", contains: str = "") -> str:
    """List Bambu Studio presets, so names used elsewhere are exact.
    kind: machine | process | filament. contains: filter text (optional)."""
    kind = kind.lower().strip()
    if kind not in ("machine", "process", "filament"):
        return _fail("kind must be machine, process or filament")
    installed = _system_presets()
    names = installed.get(kind) or []
    source = "Bambu Studio's system folder"
    if not names:
        source = "this project's built-in list (Bambu Studio not found)"
        if kind == "process":
            names = bpre["PROCESS_PRESETS"]
        elif kind == "machine":
            names = [bpre["MACHINE_PRESET"]]
        else:
            names = sorted({f["preset"] for f in bpre["FILAMENTS"].values()})
    if contains:
        names = [n for n in names if contains.lower() in n.lower()]
    return _ok({"kind": kind, "source": source, "count": len(names),
                "presets": names})


@mcp.tool()
def inspect_model(path: str) -> str:
    """Measure one STL or 3MF: bounding box, volume, triangle count, whether it
    is a closed solid, loose pieces, bed footprint, and whether it fits the
    P1S's 256 mm cube."""
    if not os.path.isfile(path):
        return _fail("No file at %s" % path)
    return _ok(bb["inspect_model"](path))


@mcp.tool()
def suggest_supports(path: str, threshold_deg: float = 0.0) -> str:
    """Analyse the overhangs in an STL or 3MF and say whether supports are
    needed, which type (normal(auto) or tree(auto)), and whether they can stand
    on the build plate only — with the reason, per 04_bambu_basics.md §2.
    threshold_deg: 0 uses Bambu's default of 30."""
    if not os.path.isfile(path):
        return _fail("No file at %s" % path)
    return _ok(bb["suggest_supports"](path, threshold_deg or None))


@mcp.tool()
def suggest_raft(path: str) -> str:
    """Apply the raft rule in 04_bambu_basics.md §2 to one model: raft on (2
    layers) or off, with the footprint and height it was decided from."""
    if not os.path.isfile(path):
        return _fail("No file at %s" % path)
    return _ok(bb["suggest_raft"](path))


@mcp.tool()
def compare_orientations(path: str, part_name: str = "") -> str:
    """Try the sensible ways up for a part and pick one by 04_bambu_basics.md
    §3 — strength first if the part looks load-bearing, then largest flat face,
    then fewest supports. Returns every candidate's support area, footprint and
    height, and which was chosen and why."""
    if not os.path.isfile(path):
        return _fail("No file at %s" % path)
    return _ok(bb["compare_orientations"](path, name=part_name or None))


@mcp.tool()
def plan_plate(project: str, spacing_mm: float = 0.0) -> str:
    """Work out what would go on the plate for a project — newest STL of each
    part, Quantity copies, packed with the given spacing — without writing
    anything. A dry run of build_print_3mf."""
    folder, hits = bp["resolve_project"](project)
    if folder is None:
        return _fail("No single project matches %r" % project, candidates=hits)
    exports = bb["newest_exports"](folder)
    if not exports:
        return _fail("No STLs in %s/stl" % folder)
    quantities = bb["read_quantities"](folder)
    sizes, labels = [], []
    for part, stl in exports.items():
        mesh = bb["bm"]["load_mesh"](stl)
        placed = bb["orient"](mesh, mode="auto", name=part)["mesh"]
        size = bb["bm"]["bbox"](placed)["size"]
        for _ in range(max(1, quantities.get(part, 1))):
            sizes.append((size[0], size[1]))
            labels.append(part)
    cfg = read_config()
    packing = bb["arrange_plate"](
        sizes, spacing_mm or cfg.get("arrange_spacing_mm",
                                     bb["DEFAULT_SPACING_MM"]))
    return _ok({"project": folder, "material": bb["read_material"](folder),
                "copies": labels, "fits_one_plate": packing["fits"],
                "leftover": [labels[i["index"]] for i in packing["leftover"]],
                "spacing_mm": packing["spacing_mm"]})


@mcp.tool()
def build_print_3mf(project: str, parts: str = "", material: str = "",
                    spacing_mm: float = 0.0, orient_mode: str = "auto",
                    process_preset: str = "", arrange: str = "auto") -> str:
    """
    Build a real Bambu Studio project 3MF for a project, in its 3mf/ folder:
    newest STL of each part, oriented, copied to its Quantity, packed on one
    plate, with filament assigned and supports/raft set from the rules.

    Does not reserve hardware — use prepare_print for the full §4 flow.
    parts: comma-separated part names, or blank for all.
    orient_mode: auto | keep
    arrange: auto (Bambu Studio's own Arrange when it's installed, otherwise
        this project's packer, centred) | studio | bonfire.
    spacing_mm: 0 keeps Bambu's default spacing. Any other value needs this
        project's packer, because Studio's command line can't change spacing.
    """
    kwargs = _layout_kwargs(spacing_mm, arrange)
    kwargs["orient_mode"] = orient_mode
    if parts:
        kwargs["parts"] = [p.strip() for p in parts.split(",") if p.strip()]
    if material:
        kwargs["material"] = material
    if process_preset:
        kwargs["process"] = process_preset
    try:
        report = bb["build_print_3mf"](project, **kwargs)
    except bb["SettingRefused"] as exc:
        return _fail(str(exc))
    report["report"] = bb["format_report"](report)
    return _ok(report)


@mcp.tool()
def prepare_print(project: str, parts: str = "", material: str = "",
                  spacing_mm: float = 0.0, orient_mode: str = "auto",
                  arrange: str = "auto") -> str:
    """
    "Get it ready to print", the whole 04_bambu_basics.md §4 flow in one call:
    build the project 3MF, reserve the project's hardware in the inventory, and
    refresh the project index. Returns the full report, including which
    settings were changed and why, and any hardware that is short.
    arrange: auto | studio | bonfire — see build_print_3mf.
    """
    kwargs = _layout_kwargs(spacing_mm, arrange)
    kwargs["orient_mode"] = orient_mode
    if parts:
        kwargs["parts"] = [p.strip() for p in parts.split(",") if p.strip()]
    if material:
        kwargs["material"] = material
    try:
        report = bb["prepare_print"](project, **kwargs)
    except bb["SettingRefused"] as exc:
        return _fail(str(exc))
    report["report"] = bb["format_report"](report)
    return _ok(report)


@mcp.tool()
def set_object_settings(settings_json: str, user_requested: str = "") -> str:
    """
    Check a set of slicer settings against the rules before using them
    (04_bambu_basics.md §2). Approved settings pass; walls, infill, speed,
    temperatures and flow are refused unless user_requested carries the user's
    own words asking for the change; anything else is refused outright.
    settings_json: e.g. {"support_type": "tree(auto)", "raft_layers": "2"}
    """
    try:
        settings = json.loads(settings_json)
    except Exception as exc:
        return _fail("settings_json isn't valid JSON: %s" % exc)
    try:
        return _ok({"ok": True, "allowed": bb["guard_settings"](
            settings, user_requested or None)})
    except bb["SettingRefused"] as exc:
        return _fail(str(exc))


@mcp.tool()
def describe_3mf(path: str) -> str:
    """What is inside a 3MF, and whether Bambu Studio will open it as a real
    project or fall back to "load geometry data only"."""
    if not os.path.isfile(path):
        return _fail("No file at %s" % path)
    return _ok(b3["describe"](path))


@mcp.tool()
def slice_3mf(path: str = "", project: str = "", plate: int = 0,
              allow_newer: bool = False) -> str:
    """
    Slice a Bambu project 3MF with Bambu Studio's command-line slicer and save
    the result as <name>_<n>.gcode.3mf beside it (04_bambu_basics.md §7).
    Slicing is allowed without asking; this sends nothing to the printer.

    Give either `path` (a 3MF) or `project` (its newest 3MF is used).
    plate: 0 slices every plate, or a 1-based plate number.
    allow_newer: only for a 3MF written by a newer Bambu Studio than installed.
    """
    if not path:
        if not project:
            return _fail("Give either path or project.")
        found = _newest_project_3mf(project)
        if isinstance(found, str) and found.startswith("{"):
            return found
        path = found
    cfg = read_config()
    report = bsl["slice_file"](path, plate=plate,
                               studio_exe=cfg.get("studio_exe", ""),
                               allow_newer=allow_newer)
    report["report"] = bsl["format_slice_report"](report)
    return _ok(report)


@mcp.tool()
def slice_report(path: str) -> str:
    """Read a sliced .gcode.3mf back: print time, filament per slot in grams
    and metres, whether support was generated, whether anything falls outside
    the printable area, and any slicer warnings."""
    if not os.path.isfile(path):
        return _fail("No file at %s" % path)
    info = bsl["read_slice_info"](path)
    if info.get("sliced"):
        info["report"] = bsl["format_slice_report"](dict(info, ok=True,
                                                         file=path))
    return _ok(info)


@mcp.tool()
def plate_preview(path: str, plate: int = 1, kind: str = "plate") -> str:
    """Pull the plate picture out of a 3MF so it can be looked at. kind:
    plate | small | no_light | top. Only a sliced file has all of them."""
    if not os.path.isfile(path):
        return _fail("No file at %s" % path)
    folder = os.path.dirname(os.path.abspath(path))
    project = os.path.basename(os.path.dirname(folder))
    out = None
    if os.path.isdir(os.path.join(bp["LIBRARY"], project)):
        out = bp["next_reference_path"](os.path.join(bp["LIBRARY"], project),
                                        "plate_preview", "png")
    return _ok(bsl["plate_preview"](path, plate, out, kind))


@mcp.tool()
def open_in_studio(path: str) -> str:
    """Open a 3MF in the Bambu Studio window for a human to check, or to press
    Print yourself. Always allowed — it sends nothing to the printer."""
    cfg = read_config()
    return _ok(bsl["open_in_studio"](path, cfg.get("studio_exe", "")))


@mcp.tool()
def prepare_and_slice(project: str, parts: str = "", material: str = "",
                      orient_mode: str = "auto", arrange: str = "auto") -> str:
    """
    The whole way from STLs to a sliced file: build the project 3MF with the
    rules applied, reserve the hardware, then slice it. Returns both reports.
    Still sends nothing to the printer — starting a print needs a yes, every
    time (04_bambu_basics.md §7).
    """
    kwargs = _layout_kwargs(0.0, arrange)
    kwargs["orient_mode"] = orient_mode
    if parts:
        kwargs["parts"] = [p.strip() for p in parts.split(",") if p.strip()]
    if material:
        kwargs["material"] = material
    try:
        built = bb["prepare_print"](project, **kwargs)
    except bb["SettingRefused"] as exc:
        return _fail(str(exc))
    if not built.get("ok"):
        built["report"] = bb["format_report"](built)
        return _ok(built)

    cfg = read_config()
    sliced = bsl["slice_file"](built["file"],
                               studio_exe=cfg.get("studio_exe", ""))
    return _ok({
        "ok": sliced.get("ok", False),
        "built": dict(built, report=bb["format_report"](built)),
        "sliced": dict(sliced, report=bsl["format_slice_report"](sliced)),
        "report": bb["format_report"](built) + "\n\n"
                  + bsl["format_slice_report"](sliced),
    })


@mcp.tool()
def arrange_with_studio(path: str = "", project: str = "",
                        allow_rotations: bool = True) -> str:
    """
    Re-lay-out a project 3MF's plate with Bambu Studio's own Arrange button,
    run from its command line. Parts keep the way up they already have — only
    their place on the plate changes (and, with allow_rotations, their turn
    about the vertical axis). Saves a new numbered 3MF beside the original;
    nothing is sliced or sent anywhere.

    Give either `path` (a 3MF) or `project` (its newest 3MF is used).
    Studio's command line always uses its default spacing.
    """
    if not path:
        if not project:
            return _fail("Give either path or project.")
        found = _newest_project_3mf(project)
        if found.startswith("{"):
            return found
        path = found
    if not os.path.isfile(path):
        return _fail("No file at %s" % path)
    folder = os.path.dirname(os.path.abspath(path))
    stem = os.path.splitext(os.path.basename(path))[0]
    stem = stem.rsplit("_", 1)[0] if stem.rsplit("_", 1)[-1].isdigit() else stem
    out = bp["next_export_path"](os.path.dirname(folder), stem, "3mf") \
        if os.path.basename(folder) == "3mf" else None
    result = bsl["studio_arrange"](path, out_path=out,
                                   studio_exe=read_config().get("studio_exe", ""),
                                   allow_rotations=allow_rotations)
    if result.get("ok"):
        result["report"] = ("Arranged by Bambu Studio: %s"
                             % os.path.basename(result["file"]))
        if result.get("settings_lost"):
            result["report"] += ("\n  ! Studio dropped: "
                                 + "; ".join(result["settings_lost"]))
    return _ok(result)


def _layout_kwargs(spacing_mm, arrange):
    """spacing 0 means Bambu's default, which leaves Studio's Arrange free to
    do the layout; any other spacing needs our packer."""
    arrange = (arrange or "auto").lower()
    if arrange not in ("auto", "studio", "bonfire"):
        arrange = "auto"
    cfg = read_config()
    kwargs = {"arrange": arrange, "studio_exe": cfg.get("studio_exe", "")}
    if spacing_mm:
        kwargs["spacing_mm"] = spacing_mm
    elif arrange == "bonfire":
        kwargs["spacing_mm"] = cfg.get("arrange_spacing_mm",
                                       bb["DEFAULT_SPACING_MM"])
    return kwargs


def _newest_project_3mf(project):
    """The newest 3MF in a project's 3mf/ folder, or a JSON error string."""
    folder, hits = bp["resolve_project"](project)
    if folder is None:
        return _fail("No single project matches %r" % project, candidates=hits)
    root = os.path.join(bp["LIBRARY"], folder, "3mf")
    if not os.path.isdir(root):
        return _fail("%s has no 3mf folder — build one first." % folder)
    files = [os.path.join(root, f) for f in os.listdir(root)
             if f.lower().endswith(".3mf")
             and not f.lower().endswith(".gcode.3mf")]
    if not files:
        return _fail("No project 3MF in %s/3mf — run build_print_3mf first."
                     % folder)
    return max(files, key=os.path.getmtime)


@mcp.tool()
def bambu_account() -> str:
    """Whether this PC is signed in to Bambu Cloud, as whom, which printer,
    and when the sign-in runs out. Doesn't touch the network. Signing in is
    never done from here — the person runs
    `python tools/bambu_cloud.py login <email>` in a terminal, so the password
    never passes through Claude."""
    return _ok(bcl["account_state"]())


@mcp.tool()
def printer_list() -> str:
    """The printers bound to the Bambu account, with serial and online state."""
    try:
        return _ok({"ok": True, "printers": bcl["list_devices"]()})
    except bcl["CloudError"] as exc:
        return _fail(str(exc))


@mcp.tool()
def printer_status(serial: str = "") -> str:
    """
    What the P1S is doing right now, over Bambu Cloud: idle / printing /
    paused / finished / failed, the job, progress, layer, time left,
    temperatures, any HMS errors (with Bambu's wiki link for each), and what's
    loaded in every AMS slot. Read-only — nothing is sent to the printer except
    a request for its report. Takes a few seconds.
    """
    try:
        st = bcl["printer_status"](serial)
    except bcl["CloudError"] as exc:
        return _fail(str(exc))
    st["ok"] = True
    st["report"] = bcl["format_status"](st)
    return _ok(st)


@mcp.tool()
def ams_status(serial: str = "") -> str:
    """What's loaded in each AMS slot — type, colour, amount left — numbered
    the way Bambu Studio numbers them. 04 section 4 says to read this each
    time before mapping a project's filaments to slots; if a material the
    project needs isn't loaded, say which and ask."""
    try:
        st = bcl["printer_status"](serial)
    except bcl["CloudError"] as exc:
        return _fail(str(exc))
    return _ok({"ok": True, "printer": st.get("printer"), "state": st.get("state"),
                "slots": st.get("ams", [])})


def _guard(fn, *a, **kw):
    """Run a print-side call and turn the expected refusals into JSON."""
    try:
        return fn(*a, **kw)
    except (bpr["PrintError"], bcl["CloudError"], blan["LanError"]) as exc:
        return {"ok": False, "error": str(exc)}


@mcp.tool()
def lan_check() -> str:
    """Prove the home-network path works before a print depends on it: find
    the printer, log in over FTPS, list what's on its SD card. The access code
    is used but never shown."""
    r = _guard(blan["check"])
    return _ok(r)


@mcp.tool()
def print_preview(path: str, plate: int = 1, slots: str = "") -> str:
    """
    Step 1 of starting a print (04_bambu_basics.md section 7). For a sliced
    .gcode.3mf: plate, print time, grams, which AMS slot feeds each filament
    (read live from the printer), whether the printer is free, and any reason
    not to go ahead. When everything is fine it returns a one-time
    approval_code (10 minutes, this file and plate only).

    Show the person the `report`, and only call start_print with the code
    after they say yes. Never start on an earlier yes.
    slots: optional override, e.g. "1:3" = filament 1 from AMS slot 3.
    """
    r = _guard(bpr["preview"], path, plate, slots)
    if r.get("file"):
        r["report"] = bpr["format_preview"](r)
    return _ok(r)


@mcp.tool()
def start_print(path: str, plate: int = 1, approval_code: str = "") -> str:
    """
    Step 2: start the print the person just said yes to, with the
    approval_code from print_preview. Uploads the file to the printer over the
    home network and starts it through Bambu Cloud (route lan_cloud). If the
    printer refuses for authorization reasons — Bambu's lockdown reaching the
    P1S — the route switches to Bambu Connect by itself and opens it with the
    file; the report says so.
    """
    return _ok(_guard(bpr["start"], path, plate, approval_code))


@mcp.tool()
def pause_print(retry: bool = False) -> str:
    """Pause the running print. No approval needed (04 section 7). This P1S
    refuses cloud control commands (MQTT command verification), so after the
    first refusal nothing is sent and the answer says to pause in Bambu
    Studio's Device tab, Handy, or on the screen. retry=true sends anyway."""
    return _ok(_guard(bpr["pause"], retry=retry))


@mcp.tool()
def resume_print(retry: bool = False) -> str:
    """Resume a paused print. No approval needed. Refused by this P1S's
    firmware like pause_print; retry=true sends anyway."""
    return _ok(_guard(bpr["resume"], retry=retry))


@mcp.tool()
def stop_print(confirm: bool = False, retry: bool = False) -> str:
    """Stop the print for good (it can't be resumed). Needs a yes: pass
    confirm=true only after the person said yes to stopping this print.
    Refused by this P1S's firmware like pause_print — if it's urgent, tell
    the person to stop it on the printer's screen or in Handy right away."""
    return _ok(_guard(bpr["stop"], confirm, retry=retry))


@mcp.tool()
def print_route(set_to: str = "") -> str:
    """How prints get to the printer. lan_cloud (default): upload over the home
    network, start over Bambu Cloud. bambu_connect: open Bambu Connect with the
    file for the person to send — the fallback if Bambu locks network starts on
    the P1S. studio: open in Bambu Studio. Blank reads the current route."""
    if set_to:
        return _ok(_guard(bpr["set_route"], set_to, "set on request"))
    cfg = bpr["read_config"]()
    return _ok({"route": bpr["route"](),
                "last_change": cfg.get("print_route_changed"),
                "approval_required": bpr["needs_approval"]()})


@mcp.tool()
def retarget_to_p1s(path: str) -> str:
    """For a 3MF that opens set up for another Bambu printer — MakerWorld files
    often default to an X1. Swaps in the P1S's own machine settings (start/end
    G-code, nozzle, limits, bed no-print area; 69 settings from Bambu's
    profiles), keeps the process and filament choices, and writes
    <name>_P1S.3mf beside it. The original isn't touched. A file that was
    already sliced for the other printer has that G-code removed and needs
    slicing again."""
    r = _guard(bpr["retarget_to_p1s"], path)
    if r.get("ok"):
        r["report"] = bpr["format_retarget"](r)
    return _ok(r)


@mcp.tool()
def bambu_config(set_json: str = "") -> str:
    """Read the Bambu configuration, or change it by passing a JSON object of
    the keys to set. Never holds secrets — credentials live in .env."""
    cfg = read_config()
    if set_json:
        try:
            changes = json.loads(set_json)
        except Exception as exc:
            return _fail("set_json isn't valid JSON: %s" % exc)
        for key in ("access_code", "password", "token"):
            changes.pop(key, None)
        cfg.update(changes)
        write_config(cfg)
    return _ok(cfg)


if __name__ == "__main__":
    mcp.run()
