"""
Bonfire involute gears: spur gears that mesh at the true centre distance, with the
backlash and the centre-hole fit taken from 03_materials_tolerances.md.

Why it exists: the Extra Mesh Objects add-on's teeth are not involute and jam at the
correct centre distance (plugins/extra_mesh_objects.md). This is the scripted
fallback that plugins/README.md -> *Fallback* asks for, proven on the tolerance
tests' gear pair (module 2, 20 teeth, Overture PLA: 0.20 backlash, perfect mesh).

Run inside Blender through the Blender MCP, like paths.py (the math also runs in
plain Python 3, without bpy):

    import os, runpy
    BONFIRE = os.environ.get("BONFIRE_HOME") or os.path.expanduser(r"~\\Desktop\\Project Bonfire")
    gr = runpy.run_path(os.path.join(BONFIRE, "tools", "gear.py"))

    gr["tolerance"]("gear_backlash", "Overture PLA")     # 0.2, read from 03 section 3
    gr["gear_dims"](2, 20)                               # pitch / base / tip / root diameters
    gr["centre_distance"](2, 20, 30)                     # 50.0

    # one gear, material values from 03: teeth thinned by half the backlash,
    # centre hole = axle + 2 x the sliding / rotating clearance
    g = gr["make_gear"]("prod_gear", module=2, teeth=20, thickness=8,
                        axle=12.0, material="Overture PLA")

    # a meshing pair, placed at the exact centre distance and rotated to mesh
    a, b = gr["make_pair"]("prod_gear_small", "prod_gear_large", module=2, teeth_a=15,
                           teeth_b=30, thickness=8, axle_a=8, axle_b=12,
                           material="Overture PLA")
    gr["check_mesh"](a, b)       # {"ok": True, "max_overlap_mm3": 0.0, ...}  no overlap through one tooth
    gr["measure_gear"](a)        # real dimensions, for the confirmation table (01 section 5)

Rules it applies (read them before changing anything):
- 03 section 1: clearances are applied by offsetting, never by scaling. The centre hole
  gets the clearance (hole = axle + 2 x per side); the axle or peg stays nominal.
- 03 section 3, *Gear backlash*: the value is the TOTAL play between two gears. Each gear's
  teeth are thinned at the pitch circle by HALF of it; the gears sit at the exact centre
  distance m x (z1 + z2) / 2. Never spread the centres to make play.
- Teeth are involute, 20 degree pressure angle, addendum 1 m, dedendum 1.25 m (standard).
- A blank cell in 03 means the material was never tested: tolerance() raises instead of
  guessing (03 section 4). Pass backlash_total= / hole= explicitly to override, and say so.
- Warnings, not errors: fewer than 17 teeth (undercut: the root is not cut back, so
  the teeth may jam near the root), module under 1 (not tested, 03), and a tip narrower
  than one nozzle line.

Objects are built as one closed solid each (no Boolean modifiers), named as given, and
linked to the "prod" collection unless told otherwise. Export them with
export_gate.py -> export_part() like any other part.
"""
import math
import os
import re

_HERE = os.path.dirname(os.path.abspath(__file__))
BONFIRE = os.path.dirname(_HERE)
TOLERANCES = os.path.join(BONFIRE, "03_materials_tolerances.md")

PRESSURE_ANGLE_DEG = 20.0
ADDENDUM = 1.0        # x module
DEDENDUM = 1.25       # x module
NOZZLE_MM = 0.4
MIN_TEETH_NO_UNDERCUT = 17


class ToleranceMissing(Exception):
    """03 has no value for this fit and material (never tested)."""


# ── Values from 03 ───────────────────────────────────────────

# Row labels in 03 section 3's main table, matched by how the row starts.
_FIT_ROWS = {
    "exact": "exact",
    "press": "press fit",
    "slide": "sliding / rotating fit",
    "rotate": "sliding / rotating fit",
    "thread": "thread",
    "gear_backlash": "gear backlash",
}


def _cell_text(cell):
    return re.sub(r"[*_`]", "", cell).strip()


