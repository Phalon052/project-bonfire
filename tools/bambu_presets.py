"""
Bambu Studio preset names for the P1S, and the project_settings.config that
goes inside a project 3MF.

Two ways to get those settings, and the difference matters:

  * **Template (preferred).** A project saved once from Bambu Studio with the
    right presets selected. Its project_settings.config is a full flattened
    dump of every setting, so everything this project doesn't touch stays
    exactly at Bambu's defaults. Put it at `tools/bambu_template.3mf`.
  * **Minimal (fallback).** Built here from scratch. Studio still opens it as a
    project and still selects the named presets, but any key not listed starts
    from the slicer's built-in default rather than the preset's value.
    Usable, not equivalent. Anything built this way says so in its report.

Checked against a real project saved from Bambu Studio 01.09.07.52 on this
machine — which settled two things the documentation doesn't:

  * Studio writes **no** `inherits_group` and **no**
    `different_settings_to_system` for unmodified system presets. It just names
    them. So the template path adds neither.
  * That Studio picked `Bambu PLA Basic @BBL X1C` for the P1S, not the
    `@BBL P1S` name that exists in newer profile bundles. Filament preset names
    move between Studio versions, so each material lists its known names and
    the first one actually installed wins.

Preset names verified against BambuStudio's resources/profiles/BBL:
  machine   Bambu Lab P1S 0.4 nozzle          (no @BBL suffix)
  process   0.20mm Standard @BBL X1C          (the P1S shares the X1C family —
                                               there are no @BBL P1S processes)
Don't judge a filament preset by its suffix; check its compatible_printers.
"""
import os
import runpy

_HERE = os.path.dirname(os.path.abspath(__file__))

PRINTER_MODEL = "Bambu Lab P1S"
PRINTER_VARIANT = "0.4"
MACHINE_PRESET = "Bambu Lab P1S 0.4 nozzle"
PROCESS_PRESET = "0.20mm Standard @BBL X1C"

# The process presets the P1S 0.4 can use, best quality first.
PROCESS_PRESETS = [
    "0.08mm Extra Fine @BBL X1C",
    "0.08mm High Quality @BBL X1C",
    "0.12mm Fine @BBL X1C",
    "0.12mm High Quality @BBL X1C",
    "0.16mm High Quality @BBL X1C",
    "0.16mm Optimal @BBL X1C",
    "0.20mm Standard @BBL X1C",
    "0.20mm Strength @BBL X1C",
    "0.24mm Draft @BBL X1C",
    "0.28mm Extra Draft @BBL X1C",
]

# Material name (as it appears after MAT: in a drawing) -> filament presets,
# most specific first. The first name installed in Bambu Studio is used; if
# Studio can't be found, the first name is used as-is.
FILAMENTS = {
    "PLA":          {"presets": ["Bambu PLA Basic @BBL P1S 0.4 nozzle",
                                 "Bambu PLA Basic @BBL X1C"],
                     "id": "GFA00", "type": "PLA", "colour": "#00AE42"},
    "PLA BASIC":    {"presets": ["Bambu PLA Basic @BBL P1S 0.4 nozzle",
                                 "Bambu PLA Basic @BBL X1C"],
                     "id": "GFA00", "type": "PLA", "colour": "#00AE42"},
    "PLA MATTE":    {"presets": ["Bambu PLA Matte @BBL P1S 0.4 nozzle",
                                 "Bambu PLA Matte @BBL X1C"],
                     "id": "GFA01", "type": "PLA", "colour": "#F4EE2A"},
    "PETG":         {"presets": ["Bambu PETG HF @BBL P1S 0.4 nozzle",
                                 "Bambu PETG Basic @BBL X1C",
                                 "Bambu PETG HF @BBL X1C"],
                     "id": "GFG02", "type": "PETG", "colour": "#0086D6"},
    "PETG HF":      {"presets": ["Bambu PETG HF @BBL P1S 0.4 nozzle",
                                 "Bambu PETG HF @BBL X1C"],
                     "id": "GFG02", "type": "PETG", "colour": "#0086D6"},
    "PETG BASIC":   {"presets": ["Bambu PETG Basic @BBL X1C"],
                     "id": "GFG00", "type": "PETG", "colour": "#0086D6"},
    "ABS":          {"presets": ["Bambu ABS @BBL P1S 0.4 nozzle",
                                 "Bambu ABS @BBL X1C"],
                     "id": "GFB00", "type": "ABS", "colour": "#FFFFFF"},
    "TPU":          {"presets": ["Bambu TPU 95A HF @BBL P1S",
                                 "Bambu TPU 95A @BBL X1C"],
                     "id": "GFU02", "type": "TPU", "colour": "#000000"},
}

# Third-party brands mapped to the Bambu preset that prints them (03 §2).
MATERIAL_ALIASES = {
    "OVERTURE PLA": "PLA",
    "OVERTURE PETG": "PETG",
    "GENERIC PLA": "PLA",
    "GENERIC PETG": "PETG",
}

DEFAULT_MATERIAL = "PLA"
TEMPLATE_NAME = "bambu_template.3mf"


def resolve_material(name):
    """A MAT: marker or a spoken material name -> a key in FILAMENTS."""
    if not name:
        return DEFAULT_MATERIAL
    key = " ".join(str(name).upper().replace("-", " ").split())
    if key in MATERIAL_ALIASES:
        key = MATERIAL_ALIASES[key]
    if key in FILAMENTS:
        return key
    for known in sorted(FILAMENTS, key=len, reverse=True):
        if key.startswith(known) or known in key:
            return known
    return DEFAULT_MATERIAL


