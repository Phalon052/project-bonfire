"""
Project Bonfire — Bambu tools (Layer A: everything up to, but not including,
the slicer and the printer).

The rules in `04_bambu_basics.md` live here as code, so they are applied the
same way every time instead of being remembered:

  * section 2 — the approved settings list, and the locked settings that can't
    be changed without an explicit request (the settings guard).
  * section 2 — when to use supports, which type, build-plate-only, and raft.
  * section 3 — orientation: strength first, then largest flat face, then
    fewest supports.
  * section 4 — getting parts ready: newest STL of each part, Quantity copies,
    filament per part, hardware committed, and what the report must say.

Use it like the other Bonfire tools:

    import os, runpy
    ROOT = os.environ.get("BONFIRE_HOME") or os.path.expanduser(r"~\\Desktop\\Project Bonfire")
    bb = runpy.run_path(os.path.join(ROOT, "tools", "bambu.py"))
    print(bb["inspect_model"](r"...\\stl\\bracket_3.stl"))
    print(bb["prepare_print"]("shelf bracket"))

Nothing here talks to the printer or runs the slicer — that is Layers B and C.
Nothing here starts a print.
"""
import math
import os
import re
import runpy

_HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(_HERE)

bm = runpy.run_path(os.path.join(_HERE, "bambu_mesh.py"))
b3 = runpy.run_path(os.path.join(_HERE, "bambu_3mf.py"))
bpre = runpy.run_path(os.path.join(_HERE, "bambu_presets.py"))
bp = runpy.run_path(os.path.join(_HERE, "paths.py"))
bsl = runpy.run_path(os.path.join(_HERE, "bambu_slice.py"))


# ── the build volume ─────────────────────────────────────────────────

BUILD_VOLUME_MM = (256.0, 256.0, 256.0)     # P1S, 04 section 1
PLATE_MARGIN_MM = 4.0                        # keep parts off the very edge
DEFAULT_SPACING_MM = 6.0                     # Bambu's arrange default

# The P1S has a no-print patch in the front-left corner of the bed
# (bed_exclude_area "0x0,18x0,18x28,0x28" in its machine preset). A part — or
# its brim — inside it fails with "too close to exclusion area".
BED_EXCLUDE_AREAS = [(0.0, 0.0, 18.0, 28.0)]
# Bambu's auto brim is up to 5 mm wide, so keep that much clear of the patch.
BRIM_MARGIN_MM = 5.0
# A raft spreads this far past the part on the first layer
# (raft_first_layer_expansion in the P1S process preset).
RAFT_EXPANSION_MM = 2.0
# Clear air between two parts' brims/rafts, on top of their own clearance.
MIN_GAP_MM = 2.0


def part_clearance(raft=False, brim=True):
    """How far a part's first layer reaches past its own outline: the brim,
    plus the raft's spread when it has one. Two parts closer than the sum of
    their clearances print toolpaths into each other — Studio then refuses the
    plate with "gcode path conflicts" (exit -101)."""
    return (BRIM_MARGIN_MM if brim else 0.0) + (RAFT_EXPANSION_MM if raft else 0.0)


# ── the settings guard (04 section 2) ────────────────────────────────

# Changeable without asking, and the only values allowed.
APPROVED_SETTINGS = {
    "enable_support": {"0", "1"},
    "support_type": {"normal(auto)", "tree(auto)"},
    "support_on_build_plate_only": {"0", "1"},
    "raft_layers": None,                     # 0 = off, 2 = on (04 section 2)
}

# Never changed unless the user asks for it in so many words.
LOCKED_SETTINGS = (
    "wall_loops", "wall_thickness", "outer_wall_line_width", "inner_wall_line_width",
    "sparse_infill_density", "sparse_infill_pattern", "infill_direction",
    "top_shell_layers", "bottom_shell_layers", "top_shell_thickness",
    "bottom_shell_thickness",
    "nozzle_temperature", "nozzle_temperature_initial_layer",
    "hot_plate_temp", "cool_plate_temp", "textured_plate_temp",
    "bed_temperature", "chamber_temperature",
    "filament_flow_ratio", "flow_ratio", "print_flow_ratio",
    "layer_height", "initial_layer_print_height",
)
_LOCKED_HINTS = ("speed", "acceleration", "jerk", "flow", "temperature", "temp")

RAFT_LAYERS_ON = 2


class SettingRefused(Exception):
    """A settings change the rules don't allow without asking."""


def is_locked(key):
    if key in LOCKED_SETTINGS:
        return True
    return any(h in key for h in _LOCKED_HINTS)


def guard_settings(changes, user_requested=None):
    """
    Every settings change passes through here (04 section 2).

    changes: {"support_type": "tree(auto)", ...}
    user_requested: the user's own words, when they explicitly asked for a
        locked setting to be changed. Without it, a locked key is refused.

    Returns the changes, unchanged, or raises SettingRefused.
    """
    changes = {k: str(v) for k, v in (changes or {}).items()}
    for key, value in changes.items():
        if key in APPROVED_SETTINGS:
            allowed = APPROVED_SETTINGS[key]
            if allowed is not None and value not in allowed:
                raise SettingRefused(
                    "%s=%s is not one of the approved values (%s) — 04 section 2"
                    % (key, value, ", ".join(sorted(allowed))))
            if key == "raft_layers" and value not in ("0", str(RAFT_LAYERS_ON)):
                raise SettingRefused(
                    "raft_layers must be 0 (off) or %d (on) — 04 section 2"
                    % RAFT_LAYERS_ON)
            continue
        if is_locked(key):
            if not user_requested:
                raise SettingRefused(
                    "%s is a locked setting (walls, infill, speed, temperatures, "
                    "flow). 04 section 2 says never change it unless asked. Pass "
                    "the user's own words as user_requested to allow it." % key)
            continue
        raise SettingRefused(
            "%s is not on the approved list and is not a known locked setting. "
            "04 section 2 says ask first." % key)
    return changes