def tolerance(fit, material, path=TOLERANCES):
    """
    A value from 03_materials_tolerances.md section 3 (the main clearance table).
    fit: exact | press | slide (= rotate) | thread | gear_backlash.
    material: a column header, e.g. "Overture PLA" (case-insensitive).
    Per-side clearance in mm, or the total backlash for gear_backlash.
    Raises ToleranceMissing for a blank cell (never tested) or an unknown fit/material.
    """
    key = fit.lower().strip()
    if key not in _FIT_ROWS:
        raise ToleranceMissing("Unknown fit %r; use one of %s." % (fit, ", ".join(sorted(_FIT_ROWS))))
    row_start = _FIT_ROWS[key]
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    start = text.find("## 3.")
    end = text.find("\n### ", start)
    if start < 0:
        raise ToleranceMissing("03 has no section 3.")
    block = text[start:end if end > 0 else None]
    header, rows = None, []
    for line in block.splitlines():
        if not line.startswith("|") or set(line.replace("|", "").strip()) <= set("-: "):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if header is None:
            header = [_cell_text(c).lower() for c in cells]
        else:
            rows.append(cells)
    if header is None:
        raise ToleranceMissing("03 section 3 has no table.")
    mat = material.lower().strip()
    if mat not in header:
        raise ToleranceMissing("Material %r isn't a column in 03 section 3 (columns: %s)."
                               % (material, ", ".join(header[2:])))
    col = header.index(mat)
    for cells in rows:
        if _cell_text(cells[0]).lower().startswith(row_start):
            value = _cell_text(cells[col]) if col < len(cells) else ""
            if not value:
                raise ToleranceMissing(
                    "03 section 3: '%s' is blank for %s (never tested). Settle it first "
                    "(03 section 4), or pass the value explicitly and say so in the report."
                    % (row_start, material))
            m = re.search(r"-?\d+(?:\.\d+)?", value)
            if not m:
                raise ToleranceMissing("03 section 3: can't read %r for %s." % (value, material))
            return float(m.group())
    raise ToleranceMissing("03 section 3 has no '%s' row." % row_start)


# ── Gear geometry (plain math) ───────────────────────────────

def gear_dims(module, teeth, pressure_angle=PRESSURE_ANGLE_DEG):
    """Standard spur gear diameters, mm."""
    pa = math.radians(pressure_angle)
    pitch = module * teeth
    return {
        "pitch_d": pitch,
        "base_d": pitch * math.cos(pa),
        "tip_d": pitch + 2 * ADDENDUM * module,
        "root_d": pitch - 2 * DEDENDUM * module,
        "circular_pitch": math.pi * module,
        "tooth_thickness_nominal": math.pi * module / 2,
    }


def centre_distance(module, teeth_a, teeth_b):
    """Exact centre distance for two meshing gears: m (z1 + z2) / 2."""
    return module * (teeth_a + teeth_b) / 2.0


def mesh_rotation(teeth_b):
    """
    Rotation (radians, about Z) for gear B placed on +X of gear A, so a tooth of A at
    angle 0 meets a gap of B. Both gears are built with a tooth centred on +X.
    """
    return math.pi / teeth_b if teeth_b % 2 == 0 else 0.0


def _inv(a):
    return math.tan(a) - a


def gear_outline(module, teeth, backlash_per_gear=0.0, pressure_angle=PRESSURE_ANGLE_DEG,
                 flank_points=24, tip_points=6, root_points=8):
    """
    Closed 2D outline of an involute spur gear, centred on the origin, counter-clockwise,
    first tooth centred on +X. backlash_per_gear: how much thinner each tooth is at the
    pitch circle (arc length, mm) -- half the total backlash from 03.
    Returns (points, info). info carries the numbers the warnings are based on.
    """
    if teeth < 6:
        raise ValueError("At least 6 teeth.")
    pa = math.radians(pressure_angle)
    rp = module * teeth / 2.0
    rb = rp * math.cos(pa)
    ra = rp + ADDENDUM * module
    rf = rp - DEDENDUM * module
    half = math.pi / (2 * teeth) - backlash_per_gear / (2 * rp)   # half-tooth angle at the pitch circle
    th0 = half + _inv(pa)                                         # ... at the base circle
    r0 = max(rb, rf)
    tip_half = th0 - _inv(math.acos(rb / ra))
    if tip_half <= 0:
        raise ValueError("Teeth come to a point before the tip circle (backlash too large for this module).")
    def flank_angle(r):
        return th0 - _inv(math.acos(min(1.0, rb / r)))

    foot = flank_angle(r0)          # half-angle where the flank meets the root (= th0 when rf < rb)
    if math.pi / teeth - foot <= 0:
        raise ValueError("No root gap left between teeth.")

    radii = [r0 + (ra - r0) * i / (flank_points - 1) for i in range(flank_points)]
    pts = []
    for k in range(teeth):
        c = 2 * math.pi * k / teeth
        right = [(r, c - flank_angle(r)) for r in radii]
        left = [(r, c + flank_angle(r)) for r in radii]
        a0, a1 = right[-1][1], left[-1][1]
        tip = [(ra, a0 + (a1 - a0) * i / (tip_points - 1)) for i in range(1, tip_points - 1)]
        start = [(rf, c - th0)] if rf < r0 else []
        stop = [(rf, c + th0)] if rf < r0 else []
        g0, g1 = c + foot, c + 2 * math.pi / teeth - foot
        root = [(rf, g0 + (g1 - g0) * i / (root_points - 1)) for i in range(1, root_points - 1)]
        pts += start + right + tip + left[::-1] + stop + root
    xy = [(r * math.cos(a), r * math.sin(a)) for r, a in pts]
    info = {
        "pitch_r": rp, "base_r": rb, "tip_r": ra, "root_r": rf,
        "tooth_thickness_at_pitch": 2 * half * rp,
        "tip_width": 2 * tip_half * ra,
        "backlash_per_gear": backlash_per_gear,
    }
    return xy, info


