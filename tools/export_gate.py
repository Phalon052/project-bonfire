"""
Project Bonfire — the STL export gate. Every STL leaves Blender through here.

Run inside Blender (through the Blender MCP), like paths.py:

    import os, runpy
    BONFIRE = os.environ.get("BONFIRE_HOME") or os.path.expanduser(r"~\\Desktop\\Project Bonfire")
    eg = runpy.run_path(os.path.join(BONFIRE, "tools", "export_gate.py"))

    r = eg["export_part"]("prod_lid", "shelf bracket")        # check, then export if it passes
    print(r["report"])
    eg["check_part"]("prod_lid")                                # check only, writes nothing

What it does, in order:
  1. Takes the object as it would be printed: modifiers applied, in its world
     position (the same mesh the STL exporter would write).
  2. Runs 3D Print Toolbox's checks on it (the Blender extension
     `print3d_toolbox`, Blender 4.2+).
  3. BLOCKS the export — no file is written — when any of these fail:
       * Solid: non-manifold edges or edges with flipped neighbouring normals
         (the mesh isn't one closed, consistently-facing shell)
       * Intersections: faces passing through each other (booleans leave these;
         counting open edges doesn't see them)
       * Degenerate: zero-area faces or zero-length edges
       * Shells: more than one separate piece (01_blender_basics.md §3: one
         part = one closed solid, no loose pieces)
  4. Warns, without blocking, on thin walls (below `min_wall_mm`), overhangs
     past `overhang_deg`, and very sharp edges.
  5. Only then writes <project>/stl/<object>_<n>.stl (paths.next_export_path,
     never overwriting) and refreshes the project index.

The confirmation table (01_blender_basics.md §5) is a separate gate: it proves
the part is the *right* part; this proves it's a *printable* one. Both have to
pass. There is no switch to skip a blocking check — fix the mesh. The one
exception is `allow_shells` for a deliberate multi-piece object (e.g. a
print-in-place assembly), and only when the person has said so.

Cleanup (the Toolbox's "Make Manifold") moves geometry, so it is never run
from here; after any cleanup, measure again and redo the confirmation table.
"""
import math
import os
import runpy
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))

# Wall thickness for the 0.4 mm nozzle (04_bambu_basics.md §6, from public
# design guides): below 2 × nozzle (0.8 mm) a wall can't get two perimeters —
# Bambu's own 0.20 mm Standard lays 0.42 + 0.45 mm lines, 2 loops — so it
# prints as one weak line or not at all. 1.2 mm (3 lines) is the recommended
# minimum for anything that carries load.
MIN_WALL_MM = 0.8          # "too thin": under two perimeters
REC_WALL_MM = 1.2          # "thin": under the recommended three lines
OVERHANG_DEG = 45.0        # past this from vertical, a face needs support (04 §2)
SHARP_DEG = 160.0          # the Toolbox's default: edges folded tighter than this
ZERO_MM = 0.0001           # "zero" length for degenerate edges / faces

BLOCKING = ("Non-manifold Edges", "Bad Contiguous Edges", "Intersect Faces",
            "Zero Faces", "Zero Edges", "Shells")
EXPLAIN = {
    "Non-manifold Edges": "holes or edges shared by more than two faces — not one closed shell",
    "Bad Contiguous Edges": "neighbouring faces point opposite ways (flipped normals)",
    "Intersect Faces": "faces pass through each other (often left by a boolean)",
    "Zero Faces": "faces with no area",
    "Zero Edges": "edges with no length",
    "Shells": "separate pieces in one object",
    "Thin Faces": "walls thinner than %.1f mm (2 × the 0.4 nozzle) — they get "
                  "under two perimeters and print weak or not at all" % MIN_WALL_MM,
    "Below Recommended Wall": "walls thinner than the recommended %.1f mm (3 lines) — "
                              "fine for light features, weak for anything load-bearing"
                              % REC_WALL_MM,
    "Overhang Faces": "faces overhanging more than %g° (need support)" % OVERHANG_DEG,
    "Sharp Edges": "very sharp edges",
    "Non-flat Faces": "faces that aren't flat",
}


class ExportRefused(Exception):
    """The gate said no; the message says why."""


def _toolbox():
    """The installed 3D Print Toolbox's check classes, whichever repository it
    came from (bl_ext.<repo>.print3d_toolbox)."""
    for name, mod in list(sys.modules.items()):
        if name.endswith(".print3d_toolbox.operators.analyze"):
            return mod
    try:
        import bpy
        import addon_utils
        for mod in addon_utils.modules():
            if mod.__name__.endswith("print3d_toolbox"):
                addon_utils.enable(mod.__name__, default_set=True)
        for name, mod in list(sys.modules.items()):
            if name.endswith(".print3d_toolbox.operators.analyze"):
                return mod
    except Exception:
        pass
    raise ExportRefused(
        "3D Print Toolbox isn't installed or enabled in Blender. Install it from "
        "Edit → Preferences → Get Extensions (search \"3D Print Toolbox\"), or "
        "https://extensions.blender.org/add-ons/print3d-toolbox/. No STL is "
        "exported without its checks.")