def get_rules():
    """What the rules currently say — so a print task can check them up front."""
    return {
        "printer": "Bambu Lab P1S, AMS 4 slots, 0.4 mm nozzle",
        "build_volume_mm": list(BUILD_VOLUME_MM),
        "approved_without_asking": {
            "enable_support": "on when overhangs would cause print errors",
            "support_type": "normal(auto) for large overhangs; tree(auto) for "
                            "many small or thin ones; normal(auto) when both",
            "support_on_build_plate_only": "on when supports need only stand on "
                                           "the bed",
            "raft_layers": "%d when the footprint is thin, or small compared to "
                           "the height" % RAFT_LAYERS_ON,
            "also": "orienting, arranging/packing the plate, slicing, and saving "
                    "the sliced file",
        },
        "never_change_without_asking": list(LOCKED_SETTINGS),
        "needs_approval_every_time": [
            "starting a print (show the summary, then wait for a yes)",
            "stopping a print",
        ],
        "optimize_for": "strength, then less support/material, then print time — "
                        "all within Bambu's default settings",
        "source": "04_bambu_basics.md sections 1-4 and 7",
    }


# ── inspecting a model ───────────────────────────────────────────────

def inspect_model(path, threshold_deg=None):
    """Size, solidity and fit for one STL or 3MF."""
    mesh = bm["load_mesh"](path)
    mesh, _ = bm["drop_to_bed"](mesh)
    report = bm["mesh_report"](mesh)
    size = report["bbox_mm"]
    fits = all(size[a] <= BUILD_VOLUME_MM[i] - 2 * PLATE_MARGIN_MM
               for i, a in enumerate("xyz"))
    foot = bm["footprint"](mesh)
    report.update({
        "path": path,
        "fits_build_volume": fits,
        "build_volume_mm": list(BUILD_VOLUME_MM),
        "footprint_mm2": foot["area_mm2"],
        "footprint_x_mm": foot["x"],
        "footprint_y_mm": foot["y"],
        "footprint_to_height": (foot["min_dim_mm"] / size["z"]) if size["z"] else 0,
    })
    if not fits:
        report["warning"] = (
            "%.1f x %.1f x %.1f mm doesn't fit the P1S's %d mm cube — it needs "
            "splitting (04 section 5)."
            % (size["x"], size["y"], size["z"], int(BUILD_VOLUME_MM[0])))
    if not report["closed_solid"]:
        report["warning_mesh"] = (
            "not a closed solid: %d naked edges, %d over-used edges. It may "
            "still slice, but check it." % (report["naked_edges"],
                                            report["overused_edges"]))
    return report


# ── supports (04 section 2) ──────────────────────────────────────────

# An overhang patch this big counts as a "large overhang surface".
LARGE_OVERHANG_MM2 = 100.0
# Below this, a patch is a "small overhang".
SMALL_OVERHANG_MM2 = 25.0
# Fewer overhangs than this in total is not worth supporting at all.
IGNORE_OVERHANG_MM2 = 10.0
# "Many" small overhangs.
MANY_ISLANDS = 4

# Patches this small print fine unsupported: engraved lettering, the facets of
# a round hole, small chamfers. Slicers ignore them and so do we — otherwise
# every labelled part comes back asking for tree supports it doesn't need.
NOISE_ISLAND_MM2 = 2.0
NOISE_ISLAND_SPAN_MM = 2.0


def _real_islands(islands):
    return [i for i in islands
            if i["area_mm2"] >= NOISE_ISLAND_MM2
            and i["span_mm"] >= NOISE_ISLAND_SPAN_MM]