def warnings_for(module, teeth, info):
    out = []
    if teeth < MIN_TEETH_NO_UNDERCUT:
        out.append("%d teeth: under %d, the root isn't undercut (cut back), so the teeth may "
                   "jam near the root. Use %d+ teeth or check the mesh carefully."
                   % (teeth, MIN_TEETH_NO_UNDERCUT, MIN_TEETH_NO_UNDERCUT))
    if module < 1.0:
        out.append("Module %.2f: modules under ~1 weren't tested (03 section 3); flag it." % module)
    if info["tip_width"] < NOZZLE_MM:
        out.append("Tip width %.2f mm is under one nozzle line (%.1f): the tips will print "
                   "rounded or not at all." % (info["tip_width"], NOZZLE_MM))
    return out


def _resolve_values(material, backlash_total, axle, hole, bore_fit):
    notes = []
    if backlash_total is None:
        if material is None:
            raise ToleranceMissing("Give material= (values from 03) or backlash_total= explicitly.")
        backlash_total = tolerance("gear_backlash", material)
        notes.append("backlash %.2f total from 03 (%s)" % (backlash_total, material))
    else:
        notes.append("backlash %.2f total given explicitly" % backlash_total)
    if hole is None and axle is not None:
        if bore_fit == "exact":
            clearance = 0.0
        else:
            if material is None:
                raise ToleranceMissing("Give material= (values from 03) or hole= explicitly.")
            clearance = tolerance(bore_fit, material)
        hole = axle + 2 * clearance
        notes.append("hole %.2f = axle %.2f + 2 x %.2f (%s)" % (hole, axle, clearance, bore_fit))
    elif hole is not None:
        notes.append("hole %.2f given explicitly" % hole)
    return backlash_total, hole, notes


# ── Blender ──────────────────────────────────────────────────

def _collection(name):
    import bpy
    coll = bpy.data.collections.get(name)
    if coll is None:
        coll = bpy.data.collections.new(name)
        bpy.context.scene.collection.children.link(coll)
    return coll


def _build_mesh(name, outline, thickness, hole, segments):
    """One closed solid: the outline (with a round hole) extruded 0..thickness."""
    import bpy
    import bmesh
    bm = bmesh.new()
    outer = [bm.verts.new((x, y, 0.0)) for x, y in outline]
    edges = [bm.edges.new((outer[i], outer[(i + 1) % len(outer)])) for i in range(len(outer))]
    if hole:
        r = hole / 2.0
        inner = [bm.verts.new((r * math.cos(2 * math.pi * i / segments),
                               r * math.sin(2 * math.pi * i / segments), 0.0)) for i in range(segments)]
        edges += [bm.edges.new((inner[i], inner[(i + 1) % segments])) for i in range(segments)]
    faces = bmesh.ops.triangle_fill(bm, use_beauty=True, use_dissolve=False, edges=edges)["geom"]
    faces = [f for f in faces if isinstance(f, bmesh.types.BMFace)]
    # triangle_fill fills the hole too when it can't tell it's a hole; drop faces inside it
    if hole:
        r2 = (hole / 2.0) ** 2
        drop = [f for f in faces if (f.calc_center_median().x ** 2 + f.calc_center_median().y ** 2) < r2]
        bmesh.ops.delete(bm, geom=drop, context="FACES_ONLY")
        faces = [f for f in faces if f.is_valid]
    ext = bmesh.ops.extrude_face_region(bm, geom=faces)
    moved = [e for e in ext["geom"] if isinstance(e, bmesh.types.BMVert)]
    bmesh.ops.translate(bm, vec=(0.0, 0.0, thickness), verts=moved)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    open_edges = sum(1 for e in bm.edges if not e.is_manifold)
    me = bpy.data.meshes.new(name[5:] if name.startswith("prod_") else name)
    bm.to_mesh(me)
    bm.free()
    if open_edges:
        bpy.data.meshes.remove(me)
        raise RuntimeError("Gear mesh isn't closed (%d open edges)." % open_edges)
    return me