def _mm_to_bu(scene, mm):
    """Blender units for a length in mm, whatever the scene's unit scale."""
    us = scene.unit_settings
    metres_per_bu = us.scale_length if us.system != "NONE" else 0.001
    return (mm / 1000.0) / metres_per_bu


def _printable_copy(obj):
    """A temporary object holding exactly what the STL would contain:
    modifiers applied, world transform kept."""
    import bpy
    deps = bpy.context.evaluated_depsgraph_get()
    mesh = bpy.data.meshes.new_from_object(obj.evaluated_get(deps),
                                           preserve_all_data_layers=False,
                                           depsgraph=deps)
    tmp = bpy.data.objects.new(".gate_" + obj.name, mesh)
    tmp.matrix_world = obj.matrix_world.copy()
    bpy.context.scene.collection.objects.link(tmp)
    return tmp


def _remove(tmp):
    import bpy
    mesh = tmp.data
    bpy.data.objects.remove(tmp, do_unlink=True)
    if mesh and mesh.users == 0:
        bpy.data.meshes.remove(mesh)


def _overhangs(obj, overhang_deg, bed_tol):
    """Faces overhanging past `overhang_deg` from vertical — the Toolbox's
    overhang check, minus the faces lying on the bed (a flat bottom points
    straight down but needs no support)."""
    import bmesh
    from mathutils import Vector
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bm.transform(obj.matrix_world)
    bm.normal_update()
    if not bm.verts:
        bm.free()
        return 0
    z_min = min(v.co.z for v in bm.verts)
    limit = math.radians(90.0 - overhang_deg)
    down = Vector((0, 0, -1))
    n = 0
    for f in bm.faces:
        if f.calc_area() <= 0 or f.normal.length == 0:
            continue
        if down.angle(f.normal) < limit and \
                max(v.co.z for v in f.verts) > z_min + bed_tol:
            n += 1
    bm.free()
    return n


def run_checks(obj, min_wall_mm=MIN_WALL_MM, overhang_deg=OVERHANG_DEG,
               sharp_deg=SHARP_DEG, rec_wall_mm=REC_WALL_MM):
    """The Toolbox's checks on one object → {name: count}. Settings are the
    project's (in mm), restored afterwards so the Toolbox panel is untouched."""
    import bpy
    an = _toolbox()
    scene = bpy.context.scene
    props = scene.print3d_toolbox
    saved = {k: getattr(props, k) for k in ("threshold_zero", "thickness_min",
                                            "angle_overhang", "angle_sharp")}
    try:
        props.threshold_zero = _mm_to_bu(scene, ZERO_MM)
        props.thickness_min = _mm_to_bu(scene, min_wall_mm)
        props.angle_overhang = math.radians(overhang_deg)
        props.angle_sharp = math.radians(sharp_deg)
        data = []
        for cls_name in ("MESH_OT_check_solid", "MESH_OT_check_intersections",
                         "MESH_OT_check_shells", "MESH_OT_check_degenerate",
                         "MESH_OT_check_thick", "MESH_OT_check_sharp"):
            cls = getattr(an, cls_name, None)
            if cls is not None:
                cls.main_check(obj, data)
        # Second thickness pass at the recommended minimum.
        thick = getattr(an, "MESH_OT_check_thick", None)
        if thick is not None and rec_wall_mm and rec_wall_mm > min_wall_mm:
            props.thickness_min = _mm_to_bu(scene, rec_wall_mm)
            extra = []
            thick.main_check(obj, extra)
            thin = set()
            for item in data:
                if item.name == "Thin Faces" and item.indices is not None:
                    thin |= set(item.indices)
            for item in extra:
                between = sorted(set(item.indices or ()) - thin)   # 0.8–1.2 mm only
                data.append(item._replace(name="Below Recommended Wall",
                                          value=str(len(between)), indices=between))
    finally:
        for k, v in saved.items():
            setattr(props, k, v)
    data_overhang = _overhangs(obj, overhang_deg, _mm_to_bu(scene, 0.05))
    out = {"Overhang Faces": data_overhang}
    for item in data:
        try:
            out[item.name] = int(item.value)
        except (TypeError, ValueError):
            out[item.name] = item.value         # e.g. "Skipping Overhang"
    return out