def suggest_supports(path, threshold_deg=None):
    """
    Overhang analysis, turned into the 04 section 2 decision:
    none, normal(auto), or tree(auto); and build-plate-only or not.
    """
    threshold = bm["DEFAULT_SUPPORT_THRESHOLD_DEG"] if threshold_deg is None \
        else threshold_deg
    mesh = bm["load_mesh"](path) if isinstance(path, str) else path
    mesh, _ = bm["drop_to_bed"](mesh)
    shallow = bm["overhang_faces"](mesh, threshold)
    grid = bm["build_xy_grid"](mesh)
    faces = bm["unsupported_faces"](mesh, shallow, grid=grid)
    self_supported = len(shallow) - len(faces)
    all_islands = bm["overhang_islands"](mesh, faces)
    islands = _real_islands(all_islands)
    ignored = len(all_islands) - len(islands)
    total = sum(i["area_mm2"] for i in islands)
    large = [i for i in islands if i["area_mm2"] >= LARGE_OVERHANG_MM2]
    small = [i for i in islands if i["area_mm2"] < SMALL_OVERHANG_MM2]

    result = {
        "threshold_deg": threshold,
        "overhang_area_mm2": total,
        "overhang_islands": len(islands),
        "largest_island_mm2": islands[0]["area_mm2"] if islands else 0.0,
        "large_islands": len(large),
        "small_islands": len(small),
        "ignored_tiny_islands": ignored,
        "self_supporting_faces": self_supported,
    }

    if total <= IGNORE_OVERHANG_MM2 or not islands:
        extra = ("" if not ignored else
                 " (%d patch%s too small to matter — lettering, hole facets and "
                 "the like — were ignored)"
                 % (ignored, "" if ignored == 1 else "es"))
        result.update({
            "enable_support": False, "support_type": None,
            "support_on_build_plate_only": None,
            "reason": "No overhangs shallower than %g degrees worth supporting"
                      "%s, so no supports." % (threshold, extra),
        })
        return result

    has_large = bool(large)
    many_small = len(small) >= MANY_ISLANDS
    if has_large and many_small:
        stype, why = "normal(auto)", (
            "%d large overhang surface%s and %d small ones — 04 section 2 says "
            "normal(auto) when there are both."
            % (len(large), "" if len(large) == 1 else "s", len(small)))
    elif has_large:
        stype, why = "normal(auto)", (
            "%d large overhang surface%s (biggest %.0f mm2) — normal(auto)."
            % (len(large), "" if len(large) == 1 else "s",
               islands[0]["area_mm2"]))
    elif many_small:
        stype, why = "tree(auto)", (
            "%d small or thin overhangs and no large surface — tree(auto)."
            % len(small))
    else:
        stype, why = "normal(auto)", (
            "%d overhang%s totalling %.0f mm2, none of them large — "
            "normal(auto) is the safe choice."
            % (len(islands), "" if len(islands) == 1 else "s", total))

    # Can the supports all stand on the plate, or does the part get in the way?
    on_part = []
    for isl in islands:
        if bm["geometry_below"](mesh, isl["centroid"], isl["z_min"], faces):
            on_part.append(isl)
    plate_only = not on_part
    if plate_only:
        plate_why = ("Nothing sits under the overhangs, so the supports can all "
                     "stand on the bed.")
    else:
        plate_why = ("%d overhang%s ha%s part of the model underneath, so "
                     "supports have to stand on the part too."
                     % (len(on_part), "" if len(on_part) == 1 else "s",
                        "s" if len(on_part) == 1 else "ve"))

    result.update({
        "enable_support": True,
        "support_type": stype,
        "support_on_build_plate_only": plate_only,
        "reason": why + " " + plate_why,
    })
    return result


# ── raft (04 section 2) ──────────────────────────────────────────────

# A footprint at least this wide in both directions is stable on its own.
STABLE_FOOTPRINT_MM = 30.0
# Below this, the footprint is small however tall the part is.
TINY_FOOTPRINT_MM = 10.0
# Tall-and-narrow: the screw example is 15 mm wide and 35 mm tall.
NARROW_FOOTPRINT_MM = 15.0
TALL_RATIO = 35.0 / 15.0


def suggest_raft(path):
    """
    The 04 section 2 raft rule, with its own examples as the test cases:
      raft     — a screw head under 15 mm across and 35 mm or taller
               — a part standing on feet under 10 mm square
      no raft  — a bearing 15 mm or less across and under 1.5x as tall
               — a base larger than about 30 x 30 mm, even if 3x as tall
    """
    mesh = bm["load_mesh"](path) if isinstance(path, str) else path
    mesh, _ = bm["drop_to_bed"](mesh)
    foot = bm["footprint"](mesh)
    height = bm["bbox"](mesh)["size"][2]
    w = foot["min_dim_mm"]
    ratio = (height / w) if w else float("inf")

    facts = {"footprint_x_mm": foot["x"], "footprint_y_mm": foot["y"],
             "footprint_min_mm": w, "footprint_area_mm2": foot["area_mm2"],
             "height_mm": height, "height_to_footprint": ratio,
             "raft_layers": 0}

    if w >= STABLE_FOOTPRINT_MM:
        facts.update({"raft": False, "reason":
                      "The footprint is %.0f x %.0f mm, bigger than about "
                      "30 x 30, so it's stable on its own even at %.0f mm tall."
                      % (foot["x"], foot["y"], height)})
    elif w > 0 and w < TINY_FOOTPRINT_MM:
        facts.update({"raft": True, "raft_layers": RAFT_LAYERS_ON, "reason":
                      "It stands on only %.1f mm of bed in the narrow "
                      "direction — under 10 mm, so a raft." % w})
    elif w < NARROW_FOOTPRINT_MM and ratio >= TALL_RATIO:
        facts.update({"raft": True, "raft_layers": RAFT_LAYERS_ON, "reason":
                      "The footprint is %.1f mm across and the part is %.0f mm "
                      "tall (%.1fx), thin compared to its height, so a raft."
                      % (w, height, ratio)})
    elif ratio >= TALL_RATIO * 1.5:
        facts.update({"raft": True, "raft_layers": RAFT_LAYERS_ON, "reason":
                      "It is %.1fx as tall as its footprint is wide (%.1f mm), "
                      "so a raft." % (ratio, w)})
    else:
        facts.update({"raft": False, "reason":
                      "A %.1f mm footprint under a %.0f mm part (%.1fx) is "
                      "stable enough — no raft." % (w, height, ratio)})
    return facts


# ── orientation (04 section 3) ───────────────────────────────────────

# Two ways up "sit on about as much bed" when the smaller footprint is at
# least this fraction of the biggest.
COMPARABLE_FOOTPRINT = 0.6

LOAD_BEARING_WORDS = ("bracket", "hook", "mount", "arm", "clip", "hinge",
                      "lever", "handle", "latch", "support", "hanger", "clamp",
                      "holder", "leg", "foot", "shelf", "joint", "spring")


def looks_load_bearing(name):
    n = str(name).lower()
    return any(w in n for w in LOAD_BEARING_WORDS)


def orientation_candidates(mesh, limit=5):
    """
    Ways up worth trying: as modelled, then the biggest flat faces laid down.
    Each candidate carries the rotation that gets there.
    """
    out = [{"mode": "keep", "matrix": bm["_identity"](),
            "label": "as modelled in Blender"}]
    for g in bm["flat_face_candidates"](mesh, limit=limit):
        n = g["normal"]
        if abs(n[0]) < 1e-6 and abs(n[1]) < 1e-6 and n[2] < 0:
            continue                      # already the face on the bed
        out.append({
            "mode": "lay_on_face",
            "matrix": bm["rotation_to"](n),
            "label": "%.0f mm2 face down" % g["area"],
            "face_area_mm2": g["area"],
        })
    return out