def installed_filament_presets():
    """Filament preset names Bambu Studio actually has installed, or ()."""
    roots = [os.path.expandvars(r"%APPDATA%\BambuStudio\system\BBL\filament"),
             os.path.expanduser("~/Library/Application Support/BambuStudio/"
                                "system/BBL/filament"),
             os.path.expanduser("~/.config/BambuStudio/system/BBL/filament")]
    for root in roots:
        if os.path.isdir(root):
            return {os.path.splitext(f)[0] for f in os.listdir(root)
                    if f.endswith(".json")}
    return set()


def filament_preset(material, installed=None, prefer=None):
    """The preset name to use for a material: one the user's Studio has, one
    the template already used, or the first known name."""
    entry = FILAMENTS[resolve_material(material)]
    names = entry["presets"]
    if prefer and prefer in names:
        return prefer
    if installed is None:
        installed = installed_filament_presets()
    for name in names:
        if name in installed:
            return name
    return names[0]


def template_path(root):
    return os.path.join(root, "tools", TEMPLATE_NAME)


def _filament_block(materials, installed=None, prefer=None):
    """Per-slot filament values, in AMS-slot order."""
    installed = installed_filament_presets() if installed is None else installed
    keys = [resolve_material(m) for m in materials]
    prefer = prefer or []
    out = []
    for i, k in enumerate(keys):
        entry = FILAMENTS[k]
        want = prefer[i] if i < len(prefer) else None
        out.append({"preset": filament_preset(k, installed, want),
                    "id": entry["id"], "type": entry["type"],
                    "colour": entry["colour"]})
    return out


def minimal_project_settings(materials=None, overrides=None,
                             process=PROCESS_PRESET, installed=None):
    """
    A project_settings.config built from scratch. `materials` is the list of
    filament slots in order (slot 1 first). Every value is a string or a list
    of strings — the format Bambu writes and its reader expects.
    """
    fil = _filament_block(materials or [DEFAULT_MATERIAL], installed)
    n = len(fil)
    settings = {
        "version": "01.09.00.00",
        "name": "project_settings",
        "from": "project",
        "printer_technology": "FFF",
        "printer_model": PRINTER_MODEL,
        "printer_variant": PRINTER_VARIANT,
        "nozzle_diameter": [PRINTER_VARIANT],
        "print_settings_id": process,
        "printer_settings_id": MACHINE_PRESET,
        "filament_settings_id": [f["preset"] for f in fil],
        "filament_ids": [f["id"] for f in fil],
        "filament_colour": [f["colour"] for f in fil],
        "filament_type": [f["type"] for f in fil],
        "filament_diameter": ["1.75"] * n,
        "curr_bed_type": "Textured PEI Plate",
        # supports and raft, off until a suggestion turns them on
        "enable_support": "0",
        "support_type": "normal(auto)",
        "support_on_build_plate_only": "0",
        "support_filament": "0",
        "support_interface_filament": "0",
        "raft_layers": "0",
        "brim_type": "auto_brim",
    }
    settings.update({k: str(v) for k, v in (overrides or {}).items()})
    return settings


def project_settings(root=None, materials=None, overrides=None,
                     process=PROCESS_PRESET, template=None):
    """
    The settings to embed, from the template when there is one.
    Returns (settings, source, application) where source is "template" or
    "minimal" and application is the Application string to write (the
    template's, so the file never claims a newer Studio than the installed one).
    """
    path = template or (template_path(root) if root else None)
    materials = materials or [DEFAULT_MATERIAL]
    installed = installed_filament_presets()

    if path and os.path.isfile(path):
        b3 = runpy.run_path(os.path.join(_HERE, "bambu_3mf.py"))
        settings = dict(b3["read_project_settings"](path))
        application = b3["read_application"](path) or None

        settings["print_settings_id"] = process
        settings["printer_settings_id"] = MACHINE_PRESET
        settings["printer_model"] = PRINTER_MODEL
        # Keep the template's own preset for a slot whose material matches, so
        # the name is one this Studio definitely has.
        old_presets = settings.get("filament_settings_id") or []
        old_types = settings.get("filament_type") or []
        prefer = []
        for i, m in enumerate(materials):
            want = FILAMENTS[resolve_material(m)]["type"]
            match = next((p for j, p in enumerate(old_presets)
                          if j < len(old_types) and old_types[j] == want), None)
            prefer.append(match)
        fil = _filament_block(materials, installed, prefer)
        n = len(fil)
        old_colours = settings.get("filament_colour") or []
        settings["filament_settings_id"] = [f["preset"] for f in fil]
        settings["filament_ids"] = [f["id"] for f in fil]
        settings["filament_type"] = [f["type"] for f in fil]
        settings["filament_colour"] = [
            old_colours[i] if i < len(old_colours) else fil[i]["colour"]
            for i in range(n)]
        settings["filament_diameter"] = ["1.75"] * n
        # Any other per-slot list has to match the new slot count.
        for key, value in list(settings.items()):
            if key.startswith("filament_") and isinstance(value, list) \
                    and len(value) not in (n, 0):
                settings[key] = [value[i] if i < len(value) else value[-1]
                                 for i in range(n)]
        settings.update({k: str(v) for k, v in (overrides or {}).items()})
        if not settings.get("filament_colour"):
            settings["filament_colour"] = ["#00AE42"]
        return settings, "template", application

    return (minimal_project_settings(materials, overrides, process, installed),
            "minimal", None)
