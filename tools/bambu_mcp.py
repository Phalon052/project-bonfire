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
import functools
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

# The tool code is loaded from tools/*.py, and loaded again whenever one of
# those files changes — so an update takes effect on the next tool call,
# without restarting the Claude app. (A changed tool *description* or a new
# parameter still needs a restart: the app reads those once, at start.)
_MODULES = {"bb": "bambu.py", "b3": "bambu_3mf.py", "bpre": "bambu_presets.py",
            "bsl": "bambu_slice.py", "bcl": "bambu_cloud.py",
            "blan": "bambu_lan.py", "bpr": "bambu_print.py", "bp": "paths.py",
            "bcam": "bambu_camera.py", "bw": "bambu_watch.py",
            "ph": "photo.py", "bmo": "bambu_modes.py", "bui": "bambu_studio_ui.py"}
_LOADED_AT = [0.0]


def _code_mtime():
    return max(os.path.getmtime(os.path.join(TOOLS, f))
               for f in _MODULES.values() if os.path.isfile(os.path.join(TOOLS, f)))


def _fresh():
    """Reload the tool modules if any of their files changed since loading."""
    newest = _code_mtime()
    if newest <= _LOADED_AT[0]:
        return False
    fresh = {name: runpy.run_path(os.path.join(TOOLS, f))
             for name, f in _MODULES.items()}
    globals().update(fresh)
    _LOADED_AT[0] = newest
    return True


bb = b3 = bpre = bsl = bcl = blan = bpr = bp = bcam = bw = ph = bmo = bui = None
_fresh()

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
    from mcp.server.fastmcp import Image as McpImage  # a picture Claude can see
except ImportError:                                   # pragma: no cover
    McpImage = None

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
_register_tool = mcp.tool


def _tool_with_reload(*args, **kwargs):
    """mcp.tool, plus a check for changed code before every call."""
    register = _register_tool(*args, **kwargs)

    def wrap(fn):
        @functools.wraps(fn)
        def call(*a, **kw):
            try:
                _fresh()
            except Exception as exc:          # a half-saved file: keep the old code
                sys.stderr.write("bonfire-bambu: reload skipped (%s)\n" % exc)
            return fn(*a, **kw)
        return register(call)
    return wrap


mcp.tool = _tool_with_reload


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


def _part_materials(text):
    """ "hex_nut: Overture PLA black, machine_screw: PLA white" -> dict."""
    out = {}
    for chunk in text.split(","):
        if ":" in chunk:
            part, mat = chunk.split(":", 1)
            if part.strip() and mat.strip():
                out[part.strip()] = mat.strip()
    return out


@mcp.tool()
def plan_plate(project: str, spacing_mm: float = 0.0,
               plate_goal: str = "fewest_plates", multicolor: bool = False,
                    part_materials: str = "") -> str:
    """Work out how a project would go onto plates — newest STL of each part,
    oriented, Quantity copies, with room for each part's brim and raft —
    without writing anything. A dry run of build_print_3mf. When it doesn't
    fit one plate, says how many plates and what goes on each.
    plate_goal: fewest_plates | shortest_time (tall parts share plates).
    multicolor / part_materials: as in build_print_3mf — by default each
    filament (type, brand, colour) gets plates of its own."""
    folder, hits = bp["resolve_project"](project)
    if folder is None:
        return _fail("No single project matches %r" % project, candidates=hits)
    exports = bb["newest_exports"](folder)
    if not exports:
        return _fail("No STLs in %s/stl" % folder)
    quantities = bb["read_quantities"](folder)
    overrides = _part_materials(part_materials)
    project_material = bb["read_material"](folder) or bpre["DEFAULT_MATERIAL"]
    sizes, labels, reach, tall, mats = [], [], [], [], []
    for part, stl in exports.items():
        mesh = bb["bm"]["load_mesh"](stl)
        placed = bb["orient"](mesh, mode="auto", name=part)["mesh"]
        size = bb["bm"]["bbox"](placed)["size"]
        raft = bb["suggest_raft"](placed)["raft"]
        for _ in range(max(1, quantities.get(part, 1))):
            sizes.append((size[0], size[1]))
            labels.append(part)
            reach.append(bb["part_clearance"](raft=bool(raft)))
            tall.append(size[2])
            mats.append(bpre["filament_key"](overrides.get(part, project_material)))
    try:
        plan = bb["plan_plates"](sizes, spacing_mm or bb["DEFAULT_SPACING_MM"],
                                 clearances=None if spacing_mm else reach,
                                 heights=tall, materials=mats, goal=plate_goal,
                                 max_materials=4 if multicolor else 1)
    except ValueError as exc:
        return _fail(str(exc))
    return _ok({"project": folder, "material": bb["read_material"](folder),
                "copies": len(labels), "plate_count": plan["plate_count"],
                "fits_one_plate": plan["plate_count"] <= 1 and not plan["unplaceable"],
                "plates": [{"plate": k + 1,
                            "parts": sorted(labels[i] for i in pl["items"]),
                            "filaments": pl["materials"],
                            "height_mm": pl["height_mm"]}
                           for k, pl in enumerate(plan["plates"])],
                "too_big_for_a_plate": sorted(set(labels[i] for i in plan["unplaceable"])),
                "goal": plate_goal})