def score_orientation(mesh, name="", accurate=False):
    """
    What one way up costs: support area, footprint, height.

    `accurate` also works out which overhangs have a real drop under them, the
    way suggest_supports does. It costs a ray-cast per face, so ranking uses
    the cheap angle-only measure and only the chosen way up is measured
    properly — otherwise a threaded part takes half a minute to orient.
    """
    m, _ = bm["drop_to_bed"](mesh)
    faces = bm["overhang_faces"](m)
    if accurate:
        faces = bm["unsupported_faces"](m, faces)
    islands = _real_islands(bm["overhang_islands"](m, faces)) if accurate \
        else bm["overhang_islands"](m, faces)
    foot = bm["footprint"](m)
    size = bm["bbox"](m)["size"]
    return {
        "overhang_area_mm2": sum(i["area_mm2"] for i in islands),
        "overhang_islands": len(islands),
        "footprint_mm2": foot["area_mm2"],
        "footprint_min_mm": foot["min_dim_mm"],
        "height_mm": size[2],
        "size_mm": list(size),
        "fits": all(size[i] <= BUILD_VOLUME_MM[i] - 2 * PLATE_MARGIN_MM
                    for i in range(3)),
    }


def compare_orientations(path, name=None, candidates=4):
    """
    Try the likely ways up and pick one by 04 section 3: strength first when the
    part looks load-bearing, then largest flat face, then fewest supports.
    Returns every candidate with its numbers, and which one was chosen and why.
    """
    mesh = bm["load_mesh"](path) if isinstance(path, str) else path
    name = name or mesh.get("name", "")
    load_bearing = looks_load_bearing(name)

    rows = []
    for cand in orientation_candidates(mesh, limit=candidates):
        placed = bm["transform_mesh"](mesh, cand["matrix"])
        row = dict(cand)
        row.pop("matrix", None)
        row["_matrix"] = cand["matrix"]
        row.update(score_orientation(placed, name))
        rows.append(row)

    usable = [r for r in rows if r["fits"]] or rows
    if load_bearing:
        # 04 section 3 step 1: the layer direction was chosen in Blender for
        # the load it carries, so keep it.
        chosen = next((r for r in usable if r["mode"] == "keep"), usable[0])
        lead = ("'%s' reads as load-bearing, so 04 section 3 keeps the "
                "orientation it was modelled in — the layer lines were chosen "
                "for the load." % name)
    else:
        # Step 2 decides: largest flat face on the bed. Step 3, fewest
        # supports, is only the tie-break between ways up that sit on a
        # comparable amount of bed. The other way round stands a hex nut on
        # its edge to save a few mm2 of support.
        best = max(r["footprint_mm2"] for r in usable)
        comparable = [r for r in usable
                      if r["footprint_mm2"] >= best * COMPARABLE_FOOTPRINT]
        chosen = min(comparable, key=lambda r: (r["overhang_area_mm2"],
                                                -r["footprint_mm2"],
                                                0 if r["mode"] == "keep" else 1))
        if len(comparable) == 1:
            lead = ("Largest flat face down: %.0f mm2 on the bed, more than any "
                    "other way up." % chosen["footprint_mm2"])
        else:
            lead = ("Largest flat face down (%.0f mm2 on the bed), and the "
                    "best of the %d ways up that sit on about as much bed."
                    % (chosen["footprint_mm2"], len(comparable)))
        if chosen["mode"] == "keep":
            lead += " That is how it was modelled in Blender."

    # The ranking above used the cheap angle-only measure, which counts a
    # thread's underside as an overhang. Measure the chosen way up properly
    # before saying anything about support.
    real = score_orientation(bm["transform_mesh"](mesh, chosen["_matrix"]),
                             name, accurate=True)
    chosen["support_area_mm2"] = real["overhang_area_mm2"]
    if real["overhang_area_mm2"] <= IGNORE_OVERHANG_MM2:
        why = lead + " It needs no support."
    else:
        why = lead + (" It needs %.0f mm2 of support."
                      % real["overhang_area_mm2"])

    for r in rows:
        r["chosen"] = r is chosen
    return {"part": name, "load_bearing": load_bearing,
            "candidates": [{k: v for k, v in r.items() if k != "_matrix"}
                           for r in rows],
            "chosen": {k: v for k, v in chosen.items() if k != "_matrix"},
            "matrix": chosen["_matrix"], "reason": why}


def orient(path, mode="auto", axis=None, degrees=0.0, name=None):
    """
    Return the mesh the right way up, plus a line saying why.
    modes: keep | auto (04 section 3) | rotate (axis + degrees)
    """
    mesh = bm["load_mesh"](path) if isinstance(path, str) else path
    name = name or mesh.get("name", "")
    if mode == "keep":
        placed, _ = bm["drop_to_bed"](mesh)
        return {"mesh": placed, "reason": "Kept the orientation from Blender.",
                "mode": "keep"}
    if mode == "rotate":
        placed = bm["transform_mesh"](mesh, bm["rotation_matrix"](axis, degrees))
        placed, _ = bm["drop_to_bed"](placed)
        return {"mesh": placed,
                "reason": "Rotated %g degrees about %s as asked." % (degrees, axis),
                "mode": "rotate"}
    result = compare_orientations(mesh, name=name)
    placed = bm["transform_mesh"](mesh, result["matrix"])
    placed, _ = bm["drop_to_bed"](placed)
    return {"mesh": placed, "reason": result["reason"], "mode": "auto",
            "comparison": result}