def make_gear(name, module, teeth, thickness, axle=None, material=None, backlash_total=None,
              hole=None, bore_fit="slide", pressure_angle=PRESSURE_ANGLE_DEG,
              location=(0.0, 0.0, 0.0), rotation=0.0, collection="prod", segments=128):
    """
    Build one involute spur gear in Blender, bottom face on z = location z.

    axle: nominal diameter of the peg or shaft it turns on; the hole gets the clearance
          for bore_fit from 03 (default "slide" = sliding / rotating). "exact" = no clearance.
    hole: exact hole diameter instead (skips 03). None and axle None = solid gear.
    material: 03 column for the backlash and the hole clearance, e.g. "Overture PLA".
    backlash_total: override 03's gear backlash (total play, mm). Each gear gets half.
    rotation: about Z, radians (see mesh_rotation()).

    The values used are stored on the object (custom properties) and returned in
    obj["gear_report"] as text, for the report.
    """
    import bpy
    backlash_total, hole, notes = _resolve_values(material, backlash_total, axle, hole, bore_fit)
    outline, info = gear_outline(module, teeth, backlash_total / 2.0, pressure_angle)
    if hole and hole / 2.0 >= info["root_r"] - 1.2:
        raise ValueError("Hole %.2f leaves under 1.2 mm of wall to the root circle (root %.2f)."
                         % (hole, 2 * info["root_r"]))
    me = _build_mesh(name, outline, thickness, hole, segments)
    obj = bpy.data.objects.new(name, me)
    _collection(collection).objects.link(obj)
    obj.location = location
    obj.rotation_euler = (0.0, 0.0, rotation)
    warns = warnings_for(module, teeth, info)
    props = {"module": module, "teeth": teeth, "thickness": thickness,
             "pressure_angle": pressure_angle, "backlash_total": backlash_total,
             "hole": hole or 0.0, "material": material or ""}
    for k, v in props.items():
        obj["gear_" + k] = v
    obj["gear_report"] = "; ".join(notes + warns)
    return obj


def make_pair(name_a, name_b, module, teeth_a, teeth_b, thickness, axle_a=None, axle_b=None,
              material=None, backlash_total=None, hole_a=None, hole_b=None, bore_fit="slide",
              origin=(0.0, 0.0, 0.0), collection="prod", **kw):
    """Two gears at the exact centre distance along +X, rotated so they mesh."""
    x0, y0, z0 = origin
    a = make_gear(name_a, module, teeth_a, thickness, axle=axle_a, material=material,
                  backlash_total=backlash_total, hole=hole_a, bore_fit=bore_fit,
                  location=(x0, y0, z0), collection=collection, **kw)
    b = make_gear(name_b, module, teeth_b, thickness, axle=axle_b, material=material,
                  backlash_total=backlash_total, hole=hole_b, bore_fit=bore_fit,
                  location=(x0 + centre_distance(module, teeth_a, teeth_b), y0, z0),
                  rotation=mesh_rotation(teeth_b), collection=collection, **kw)
    return a, b


