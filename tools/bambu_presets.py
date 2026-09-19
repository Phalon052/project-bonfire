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
import json
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

# The filament_id the AMS reports for a slot set to a third-party brand's own
# preset (Studio's system presets). Used to find that brand's roll in the AMS.
BRAND_FILAMENT_IDS = {
    "OVERTURE PLA": "GFL04",
    "OVERTURE MATTE PLA": "GFL05",
    "OVERTURE PLA MATTE": "GFL05",
    "GENERIC PLA": "GFL99",
    "GENERIC PETG": "GFG99",
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


FILAMENT_PRESET_ROOTS = [
    os.path.expandvars(r"%APPDATA%\BambuStudio\system\BBL\filament"),
    os.path.expanduser("~/Library/Application Support/BambuStudio/system/BBL/filament"),
    os.path.expanduser("~/.config/BambuStudio/system/BBL/filament"),
]


def filament_preset_root():
    for root in FILAMENT_PRESET_ROOTS:
        if os.path.isdir(root):
            return root
    return ""


def installed_filament_presets():
    """Filament preset names Bambu Studio actually has installed, or ()."""
    root = filament_preset_root()
    if not root:
        return set()
    return {os.path.splitext(f)[0] for f in os.listdir(root) if f.endswith(".json")}


_PRESET_CACHE = {}


def _preset_file(name, root):
    path = os.path.join(root, name + ".json")
    if os.path.isfile(path):
        return path
    for folder, _, files in os.walk(root):
        if name + ".json" in files:
            return os.path.join(folder, name + ".json")
    return ""


def resolve_filament_preset(name, root=None, _depth=0):
    """
    A system filament preset with everything it inherits filled in — the
    values Studio itself uses for it: the parent chain, then its `include`
    templates, then its own keys. None when the files aren't here.
    """
    root = root if root is not None else filament_preset_root()
    if not root or not name or _depth > 12:
        return None
    key = (root, name)
    if key in _PRESET_CACHE:
        return _PRESET_CACHE[key]
    path = _preset_file(name, root)
    if not path:
        return None
    try:
        with open(path, encoding="utf-8") as fh:
            own = json.load(fh)
    except (OSError, ValueError):
        return None
    # Studio's order: the parent chain, then `include` templates on top (a
    # saved P1S project shows the dual-variant template's values winning over
    # the base preset's), then the preset's own keys.
    merged = {}
    parent = own.get("inherits")
    if parent:
        merged.update(resolve_filament_preset(parent, root, _depth + 1) or {})
    for inc in own.get("include") or []:
        merged.update(resolve_filament_preset(inc, root, _depth + 1) or {})
    merged.update(own)
    _PRESET_CACHE[key] = merged
    return merged


# Filament settings Studio 2.x keeps in project_settings without the
# "filament_" prefix (read from its own filament presets). Used when the
# preset files can't be read to work it out.
NON_PREFIXED_FILAMENT_KEYS = {
    "activate_air_filtration", "additional_cooling_fan_speed",
    "additional_fan_full_speed_layer", "chamber_temperatures",
    "circle_compensation_speed", "close_additional_fan_first_x_layers",
    "close_fan_the_first_x_layers", "complete_print_exhaust_fan_speed",
    "cool_plate_temp", "cool_plate_temp_initial_layer",
    "cooling_perimeter_transition_distance", "cooling_slowdown_logic",
    "counter_coef_1", "counter_coef_2", "counter_coef_3", "counter_limit_max",
    "counter_limit_min", "diameter_limit", "during_print_exhaust_fan_speed",
    "eng_plate_temp", "eng_plate_temp_initial_layer", "fan_cooling_layer_time",
    "fan_max_speed", "fan_min_speed", "full_fan_speed_layer", "hole_coef_1",
    "hole_coef_2", "hole_coef_3", "hole_limit_max", "hole_limit_min",
    "hot_plate_temp", "hot_plate_temp_initial_layer", "impact_strength_z",
    "long_retractions_when_ec", "no_slow_down_for_cooling_on_outwalls",
    "nozzle_temperature", "nozzle_temperature_initial_layer",
    "nozzle_temperature_range_high", "nozzle_temperature_range_low",
    "overhang_fan_speed", "overhang_fan_threshold",
    "override_process_overhang_speed", "reduce_fan_stop_start_freq",
    "required_nozzle_HRC", "retraction_distances_when_ec",
    "slow_down_for_layer_cooling", "slow_down_layer_time", "slow_down_min_speed",
    "supertack_plate_temp", "supertack_plate_temp_initial_layer",
    "temperature_vitrification", "textured_plate_temp",
    "textured_plate_temp_initial_layer", "volumetric_speed_coefficients",
}

DEFAULT_FLUSH_MM3 = "280"      # between two different filaments; unused
                               # when every plate has one filament


def expand_filaments(settings, filaments, root=None):
    """
    Turn a project_settings from a one-filament template into one with
    len(filaments) filaments, the way Studio writes it.

    Studio 2.x keeps a block of values per filament for every filament
    setting — 1 value for most, 2 for the per-nozzle-variant ones
    (filament_extruder_variant), 4 for the AMS drying ones — back to back.
    Each filament's block comes from its own system preset when the preset
    files are here (so PETG gets PETG temperatures), else from the template's.
    filaments: [{"preset", "id", "type", "colour"}...].
    """
    n = len(filaments)
    old_n = max(1, len(settings.get("filament_settings_id") or []) or 1)
    root = root if root is not None else filament_preset_root()
    template_preset = resolve_filament_preset(
        (settings.get("filament_settings_id") or [""])[0], root) or {}
    fkeys = {k for k, v in settings.items() if isinstance(v, list) and (
        k.startswith("filament_") or k in NON_PREFIXED_FILAMENT_KEYS
        or (k in template_preset and k not in ("compatible_printers",
                                                "include", "inherits")))}
    fkeys -= {"filament_self_index", "filament_settings_id"}
    # A filament on the template's own preset keeps the template's block
    # as-is, tweaks and all; others get their system preset's values.
    template_name = (settings.get("filament_settings_id") or [""])[0]
    presets = [None if f["preset"] == template_name
               else (resolve_filament_preset(f["preset"], root) or {})
               for f in filaments]

    for key in fkeys:
        value = settings[key]
        if len(value) % old_n:
            continue                        # not a per-filament list after all
        size = len(value) // old_n
        first = value[:size]
        out = []
        for p in presets:
            mine = None if p is None else p.get(key)
            if isinstance(mine, list) and len(mine) == size:
                out.extend(str(x) for x in mine)
            elif isinstance(mine, list) and len(mine) == 1:
                out.extend([str(mine[0])] * size)   # one value for every variant
            elif isinstance(mine, str):
                out.extend([mine] * size)
            else:
                out.extend(first)
        settings[key] = out

    variants = len(settings.get("filament_extruder_variant") or []) // n or 1
    settings["filament_self_index"] = [str(i + 1) for i in range(n)
                                       for _ in range(variants)]
    settings["filament_settings_id"] = [f["preset"] for f in filaments]
    settings["filament_ids"] = [f["id"] for f in filaments]
    settings["filament_type"] = [f["type"] for f in filaments]
    settings["filament_colour"] = [f["colour"] for f in filaments]
    if "filament_multi_colour" in settings:
        settings["filament_multi_colour"] = [f["colour"] for f in filaments]
    for key in ("filament_map", "filament_nozzle_map"):
        if key in settings:
            settings[key] = ["1"] * n
    if "filament_volume_map" in settings:
        settings["filament_volume_map"] = ["0"] * n
    if "flush_volumes_matrix" in settings:
        settings["flush_volumes_matrix"] = [
            "0" if i == j else DEFAULT_FLUSH_MM3 for i in range(n) for j in range(n)]
    vec = settings.get("flush_volumes_vector")
    if isinstance(vec, list) and vec:
        per = max(1, len(vec) // old_n)
        settings["flush_volumes_vector"] = (vec[:per] * n)
    diff = settings.get("different_settings_to_system")
    if isinstance(diff, list) and len(diff) == old_n + 2:
        settings["different_settings_to_system"] = (
            [diff[0]] + [diff[1]] * n + [diff[-1]])
    return settings


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
        old_colours = settings.get("filament_colour") or []
        for i, f in enumerate(fil):
            if i < len(old_colours) and len(fil) == 1:
                f["colour"] = old_colours[i]
        expand_filaments(settings, fil)
        settings.update({k: str(v) for k, v in (overrides or {}).items()})
        if not settings.get("filament_colour"):
            settings["filament_colour"] = ["#00AE42"]
        return settings, "template", application

    return (minimal_project_settings(materials, overrides, process, installed),
            "minimal", None)


# Colour words that may follow a material name ("Overture PLA black").
COLOUR_WORDS = {
    "BLACK": "#000000", "WHITE": "#FFFFFF", "GREY": "#808080", "GRAY": "#808080",
    "SILVER": "#C0C0C0", "RED": "#E0201B", "ORANGE": "#FF8000",
    "YELLOW": "#F4EE2A", "GREEN": "#00AE42", "BLUE": "#0A2CE0",
    "PURPLE": "#7D3C98", "PINK": "#F4A6C0", "BROWN": "#7B4B2A",
    "BEIGE": "#E8D8B0", "CLEAR": "#F0F0F0", "NATURAL": "#F0EAD6",
}


def filament_key(name):
    """One filament = one brand/type/colour as written: "Overture PLA black"
    and "Overture PLA white" are different filaments, "overture pla Black" and
    "Overture PLA black" the same one."""
    return " ".join(str(name or DEFAULT_MATERIAL).upper().replace("-", " ").split())


def colour_hint(name):
    """The colour a material name asks for, as #RRGGBB, or None."""
    for word in filament_key(name).split():
        if word in COLOUR_WORDS:
            return COLOUR_WORDS[word]
    return None


def _colour_distance(a, b):
    try:
        ca = [int(a.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4)]
        cb = [int(b.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4)]
    except (ValueError, AttributeError):
        return 999.0
    return sum((x - y) ** 2 for x, y in zip(ca, cb)) ** 0.5


CLOSE_COLOUR = 110.0          # RGB distance still read as "that colour"


def match_loaded_slots(materials, loaded):
    """
    For each material (slot order), the AMS slot currently holding a roll of
    it, or None. `loaded` is bambu_cloud.parse_ams() output. Best match first:
    the exact filament (its filament_id — Bambu PLA Basic, or a third-party
    brand's own preset), then the same type (PLA, PETG...). When the name
    carries a colour ("... black"), only a roll close to that colour counts.
    A roll is given to one material only, and the lowest slot wins a tie.
    """
    rolls = [t for t in (loaded or []) if t.get("loaded") and t.get("type")]
    taken, out = set(), []
    for m in materials:
        key = filament_key(m)
        entry = FILAMENTS[resolve_material(m)]
        brand = next((b for b in sorted(BRAND_FILAMENT_IDS, key=len, reverse=True)
                      if key.startswith(b)), None)
        want_id = BRAND_FILAMENT_IDS[brand] if brand else entry["id"]
        free = [t for t in rolls if str(t["slot"]) not in taken]
        exact = [t for t in free if t.get("filament_id") == want_id]
        same_type = [t for t in free if str(t["type"]).upper() == entry["type"]]
        hint = colour_hint(m)
        if hint:
            # A named colour beats the brand: the black roll of any PLA
            # prints "PLA black" better than the yellow roll of the brand.
            near = lambda ts: sorted((t for t in ts if _colour_distance(
                t.get("colour"), hint) <= CLOSE_COLOUR),
                key=lambda t: _colour_distance(t.get("colour"), hint))
            pick = near(exact) or near(same_type)
            hit = pick[0] if pick else None
        else:
            hit = (exact or same_type or [None])[0]
        if hit:
            taken.add(str(hit["slot"]))
        out.append(hit)
    return out