# ── packing the plate (04 section 4) ─────────────────────────────────

def _hits_excluded(x0, y0, x1, y1, exclude, margin):
    for ex in exclude:
        if (x0 - margin < ex[2] and x1 + margin > ex[0] and
                y0 - margin < ex[3] and y1 + margin > ex[1]):
            return ex
    return None


def arrange_plate(sizes, spacing_mm=DEFAULT_SPACING_MM, bed=None, allow_rotate=True,
                  exclude=None, margin=BRIM_MARGIN_MM, clearances=None):
    """
    Pack footprints onto one plate. `sizes` is a list of (width, depth) in mm,
    in the order they should be placed. Returns positions (plate coordinates,
    centre of each item) and whatever didn't fit.

    clearances: per item, how far its brim/raft reaches past the outline
    (part_clearance). When given, each part is packed as its outline plus
    that reach, parts are kept MIN_GAP_MM apart on top (or spacing_mm, if
    larger), and the no-print corner is checked against the reach itself.

    A shelf packer, biggest first: good enough for the parts this project
    prints, and it reports honestly what is left over rather than overlapping.
    """
    bed = bed or (BUILD_VOLUME_MM[0], BUILD_VOLUME_MM[1])
    exclude = BED_EXCLUDE_AREAS if exclude is None else exclude
    usable_w = bed[0] - 2 * PLATE_MARGIN_MM
    usable_d = bed[1] - 2 * PLATE_MARGIN_MM

    if clearances is not None:
        # Pack the brim/raft footprint, not the bare outline.
        sizes = [(w + 2 * c, d + 2 * c) for (w, d), c in zip(sizes, clearances)]
        spacing_mm = max(MIN_GAP_MM, spacing_mm if spacing_mm is not None else 0)
        margin = 0.0                       # the reach is already inside the box
    items = []
    for i, (w, d) in enumerate(sizes):
        items.append({"index": i, "w": float(w), "d": float(d)})
    items.sort(key=lambda it: -max(it["w"], it["d"]))

    placed, leftover = {}, []
    shelf_y = PLATE_MARGIN_MM
    shelf_h = 0.0
    cursor_x = PLATE_MARGIN_MM
    for it in items:
        w, d, rotated = it["w"], it["d"], False
        if allow_rotate and w > d and w > usable_w - (cursor_x - PLATE_MARGIN_MM):
            w, d, rotated = d, w, True
        if w > usable_w or d > usable_d:
            leftover.append({"index": it["index"], "reason":
                             "%.0f x %.0f mm is bigger than the plate" % (it["w"], it["d"])})
            continue
        if cursor_x + w > PLATE_MARGIN_MM + usable_w:      # next shelf
            shelf_y += shelf_h + spacing_mm
            shelf_h = 0.0
            cursor_x = PLATE_MARGIN_MM
        # Step past the no-print corner rather than landing in it.
        ex = _hits_excluded(cursor_x, shelf_y, cursor_x + w, shelf_y + d,
                            exclude, margin)
        if ex:
            cursor_x = ex[2] + margin
            if cursor_x + w > PLATE_MARGIN_MM + usable_w:
                shelf_y += shelf_h + spacing_mm
                shelf_h = 0.0
                cursor_x = PLATE_MARGIN_MM
        if shelf_y + d > PLATE_MARGIN_MM + usable_d:
            leftover.append({"index": it["index"], "reason": "no room left on the plate"})
            continue
        placed[it["index"]] = {"x": cursor_x + w / 2.0, "y": shelf_y + d / 2.0,
                               "rotated": rotated, "w": w, "d": d}
        cursor_x += w + spacing_mm
        shelf_h = max(shelf_h, d)

    used_h = shelf_y + shelf_h - PLATE_MARGIN_MM

    # The shelves fill from the front-left corner. Move the whole group so it
    # sits in the middle of the plate, where the bed is flattest and the parts
    # are furthest from the edge — the way Bambu Studio's Arrange leaves it.
    if placed:
        x0 = min(p["x"] - p["w"] / 2.0 for p in placed.values())
        x1 = max(p["x"] + p["w"] / 2.0 for p in placed.values())
        y0 = min(p["y"] - p["d"] / 2.0 for p in placed.values())
        y1 = max(p["y"] + p["d"] / 2.0 for p in placed.values())
        dx = bed[0] / 2.0 - (x0 + x1) / 2.0
        dy = bed[1] / 2.0 - (y0 + y1) / 2.0
        # Only centre if that doesn't carry something into the no-print
        # corner; a full plate stays where the packer put it.
        clash = any(_hits_excluded(p["x"] + dx - p["w"] / 2.0,
                                   p["y"] + dy - p["d"] / 2.0,
                                   p["x"] + dx + p["w"] / 2.0,
                                   p["y"] + dy + p["d"] / 2.0, exclude, margin)
                    for p in placed.values())
        if not clash:
            for p in placed.values():
                p["x"] += dx
                p["y"] += dy

    return {
        "positions": [placed.get(i) for i in range(len(sizes))],
        "leftover": leftover,
        "fits": not leftover,
        "spacing_mm": spacing_mm,
        "bed_used_mm": [usable_w, max(0.0, used_h)],
    }


def plan_plates(sizes, spacing_mm=DEFAULT_SPACING_MM):
    """Split a job across as few plates as it takes."""
    remaining = list(range(len(sizes)))
    plates = []
    while remaining:
        subset = [sizes[i] for i in remaining]
        result = arrange_plate(subset, spacing_mm)
        on_this = [remaining[j] for j, pos in enumerate(result["positions"])
                   if pos is not None]
        if not on_this:
            break                                    # nothing fits at all
        plates.append({"items": on_this,
                       "positions": [p for p in result["positions"] if p]})
        remaining = [i for i in remaining if i not in on_this]
    return {"plates": plates, "plate_count": len(plates),
            "unplaceable": remaining}