@mcp.tool()
def build_print_3mf(project: str, parts: str = "", material: str = "",
                    spacing_mm: float = 0.0, orient_mode: str = "auto",
                    process_preset: str = "", arrange: str = "auto",
                    plate_goal: str = "fewest_plates", multicolor: bool = False,
                    part_materials: str = "") -> str:
    """
    Build a real Bambu Studio project 3MF for a project, in its 3mf/ folder:
    newest STL of each part, oriented, copied to its Quantity, packed on the
    plate, with filament assigned and supports/raft set from the rules. Jobs
    that don't fit one plate go on as many plates as needed, in the same file.
    plate_goal: fewest_plates (default) | shortest_time (tall parts share
        plates so short plates don't wait on tall layers).
    multicolor: false (default) keeps one filament per plate — parts in
        different filaments (type, brand or colour) get their own plates.
        Only set true when the person asks for a multicolour print.
    part_materials: per-part filament, e.g. "hex_nut: Overture PLA black,
        machine_screw: PLA white". Blank uses the project's material.
    Supports and rafts always print in the part's own filament.

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
    kwargs["plate_goal"] = plate_goal
    kwargs["multicolor"] = multicolor
    if part_materials:
        kwargs["material_overrides"] = _part_materials(part_materials)
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
                  arrange: str = "auto", plate_goal: str = "fewest_plates", multicolor: bool = False,
                    part_materials: str = "") -> str:
    """
    "Get it ready to print", the whole 04_bambu_basics.md §4 flow in one call:
    build the project 3MF, reserve the project's hardware in the inventory, and
    refresh the project index. Returns the full report, including which
    settings were changed and why, and any hardware that is short.
    arrange: auto | studio | bonfire — see build_print_3mf.
    """
    kwargs = _layout_kwargs(spacing_mm, arrange)
    kwargs["orient_mode"] = orient_mode
    kwargs["plate_goal"] = plate_goal
    kwargs["multicolor"] = multicolor
    if part_materials:
        kwargs["material_overrides"] = _part_materials(part_materials)
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
                      orient_mode: str = "auto", arrange: str = "auto",
                      plate_goal: str = "fewest_plates", multicolor: bool = False,
                    part_materials: str = "") -> str:
    """
    The whole way from STLs to a sliced file: build the project 3MF with the
    rules applied, reserve the hardware, then slice it. Returns both reports.
    Still sends nothing to the printer — starting a print needs a yes, every
    time (04_bambu_basics.md §7).
    """
    kwargs = _layout_kwargs(0.0, arrange)
    kwargs["orient_mode"] = orient_mode
    kwargs["plate_goal"] = plate_goal
    kwargs["multicolor"] = multicolor
    if part_materials:
        kwargs["material_overrides"] = _part_materials(part_materials)
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
    except (bpr["PrintError"], bcl["CloudError"], blan["LanError"],
            bcam["CameraError"], ph["PhotoError"], bmo["ModeError"],
            bui["UiError"]) as exc:
        return {"ok": False, "error": str(exc)}


def _with_picture(report, path):
    """The report as JSON, plus the picture itself so Claude can look at it."""
    out = [_ok(report)]
    if McpImage is not None and path and os.path.isfile(path):
        with open(path, "rb") as fh:
            out.append(McpImage(data=fh.read(), format="jpeg"))
    return out


@mcp.tool()
def photo_marker_sheet(page: str = "letter"):
    """
    Make the ArUco marker sheet for measuring from photos (tools/photo_markers.pdf):
    four markers (IDs 0-3, size from tools/photo_markers.json), cut lines,
    centre lines for setting each on a mat grid crossing, and a 100 mm bar to
    check it printed at 100 %. page: "letter" or "a4".
    """
    return _ok(_guard(ph["marker_sheet"], os.path.join(TOOLS, "photo_markers.pdf"),
                      page="a4" if page.lower() == "a4" else "letter"))


@mcp.tool()
def photo_layout(width_mm: float = 0, height_mm: float = 0, plane_mm: float = -1,
                 marker_mm: float = 0):
    """
    Show, or record, where the photo markers sit on the mat
    (tools/photo_markers.json). width_mm: centre of ID 0 to centre of ID 1;
    height_mm: centre of ID 0 to centre of ID 3; plane_mm: the markers' surface
    above the mat (the shim height, 0 on paper); marker_mm: the black square's
    side as printed. Leave a value at 0 (plane at -1) to keep it.
    """
    lay = ph["load_layout"]()
    for key, v in (("width_mm", width_mm), ("height_mm", height_mm),
                   ("marker_mm", marker_mm)):
        if v > 0:
            lay[key] = float(v)
    if plane_mm >= 0:
        lay["plane_mm"] = float(plane_mm)
    if width_mm > 0 or height_mm > 0 or plane_mm >= 0 or marker_mm > 0:
        ph["save_layout"](lay)
    return _ok({"ok": True, "layout": {k: lay[k] for k in ph["DEFAULT_LAYOUT"]},
                "centres_mm": {str(k): v for k, v in ph["marker_centres"](lay).items()}})


@mcp.tool()
def photo_rectify(photo: str, part_height_mm: float = -1, px_per_mm: float = 10):
    """
    Rectify a photo of a part lying among the four ArUco markers to a true
    straight-down view, scaled from the markers. Writes <photo>_rectified.png,
    _rectified_grid.png (mm grid, 0 at ID 0's centre) and _rectified.json
    beside the photo, and returns the report plus the grid picture so you can
    read it. Check fit_rms_mm and warnings before trusting a number.
    part_height_mm: the part's top-face height, to warn when it isn't on the
    marker plane. Measure points with photo_measure.
    """
    r = _guard(ph["rectify"], photo, ppmm=px_per_mm,
               part_height_mm=part_height_mm if part_height_mm >= 0 else None)
    out = [_ok(r)]
    if McpImage is not None and r.get("grid"):
        data = ph["preview"](r["grid"])
        if data:
            out.append(McpImage(data=data, format="jpeg"))
    return out


@mcp.tool()
def photo_measure(report: str, points: str, space: str = "rectified"):
    """
    Millimetres from a rectified photo. report: the _rectified.json path.
    points: "x1,y1; x2,y2; ..." in pixels of the rectified picture
    (space="rectified", full size, not the preview) or of the original photo
    (space="photo"). Returns each point in mm and the distance along them.
    """
    try:
        pts = [tuple(float(v) for v in p.split(",")) for p in points.split(";") if p.strip()]
    except ValueError:
        return _fail('points look like "x1,y1; x2,y2".')
    return _ok(_guard(ph["measure"], report, pts, "photo" if space == "photo" else "rectified"))


@mcp.tool()
def camera_snapshot(save_to: str = ""):
    """
    One picture from the P1S camera, over the home network, returned so you
    can see it. Saved in tools/camera_snapshots/ (newest 20 kept), or at
    save_to — e.g. a project's references/ folder when the person wants it
    kept. Read-only: nothing is sent to the printer except the camera login.
    The chamber light is the printer's own; a dark picture means it's off.
    """
    r = _guard(bcam["snapshot"], save_to or None)
    return _with_picture(r, r.get("file"))


@mcp.tool()
def camera_check():
    """
    One print check (the camera watch uses this). Reads the printer's status
    first; only while it's printing does it take a picture. Look at the
    picture for: spaghetti (loose strands), a part knocked loose or moved,
    a layer shift, blobs or a nozzle clog (nothing coming out), and anything
    on the bed that shouldn't be. Then say plainly: OK, or the problem and how
    sure you are. Never stop or pause the print from here — tell the person,
    who stops it on the screen or in Handy (04 section 7).
    """
    status = _guard(bcl["printer_status"])
    state = status.get("state")
    brief = {k: status.get(k) for k in ("printer", "state", "job", "progress_pct",
                                        "layer", "total_layers", "remaining_min",
                                        "errors", "error")}
    if status.get("ok") is False or not state:
        brief["checked"] = False
        brief["note"] = "Couldn't read the printer's status, so no picture was taken."
        return _ok(brief)
    if state not in ("printing", "paused", "preparing"):
        brief["checked"] = False
        brief["note"] = ("Not printing (%s), so no picture was taken." % state)
        return _ok(brief)
    shot = _guard(bcam["snapshot"])
    brief["checked"] = bool(shot.get("ok"))
    brief["snapshot"] = shot.get("file")
    if not shot.get("ok"):
        brief["camera_error"] = shot.get("error")
    return _with_picture(brief, shot.get("file"))


@mcp.tool()
def monitor_mode(project: str = "", mode: str = "", every_min: float = 0,
                 why: str = "", windows: str = "") -> str:
    """
    How closely the print watch should follow a project's print. With no
    project: the modes and what each is for. With one: save the mode beside
    the project's newest 3MF (<name>.monitor.json), and the watch picks it up
    by itself when that job starts.
    modes: default (every 8 min) | early (30s bursts at the start, for batches
      of small or thin parts and wide flat ones) | complex (bursts, plus your
      layer windows over the fiddly parts) | tall (tightens with height) |
      overnight (fewer pictures, lower bar, acts first) | quick (test prints) |
      watch_only (records, never alerts).
    every_min: override the mode's cadence. windows: JSON like
      [{"from_layer": 40, "to_layer": 75, "every_min": 2, "why": "lattice"}]
      (from_pct/to_pct work too).
    """
    if not project or not mode:
        return _ok({"ok": True, "modes": {k: dict(v) for k, v in bmo["MODES"].items()},
                    "settings": sorted(bmo["BASE"])})
    over = {}
    if every_min:
        over["cadence_min"] = float(every_min)
    if why:
        over["why"] = why
    if windows:
        try:
            over["windows"] = json.loads(windows)
        except ValueError:
            return _fail('windows should be JSON, e.g. [{"from_layer": 40, "every_min": 2}]')
    three = _guard(bmo["_project_3mf"], project)
    if isinstance(three, dict):
        return _ok(three)
    return _ok(_guard(bmo["write_config"], three, mode, **over))


@mcp.tool()
def print_review(action: str = "list", note: str = "") -> str:
    """
    Detections the watch wants a second opinion on. action=list returns the
    oldest one waiting, with its picture, so you can look: is it a real
    failure? Then answer action=real (stops the print through Bambu Studio) or
    action=false (flags it a false positive in the project's error report; after
    3 of those the watch stops alerting on that print).
    """
    if action == "list":
        asks = bw["pending_reviews"]()
        if not asks:
            return _ok({"ok": True, "waiting": 0})
        ask = asks[0]
        return _with_picture({"ok": True, "waiting": len(asks), "review": ask},
                             ask.get("picture"))
    if action in ("real", "false"):
        return _ok(_guard(bw["answer_review"], action == "real", note))
    return _fail("action: list | real | false")


@mcp.tool()
def studio_stop(confirm: bool = False, test: bool = False) -> str:
    """
    Stop the running print by pressing Bambu Studio's own Stop button on this
    PC (the firmware refuses stop_print from here). Studio must be open on the
    Device tab, and the button has to have been pointed at once with
    `python tools/bambu_studio_ui.py calibrate stop`.
    test=true finds the window and buttons and clicks nothing. Stopping needs a
    yes: pass confirm=true only after the person said to stop this print.
    """
    if test:
        return _ok(_guard(bui["test"]))
    if not confirm:
        return _fail("Stopping a print can't be undone — ask first, then call with "
                     "confirm=true.")
    return _ok(_guard(bui["stop"]))


@mcp.tool()
def camera_watch(action: str = "status") -> str:
    """
    The background print watch on this PC (tools/bambu_watch.py): a picture
    every few minutes while printing, scored by Obico's spaghetti detector
    run locally with onnxruntime (or in Docker, or the Claude API); on a
    problem it tries to pause (the P1S firmware refuses) and pops up a window.
    action: status | setup (download the detector model) | test (score the
    newest snapshot) | once (one check now) | install (start with Windows, and
    start now) | uninstall | on | off.
    Settings: "camera_watch" in bambu_config (interval_min, alert_score,
    spike_score, judge...).
    """
    if action == "status":
        return _ok({"ok": True, "report": bw["status_report"]()})
    if action == "setup":
        det = runpy.run_path(os.path.join(TOOLS, "bambu_detect.py"))
        try:
            return _ok({"ok": True, "model": det["setup"](progress=False)})
        except det["DetectorError"] as exc:
            return _fail(str(exc))
    if action == "test":
        shots = sorted(f for f in os.listdir(bw["SNAP_DIR"]) if f.endswith(".jpg")) \
            if os.path.isdir(bw["SNAP_DIR"]) else []
        if not shots:
            return _fail("No snapshot yet — take one with camera_snapshot first.")
        pic = os.path.join(bw["SNAP_DIR"], shots[-1])
        try:
            det = bw["local_detect"](pic)
        except Exception as exc:
            return _fail(str(exc))
        return _ok({"ok": True, "picture": pic, "score": bw["obico_score"](det),
                    "detections": det})
    if action == "once":
        try:
            r = bw["check_once"]({})
        except Exception as exc:
            return _fail(str(exc))
        return _ok({k: v for k, v in r.items()})
    if action == "install":
        return _ok({"ok": True, "report": bw["install"]()})
    if action == "uninstall":
        return _ok({"ok": True, "report": bw["uninstall"]()})
    if action in ("on", "off"):
        cfg = read_config()
        cw = dict(cfg.get("camera_watch") or {})
        cw["enabled"] = action == "on"
        cfg["camera_watch"] = cw
        write_config(cfg)
        return _ok({"ok": True, "camera_watch": cw})
    return _fail("action must be status, setup, test, once, install, uninstall, on or off")


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