def check_mesh(obj_a, obj_b, steps=7, tol_mm3=1e-4):
    """
    Turn A through one tooth pitch (and B the matching amount the other way) in `steps`
    positions and intersect them each time. ok = no overlap anywhere. Leaves the scene as
    it was. Uses temporary copies; nothing is modified.
    """
    import bpy
    import bmesh
    za, zb = int(obj_a["gear_teeth"]), int(obj_b["gear_teeth"])
    dg = bpy.context.evaluated_depsgraph_get()
    scene = bpy.context.scene
    tmp = []

    def copy(obj, nm):
        c = bpy.data.objects.new(nm, bpy.data.meshes.new_from_object(obj.evaluated_get(dg)))
        c.matrix_world = obj.matrix_world.copy()
        scene.collection.objects.link(c)
        tmp.append(c)
        return c

    vols = []
    try:
        base_a, base_b = obj_a.rotation_euler.z, obj_b.rotation_euler.z
        for i in range(steps):
            t = (2 * math.pi / za) * i / max(1, steps - 1)
            ca = copy(obj_a, "temp_gear_check_a")
            cb = copy(obj_b, "temp_gear_check_b")
            ca.rotation_euler.z = base_a + t
            cb.rotation_euler.z = base_b - t * za / zb
            mod = ca.modifiers.new("check", "BOOLEAN")
            mod.object, mod.operation, mod.solver = cb, "INTERSECT", "EXACT"
            bpy.context.view_layer.update()
            ev = ca.evaluated_get(bpy.context.evaluated_depsgraph_get())
            me = ev.to_mesh()
            bm = bmesh.new()
            bm.from_mesh(me)
            vols.append(abs(bm.calc_volume()))
            bm.free()
            ev.to_mesh_clear()
    finally:
        for c in tmp:
            me = c.data
            bpy.data.objects.remove(c)
            if me.users == 0:
                bpy.data.meshes.remove(me)
    worst = max(vols) if vols else 0.0
    return {"ok": worst <= tol_mm3, "max_overlap_mm3": round(worst, 4),
            "overlap_by_step_mm3": [round(v, 4) for v in vols], "steps": steps}


def measure_gear(obj):
    """
    Real dimensions of a gear object, measured from its mesh (not from its settings):
    tip / root / hole diameters, thickness, tooth count, tooth thickness at the pitch
    circle, and how even the tooth spacing is. For the confirmation table.
    """
    import bpy
    import bmesh
    dg = bpy.context.evaluated_depsgraph_get()
    ev = obj.evaluated_get(dg)
    me = ev.to_mesh()
    try:
        vs = [v.co.copy() for v in me.vertices]
        zmin = min(v.z for v in vs)
        zmax = max(v.z for v in vs)
        bottom = [v for v in vs if abs(v.z - zmin) < 1e-5]
        rs = [math.hypot(v.x, v.y) for v in bottom]
        rp = obj.get("gear_module", 0) * obj.get("gear_teeth", 0) / 2.0
        hole_r = obj.get("gear_hole", 0.0) / 2.0
        outer = [(math.hypot(v.x, v.y), math.atan2(v.y, v.x)) for v in bottom
                 if math.hypot(v.x, v.y) > hole_r + 0.5]
        # outline edges only: on the bottom face and shared with a side wall (not the
        # triangulation's inner edges), and not on the hole
        bm = bmesh.new()
        bm.from_mesh(me)
        crossings = []
        for e in bm.edges:
            a, b = e.verts[0].co, e.verts[1].co
            if abs(a.z - zmin) > 1e-5 or abs(b.z - zmin) > 1e-5:
                continue
            if not any(abs(f.normal.z) < 0.5 for f in e.link_faces):
                continue
            ra, rb = math.hypot(a.x, a.y), math.hypot(b.x, b.y)
            if min(ra, rb) <= hole_r + 0.5:
                continue
            if (ra - rp) * (rb - rp) < 0:
                t = (rp - ra) / (rb - ra)
                x, y = a.x + t * (b.x - a.x), a.y + t * (b.y - a.y)
                crossings.append(math.atan2(y, x) % (2 * math.pi))
        bm.free()
        crossings = sorted(set(round(c, 9) for c in crossings))
        widths = []
        for k in range(len(crossings)):
            c0, c1 = crossings[k], crossings[(k + 1) % len(crossings)]
            span = (c1 - c0) % (2 * math.pi)
            mid = (c0 + span / 2) % (2 * math.pi)
            inside = [r for r, a in outer if abs(((a - mid + math.pi) % (2 * math.pi)) - math.pi) < span / 2]
            if inside and max(inside) > rp:
                widths.append((mid, span * rp))
        mids = sorted(m for m, _ in widths)
        gaps = [((mids[(i + 1) % len(mids)] - mids[i]) % (2 * math.pi)) for i in range(len(mids))] if mids else []
        return {
            "tip_d": round(2 * max(rs), 3),
            "root_d": round(2 * min(r for r in rs if r > hole_r + 0.5), 3),
            "hole_d": round(2 * min(rs), 3) if hole_r else 0.0,
            "thickness": round(zmax - zmin, 3),
            "teeth": len(widths),
            "tooth_thickness_at_pitch": [round(min(w for _, w in widths), 3),
                                         round(max(w for _, w in widths), 3)] if widths else None,
            "spacing_deg": [round(math.degrees(min(gaps)), 3),
                            round(math.degrees(max(gaps)), 3)] if gaps else None,
        }
    finally:
        ev.to_mesh_clear()