# ── reading a project's specifications.md ────────────────────────────

def _spec_path(folder):
    return os.path.join(bp["LIBRARY"], folder, "references", "specifications.md")


def _table_rows(text, heading):
    """Rows of the markdown table under a heading, as lists of cells."""
    lines = text.splitlines()
    out, inside, in_table = [], False, False
    for line in lines:
        if line.startswith("## "):
            inside = heading.lower() in line.lower()
            in_table = False
            continue
        if not inside:
            continue
        if line.strip().startswith("|"):
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if all(set(c) <= set("-: ") for c in cells):
                in_table = True
                continue
            if in_table and any(cells):
                out.append(cells)
        elif in_table and not line.strip():
            continue
    return out


def read_quantities(folder):
    """
    The Quantities table: {part name: count}. Handles "1 each" across a
    comma-separated list of parts, plain numbers, and `n` (one unless told).
    """
    path = _spec_path(folder)
    if not os.path.isfile(path):
        return {}
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    out = {}
    for row in _table_rows(text, "Quantities"):
        if len(row) < 2:
            continue
        names = []
        for n in re.split(r"[,/]| and ", row[0]):
            if not n.strip():
                continue
            n = bp["clean"](n)
            if n.startswith("prod_"):      # the STLs drop it, so we do too
                n = n[len("prod_"):]
            names.append(n)
        qty_text = row[1].lower()
        m = re.search(r"\d+", qty_text)
        qty = int(m.group()) if m else 1        # `n` and blanks mean one
        for n in names:
            if n and not n.startswith("part_"):
                out[n] = qty
    return out


def read_material(folder, default=None):
    """The project's material, from 'Material(s) tested:'."""
    path = _spec_path(folder)
    if not os.path.isfile(path):
        return default or bpre["DEFAULT_MATERIAL"]
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            if "material(s) tested" in line.lower():
                value = line.split(":", 1)[-1].strip().strip("*").strip()
                if value and not value.startswith("("):
                    return bpre["resolve_material"](value.split("/")[0])
    return default or bpre["DEFAULT_MATERIAL"]


def newest_exports(folder, ext="stl"):
    """The newest version of each part: {part: path}, using the _<n> numbering."""
    root = os.path.join(bp["LIBRARY"], folder, ext)
    if not os.path.isdir(root):
        return {}
    best = {}
    for name in os.listdir(root):
        stem, e = os.path.splitext(name)
        if e.lower() != "." + ext:
            continue
        m = re.match(r"^(.*)_(\d+)$", stem)
        if not m:
            continue
        part, n = m.group(1), int(m.group(2))
        if part not in best or n > best[part][0]:
            best[part] = (n, os.path.join(root, name))
    return {p: path for p, (n, path) in sorted(best.items())}


# ── building the print 3MF (04 section 4) ────────────────────────────

def live_ams():
    """What's loaded in the AMS right now, over Bambu Cloud — or None when the
    printer can't be asked (not signed in, offline, no network)."""
    try:
        bc = runpy.run_path(os.path.join(_HERE, "bambu_cloud.py"))
        status = bc["printer_status"]()
        return status.get("ams") if status.get("state") != "offline" else None
    except Exception:
        return None