def judge(counts, allow_shells=1):
    """Split check results into blocking failures and warnings."""
    fails, warns = [], []
    for name, n in counts.items():
        if not isinstance(n, int):
            continue
        if name == "Shells":
            if n > allow_shells:
                fails.append((name, n))
            continue
        if n <= 0:
            continue
        (fails if name in BLOCKING else warns).append((name, n))
    return fails, warns


def _resolve_object(obj_or_name):
    import bpy
    obj = bpy.data.objects.get(obj_or_name) if isinstance(obj_or_name, str) else obj_or_name
    if obj is None:
        raise ExportRefused("No object named %r." % obj_or_name)
    if obj.type != "MESH":
        raise ExportRefused("%s is a %s, not a mesh." % (obj.name, obj.type.lower()))
    return obj


def check_part(obj_or_name, min_wall_mm=MIN_WALL_MM, overhang_deg=OVERHANG_DEG,
               allow_shells=1):
    """Check only — writes nothing. Returns {"ok", "blocking", "warnings",
    "counts", "report"}."""
    obj = _resolve_object(obj_or_name)
    tmp = _printable_copy(obj)
    try:
        counts = run_checks(tmp, min_wall_mm, overhang_deg)
    finally:
        _remove(tmp)
    fails, warns = judge(counts, allow_shells)
    return {"ok": not fails, "object": obj.name, "counts": counts,
            "blocking": [{"check": n, "count": c, "means": EXPLAIN.get(n, "")} for n, c in fails],
            "warnings": [{"check": n, "count": c, "means": EXPLAIN.get(n, "")} for n, c in warns],
            "report": format_report(obj.name, fails, warns, None)}


def format_report(name, fails, warns, path):
    lines = []
    if fails:
        lines.append("EXPORT BLOCKED — %s isn't printable yet:" % name)
        for n, c in fails:
            lines.append("  ✗ %s: %s — %s" % (n, c, EXPLAIN.get(n, "")))
    else:
        lines.append("%s passed the print checks%s." % (
            name, (" and was exported to %s" % path) if path else ""))
    for n, c in warns:
        lines.append("  ! %s: %s — %s" % (n, c, EXPLAIN.get(n, "")))
    if fails:
        lines.append("Fix the mesh and export again. To see the problem faces/edges: "
                     "3D Print Toolbox panel (N sidebar → 3D-Print) → run the check → "
                     "click the result in edit mode.")
    return "\n".join(lines)


def export_part(obj_or_name, project, min_wall_mm=MIN_WALL_MM,
                overhang_deg=OVERHANG_DEG, allow_shells=1):
    """
    Check, and export only if every blocking check passes. The STL goes to the
    project's stl/ folder under the next unused <object>_<n>.stl. Returns the
    check result plus "file"; raises ExportRefused (nothing written) on a
    failure, so a caller can't carry on as if it had been exported.
    """
    import bpy
    bp = runpy.run_path(os.path.join(_HERE, "paths.py"))
    folder, hits = bp["resolve_project"](project)
    if folder is None:
        raise ExportRefused("No single project matches %r%s." % (
            project, (": " + ", ".join(hits)) if hits else ""))
    root = os.path.join(bp["LIBRARY"], folder)
    obj = _resolve_object(obj_or_name)

    tmp = _printable_copy(obj)
    try:
        counts = run_checks(tmp, min_wall_mm, overhang_deg)
        fails, warns = judge(counts, allow_shells)
        if fails:
            raise ExportRefused(format_report(obj.name, fails, warns, None))
        path = bp["next_export_path"](root, obj.name, "stl")
        # Export exactly the mesh that was checked, alone.
        prev_sel = [o for o in bpy.context.selected_objects]
        prev_active = bpy.context.view_layer.objects.active
        for o in prev_sel:
            o.select_set(False)
        tmp.select_set(True)
        bpy.context.view_layer.objects.active = tmp
        try:
            bpy.ops.wm.stl_export(filepath=path, export_selected_objects=True,
                                  apply_modifiers=True, ascii_format=False)
        finally:
            tmp.select_set(False)
            for o in prev_sel:
                o.select_set(True)
            bpy.context.view_layer.objects.active = prev_active
    finally:
        _remove(tmp)
    if not os.path.isfile(path):
        raise ExportRefused("Blender didn't write %s." % path)
    try:
        bp["index_projects"]()
    except Exception:
        pass
    return {"ok": True, "object": obj.name, "file": path, "counts": counts,
            "warnings": [{"check": n, "count": c, "means": EXPLAIN.get(n, "")} for n, c in warns],
            "report": format_report(obj.name, [], warns, path)}