def build_print_3mf(project, parts=None, material=None, material_overrides=None,
                    settings=None, user_requested=None, spacing_mm=None,
                    orient_mode="auto", process=None, out_path=None,
                    arrange="auto", studio_exe="", ams="auto"):
    """
    The main Layer A tool: newest STL of each part, oriented, copied to its
    Quantity, packed on the plate, with filament and the approved settings
    applied, written as a real Bambu project 3MF in the project's 3mf/ folder.

    arrange: "studio" — Bambu Studio's own Arrange lays out the plate;
             "bonfire" — this file's packer, centred on the plate;
             "auto" (default) — Studio when it's installed and no custom
             spacing was asked for, otherwise ours. Studio's command line
             always uses its own default spacing, so a custom spacing_mm
             means ours.

    ams: "auto" (default) reads the loaded rolls from the printer and gives
         each filament the colour of the roll that will print it, so Studio's
         send dialog picks that AMS slot by itself; a parse_ams() list uses
         that instead; None skips it (the template's colours stay).

    Returns a report dict. Writes one file and nothing else.
    """
    custom_spacing = spacing_mm is not None
    spacing_mm = DEFAULT_SPACING_MM if spacing_mm is None else spacing_mm
    folder, hits = bp["resolve_project"](project)
    if folder is None:
        return {"ok": False, "error":
                ("Several projects match '%s': %s" % (project, ", ".join(hits)))
                if hits else "No project matches '%s'." % project,
                "candidates": hits}

    exports = newest_exports(folder)
    if not exports:
        return {"ok": False, "error":
                "No STLs in %s/stl — export from Blender first." % folder}
    if parts:
        wanted = [bp["clean"](p) for p in parts]
        missing = [p for p in wanted if p not in exports]
        if missing:
            return {"ok": False, "error":
                    "No STL for: %s. Available: %s"
                    % (", ".join(missing), ", ".join(sorted(exports)))}
        exports = {p: exports[p] for p in wanted}

    quantities = read_quantities(folder)
    project_material = material or read_material(folder)
    overrides = {bp["clean"](k): v for k, v in (material_overrides or {}).items()}

    # 1. Load, orient, and work out the per-part settings.
    entries, notes, warnings = [], [], []
    for part, stl in exports.items():
        mesh = bm["load_mesh"](stl)
        placed = orient(mesh, mode=orient_mode, name=part)
        m = placed["mesh"]
        notes.append("%s: %s" % (part, placed["reason"]))

        size = bm["bbox"](m)["size"]
        if any(size[i] > BUILD_VOLUME_MM[i] - 2 * PLATE_MARGIN_MM for i in range(3)):
            warnings.append("%s is %.0f x %.0f x %.0f mm and doesn't fit the "
                            "P1S — it needs splitting (04 section 5)."
                            % (part, size[0], size[1], size[2]))

        sup = suggest_supports(m)
        raft = suggest_raft(m)
        per_part = {}
        if sup["enable_support"]:
            per_part["enable_support"] = "1"
            per_part["support_type"] = sup["support_type"]
            per_part["support_on_build_plate_only"] = \
                "1" if sup["support_on_build_plate_only"] else "0"
            notes.append("%s: supports on — %s" % (part, sup["reason"]))
        if raft["raft"]:
            per_part["raft_layers"] = str(raft["raft_layers"])
            notes.append("%s: raft on (%d layers) — %s"
                         % (part, raft["raft_layers"], raft["reason"]))
        per_part = guard_settings(per_part)
        if settings:
            per_part.update(guard_settings(settings, user_requested))

        raw_mat = overrides.get(part, project_material)
        mat = bpre["resolve_material"](raw_mat)
        entries.append({"part": part, "stl": stl, "mesh": m, "settings": per_part,
                        "material": mat, "material_name": raw_mat, "quantity": max(1, quantities.get(part, 1)),
                        "size": size, "supports": sup, "raft": raft})

    # 2. One AMS slot per distinct material, in first-seen order.
    materials, material_names = [], []
    for e in entries:
        if e["material"] not in materials:
            materials.append(e["material"])
            material_names.append(e["material_name"] or e["material"])
    if len(materials) > 4:
        return {"ok": False, "error":
                "%d different materials, but the AMS holds 4: %s"
                % (len(materials), ", ".join(materials))}
    for e in entries:
        e["settings"]["extruder"] = str(materials.index(e["material"]) + 1)

    # 3. Pack every copy onto the plate.
    sizes, owners, reach = [], [], []
    for e in entries:
        for _ in range(e["quantity"]):
            sizes.append((e["size"][0], e["size"][1]))
            owners.append(e)
            reach.append(part_clearance(raft=bool(e["raft"]["raft"])))
    any_raft = any(e["raft"]["raft"] for e in entries)
    packing = arrange_plate(sizes, spacing_mm,
                            clearances=None if custom_spacing else reach)

    items, leftover_parts = [], []
    by_part = {}
    for i, (e, pos) in enumerate(zip(owners, packing["positions"])):
        if pos is None:
            leftover_parts.append(e["part"])
            continue
        mesh = e["mesh"]
        if pos["rotated"]:
            mesh = bm["transform_mesh"](mesh, bm["rotation_matrix"]("z", 90))
            mesh, _ = bm["drop_to_bed"](mesh)
        entry = by_part.get(e["part"])
        if entry is None:
            entry = {"mesh": mesh, "name": e["part"],
                     "source_file": os.path.basename(e["stl"]),
                     "settings": e["settings"], "instances": []}
            by_part[e["part"]] = entry
            items.append(entry)
        entry["instances"].append((pos["x"], pos["y"], 0.0))

    if not items:
        return {"ok": False, "error": "Nothing fits on the plate.",
                "leftover": leftover_parts}
    if leftover_parts:
        warnings.append(
            "These copies don't fit on one plate: %s. Say the word and I'll "
            "split them across plates (04 section 4)."
            % ", ".join(sorted(set(leftover_parts))))

    # 4. Settings for the whole project.
    proj_settings, source, application = bpre["project_settings"](
        ROOT, materials=materials,
        process=process or bpre["PROCESS_PRESET"])
    # Colour each filament like the roll that will print it, so Studio's send
    # dialog maps it to that AMS slot instead of guessing by colour.
    loaded = live_ams() if ams == "auto" else (ams or None)
    rolls = []
    if loaded:
        rolls = bpre["match_loaded_slots"](material_names, loaded)
        colours = list(proj_settings.get("filament_colour") or [])
        for i, roll in enumerate(rolls):
            if roll and roll.get("colour") and i < len(colours):
                colours[i] = roll["colour"]
                notes.append("filament %d (%s): coloured %s to match AMS slot %s"
                             % (i + 1, material_names[i], roll["colour"], roll["slot"]))
            elif i < len(colours):
                warnings.append("No %s roll is loaded in the AMS — load one, or "
                                "pick the slot by hand in Studio's send dialog."
                                % material_names[i])
        proj_settings["filament_colour"] = colours
    elif ams == "auto":
        notes.append("Couldn't read the AMS, so filament colours are the "
                     "template's; pick the slot in Studio's send dialog.")
    if source == "minimal":
        warnings.append(
            "No tools/bambu_template.3mf, so the presets were built from "
            "scratch. Studio will still select the right P1S presets, but save "
            "a project from Bambu Studio to that path and rebuild for an exact "
            "match on every other setting.")

    # Named like the STLs and never overwritten: 3mf/<project>_<n>.3mf
    friend, core = bp["_core_project"](folder)
    stem = "_".join(x for x in (friend, core) if x) or folder
    out = out_path or bp["next_export_path"](
        os.path.join(bp["LIBRARY"], folder), stem, "3mf")
    # 5. Lay out the plate. Our packer has already placed everything, centred,
    # so there is always a usable file; Studio's Arrange then improves on it.
    # Studio's command-line Arrange spaces parts by brim width only (it
    # hard-codes min_obj_distance to 0) and knows nothing of a raft's spread,
    # so two rafted parts end up with overlapping first layers and the slice
    # fails with "gcode path conflicts". Seen on this project's screw and nut.
    use_studio = arrange == "studio" or (
        arrange == "auto" and not custom_spacing and not any_raft
        and bool(bsl["find_studio"](studio_exe)))
    if arrange == "studio" and any_raft:
        warnings.append("Bambu Studio's command-line Arrange doesn't allow for "
                        "a raft's spread, so rafted parts may be packed too "
                        "close and fail to slice with a toolpath conflict.")
    if arrange == "studio" and custom_spacing:
        warnings.append("Bambu Studio's command-line Arrange always uses its "
                        "own spacing, so the %g mm asked for is ignored."
                        % spacing_mm)
    arranged_by = "bonfire"
    if use_studio:
        import tempfile
        scratch = os.path.join(tempfile.mkdtemp(prefix="bonfire_arrange_"),
                               os.path.basename(out))
        b3["write_project"](scratch, items, proj_settings, title=folder,
                            application=application)
        result = bsl["studio_arrange"](scratch, out_path=out,
                                       studio_exe=studio_exe)
        if result.get("ok"):
            arranged_by = "studio"
            lost = result.get("settings_lost")
            if lost:
                warnings.append(
                    "Bambu Studio's Arrange dropped per-part settings: %s. "
                    "Check them in Studio before slicing." % ", ".join(lost))
        else:
            warnings.append("Bambu Studio's Arrange didn't work (%s), so the "
                            "plate uses this project's own layout, centred."
                            % result.get("error", "unknown problem"))
            os.replace(scratch, out)
    else:
        b3["write_project"](out, items, proj_settings, title=folder,
                            application=application)

    return {
        "ok": True,
        "project": folder,
        "file": out,
        "preset_source": source,
        "machine_preset": bpre["MACHINE_PRESET"],
        "process_preset": process or bpre["PROCESS_PRESET"],
        "ams_slots": {str(i + 1): preset for i, preset in
                      enumerate(proj_settings.get("filament_settings_id", []))},
        "loaded_rolls": {str(i + 1): (r and {"ams_slot": r["slot"],
                                            "colour": r["colour"],
                                            "filament_id": r.get("filament_id")})
                         for i, r in enumerate(rolls)},
        "parts": [{"part": it["name"], "copies": len(it["instances"]),
                   "material": next(x["material"] for x in entries
                                    if x["part"] == it["name"]),
                   "ams_slot": it["settings"].get("extruder"),
                   "settings_changed": {k: v for k, v in it["settings"].items()
                                        if k != "extruder"}}
                  for it in items],
        "plate": {"arranged_by": arranged_by,
                  "spacing_mm": None if arranged_by == "studio" else spacing_mm,
                  "fits": not leftover_parts,
                  "leftover": sorted(set(leftover_parts))},
        "notes": notes,
        "warnings": warnings,
    }


def prepare_print(project, **kwargs):
    """
    "Get it ready to print", in one call (04 section 4): build the 3MF, then
    reserve the project's hardware and refresh the project index.
    """
    report = build_print_3mf(project, **kwargs)
    if not report.get("ok"):
        return report
    folder = report["project"]

    spec = _spec_path(folder)
    if os.path.isfile(spec):
        try:
            inv = runpy.run_path(os.path.join(_HERE, "inventory.py"))
            report["hardware"] = inv["commit"](folder)
        except Exception as exc:                 # never lose the 3MF over this
            report["hardware_error"] = (
                "The 3MF is built, but committing the hardware failed: %s" % exc)
    else:
        report["hardware"] = "No specifications.md, so no hardware to reserve."

    try:
        bp["index_projects"]()
    except Exception as exc:
        report["index_error"] = str(exc)
    return report


# ── reports in words ─────────────────────────────────────────────────

def format_report(report):
    """The 04 section 4 report, as plain lines."""
    if not report.get("ok"):
        return "Couldn't do it: %s" % report.get("error", "unknown problem")
    lines = ["Built %s" % os.path.basename(report["file"]),
             "  %s / %s" % (report["machine_preset"], report["process_preset"])]
    plate = report.get("plate", {})
    if plate.get("arranged_by") == "studio":
        lines.append("  Plate laid out by Bambu Studio's Arrange")
    elif plate:
        lines.append("  Plate laid out here, centred, with room for each "
                     "part's brim and raft")
    rolls = report.get("loaded_rolls") or {}
    for slot, preset in sorted(report["ams_slots"].items()):
        roll = rolls.get(slot)
        where = (" ← AMS slot %s (%s)" % (roll["ams_slot"], roll["colour"])
                 if roll else "")
        lines.append("  filament %s: %s%s" % (slot, preset, where))
    lines.append("")
    for p in report["parts"]:
        changed = p["settings_changed"]
        extra = (", ".join("%s=%s" % kv for kv in sorted(changed.items()))
                 if changed else "Bambu defaults, nothing changed")
        lines.append("  %s x%d  (%s, filament %s) — %s"
                     % (p["part"], p["copies"], p["material"], p["ams_slot"], extra))
    if report.get("notes"):
        lines.append("")
        lines += ["  " + n for n in report["notes"]]
    hw = report.get("hardware")
    if hw:
        lines += ["", str(hw)]
    if report.get("warnings"):
        lines.append("")
        lines += ["  ! " + w for w in report["warnings"]]
    if report.get("preset_source") == "template":
        lines.append("")
        lines.append("  Presets came from tools/bambu_template.3mf.")
    return "\n".join(lines)
