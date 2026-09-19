"""
Bonfire mesh helpers for the Bambu tools: read STL/3MF geometry and answer the
geometric questions 04_bambu_basics.md asks (does it fit, does it need
supports, does it need a raft, which way up should it go).

Pure standard library so it runs inside Blender, in a plain Python 3, or in a
cloud workspace with nothing installed.

    import os, runpy
    bm = runpy.run_path(os.path.join(BONFIRE, "tools", "bambu_mesh.py"))
    m  = bm["load_mesh"](r"...\\stl\\bracket_3.stl")
    bm["mesh_report"](m)

A mesh is a dict: {"verts": [(x,y,z), ...], "tris": [(a,b,c), ...], "name": str}
All units are millimetres. Nothing here writes files.
"""
import math
import os
import struct
import zipfile
import xml.etree.ElementTree as ET

# Bambu's own default: support is generated where the surface slope from the
# bed is below this angle. A vertical wall is 90 degrees, a ceiling is 0.
DEFAULT_SUPPORT_THRESHOLD_DEG = 30.0

# How close to the lowest point a triangle has to sit to count as touching bed.
CONTACT_TOLERANCE_MM = 0.25


# ── reading ──────────────────────────────────────────────────────────

def load_stl(path):
    """Read a binary or ASCII STL into a mesh dict, welding duplicate vertices."""
    with open(path, "rb") as fh:
        head = fh.read(5)
        fh.seek(0)
        raw = fh.read()
    is_ascii = head[:5].lower() == b"solid"
    if is_ascii:
        # A binary STL may still start with "solid"; check the declared count.
        if len(raw) >= 84:
            n = struct.unpack("<I", raw[80:84])[0]
            if len(raw) == 84 + n * 50:
                is_ascii = False
    tris_xyz = _read_ascii_stl(raw) if is_ascii else _read_binary_stl(raw)
    return _weld(tris_xyz, name=os.path.splitext(os.path.basename(path))[0])


def _read_binary_stl(raw):
    n = struct.unpack("<I", raw[80:84])[0]
    out = []
    off = 84
    for _ in range(n):
        vals = struct.unpack("<12fH", raw[off:off + 50])
        out.append((vals[3:6], vals[6:9], vals[9:12]))
        off += 50
    return out


def _read_ascii_stl(raw):
    out, cur = [], []
    for line in raw.decode("utf-8", "replace").splitlines():
        parts = line.split()
        if len(parts) == 4 and parts[0] == "vertex":
            cur.append((float(parts[1]), float(parts[2]), float(parts[3])))
            if len(cur) == 3:
                out.append(tuple(cur))
                cur = []
    return out


def _weld(tris_xyz, name="mesh", places=6):
    """Merge vertices that land on the same point, so edges can be paired."""
    index, verts, tris = {}, [], []
    for tri in tris_xyz:
        idx = []
        for v in tri:
            key = (round(v[0], places), round(v[1], places), round(v[2], places))
            i = index.get(key)
            if i is None:
                i = len(verts)
                index[key] = i
                verts.append((float(v[0]), float(v[1]), float(v[2])))
            idx.append(i)
        if idx[0] != idx[1] and idx[1] != idx[2] and idx[0] != idx[2]:
            tris.append(tuple(idx))          # drop degenerate triangles
    return {"verts": verts, "tris": tris, "name": name}


def load_3mf(path):
    """Read the geometry out of any 3MF (Bambu's or a plain one). Instances are
    applied, so what comes back is what sits on the plate."""
    ns = "{http://schemas.microsoft.com/3dmanufacturing/core/2015/02}"
    with zipfile.ZipFile(path) as z:
        names = z.namelist()
        main = "3D/3dmodel.model"
        if main not in names:
            main = next((n for n in names if n.endswith("3dmodel.model")), None)
            if main is None:
                raise ValueError("no 3dmodel.model inside %s" % path)
        roots = {main: ET.fromstring(z.read(main))}
        for n in names:                       # split-model sub files
            if n.startswith("3D/Objects/") and n.endswith(".model"):
                roots[n] = ET.fromstring(z.read(n))

    objects = {}
    for part, root in roots.items():
        for obj in root.iter(ns + "object"):
            objects[(part, obj.get("id"))] = obj

    def collect(part, oid, mat, verts, tris):
        obj = objects.get((part, oid))
        if obj is None:
            for (p, i), o in objects.items():      # id may live in another part
                if i == oid:
                    obj, part = o, p
                    break
        if obj is None:
            return
        mesh = obj.find(ns + "mesh")
        if mesh is not None:
            base = len(verts)
            for v in mesh.find(ns + "vertices"):
                p = (float(v.get("x")), float(v.get("y")), float(v.get("z")))
                verts.append(_apply(mat, p))
            for t in mesh.find(ns + "triangles"):
                tris.append((base + int(t.get("v1")),
                             base + int(t.get("v2")),
                             base + int(t.get("v3"))))
        comps = obj.find(ns + "components")
        if comps is not None:
            for c in comps:
                sub = c.get("{http://schemas.microsoft.com/3dmanufacturing/"
                            "production/2015/06}path") or part
                collect(sub, c.get("objectid"),
                        _mul(mat, _parse_transform(c.get("transform"))),
                        verts, tris)

    verts, tris = [], []
    for root in roots.values():
        build = root.find(ns + "build")
        if build is None:
            continue
        for item in build:
            collect(main, item.get("objectid"),
                    _parse_transform(item.get("transform")), verts, tris)
    if not tris:                                  # no build section: take it all
        for (part, oid) in list(objects):
            collect(part, oid, _identity(), verts, tris)
    tris_xyz = [(verts[a], verts[b], verts[c]) for a, b, c in tris]
    return _weld(tris_xyz, name=os.path.splitext(os.path.basename(path))[0])


def load_mesh(path):
    """load_stl or load_3mf, by extension."""
    ext = os.path.splitext(path)[1].lower()
    if ext == ".stl":
        return load_stl(path)
    if ext == ".3mf":
        return load_3mf(path)
    raise ValueError("unsupported model file: %s" % path)


# ── small matrix helpers (4x4 as a flat row-major tuple of 16) ────────

def _identity():
    return (1., 0., 0., 0.,  0., 1., 0., 0.,  0., 0., 1., 0.,  0., 0., 0., 1.)


def _parse_transform(text):
    """3MF writes 12 floats column-major (m00 m10 m20 m01 ...)."""
    if not text:
        return _identity()
    n = [float(x) for x in text.split()]
    if len(n) != 12:
        return _identity()
    return (n[0], n[3], n[6], n[9],
            n[1], n[4], n[7], n[10],
            n[2], n[5], n[8], n[11],
            0., 0., 0., 1.)


def _mul(a, b):
    out = [0.] * 16
    for r in range(4):
        for c in range(4):
            out[r * 4 + c] = sum(a[r * 4 + k] * b[k * 4 + c] for k in range(4))
    return tuple(out)


def _apply(m, p):
    x, y, z = p
    return (m[0] * x + m[1] * y + m[2] * z + m[3],
            m[4] * x + m[5] * y + m[6] * z + m[7],
            m[8] * x + m[9] * y + m[10] * z + m[11])


def to_transform_string(m):
    """Back to the 3MF's 12-float column-major form."""
    return " ".join(_fmt(m[r * 4 + c]) for c in range(4) for r in range(3))


def to_matrix_string(m):
    """model_settings.config wants row-major 16 floats — a different convention
    from 3dmodel.model in the same file set."""
    return " ".join(_fmt(v) for v in m)


def _fmt(v):
    s = "%.6f" % v
    s = s.rstrip("0").rstrip(".")
    return s if s not in ("", "-0") else "0"


def rotation_matrix(axis, degrees):
    """Rotation about 'x', 'y' or 'z', as a 4x4 row-major tuple."""
    a = math.radians(degrees)
    c, s = math.cos(a), math.sin(a)
    if axis == "x":
        r = ((1, 0, 0), (0, c, -s), (0, s, c))
    elif axis == "y":
        r = ((c, 0, s), (0, 1, 0), (-s, 0, c))
    elif axis == "z":
        r = ((c, -s, 0), (s, c, 0), (0, 0, 1))
    else:
        raise ValueError("axis must be x, y or z")
    return (r[0][0], r[0][1], r[0][2], 0.,
            r[1][0], r[1][1], r[1][2], 0.,
            r[2][0], r[2][1], r[2][2], 0.,
            0., 0., 0., 1.)


def rotation_to(normal):
    """A rotation that turns `normal` into (0,0,-1), i.e. lays that face down."""
    n = _unit(normal)
    target = (0., 0., -1.)
    d = _dot(n, target)
    if d > 0.999999:
        return _identity()
    if d < -0.999999:
        return rotation_matrix("x", 180)
    v = _cross(n, target)
    s, c = _norm(v), d
    vx = ((0, -v[2], v[1]), (v[2], 0, -v[0]), (-v[1], v[0], 0))
    vx2 = [[sum(vx[i][k] * vx[k][j] for k in range(3)) for j in range(3)]
           for i in range(3)]
    k = (1 - c) / (s * s)
    r = [[(1. if i == j else 0.) + vx[i][j] + vx2[i][j] * k for j in range(3)]
         for i in range(3)]
    return (r[0][0], r[0][1], r[0][2], 0.,
            r[1][0], r[1][1], r[1][2], 0.,
            r[2][0], r[2][1], r[2][2], 0.,
            0., 0., 0., 1.)


def transform_mesh(mesh, m):
    return {"verts": [_apply(m, v) for v in mesh["verts"]],
            "tris": list(mesh["tris"]), "name": mesh["name"]}


def drop_to_bed(mesh):
    """Move the mesh so its lowest point is z=0 and its footprint is centred on
    the origin in x and y. Returns (mesh, translation applied)."""
    bb = bbox(mesh)
    dx = -(bb["min"][0] + bb["max"][0]) / 2.0
    dy = -(bb["min"][1] + bb["max"][1]) / 2.0
    dz = -bb["min"][2]
    t = (1., 0., 0., dx, 0., 1., 0., dy, 0., 0., 1., dz, 0., 0., 0., 1.)
    return transform_mesh(mesh, t), (dx, dy, dz)


# ── vector helpers ───────────────────────────────────────────────────

def _sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1],
            a[2] * b[0] - a[0] * b[2],
            a[0] * b[1] - a[1] * b[0])


def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _norm(a):
    return math.sqrt(_dot(a, a))


def _unit(a):
    n = _norm(a)
    return (a[0] / n, a[1] / n, a[2] / n) if n else (0., 0., 0.)


# ── measurements ─────────────────────────────────────────────────────

def bbox(mesh):
    vs = mesh["verts"]
    if not vs:
        return {"min": (0., 0., 0.), "max": (0., 0., 0.), "size": (0., 0., 0.)}
    lo = [min(v[i] for v in vs) for i in range(3)]
    hi = [max(v[i] for v in vs) for i in range(3)]
    return {"min": tuple(lo), "max": tuple(hi),
            "size": tuple(hi[i] - lo[i] for i in range(3))}


def triangle_normal(mesh, tri):
    a, b, c = (mesh["verts"][i] for i in tri)
    return _cross(_sub(b, a), _sub(c, a))       # length = 2 * area


def triangle_area(mesh, tri):
    return _norm(triangle_normal(mesh, tri)) / 2.0


def surface_area(mesh):
    return sum(triangle_area(mesh, t) for t in mesh["tris"])


def volume(mesh):
    """Signed volume by the divergence theorem; mm^3. Negative means the
    triangle winding is inverted."""
    v = mesh["verts"]
    total = 0.0
    for a, b, c in mesh["tris"]:
        total += _dot(v[a], _cross(v[b], v[c]))
    return total / 6.0


def edge_report(mesh):
    """Manifold check: every edge should be shared by exactly two triangles,
    once in each direction."""
    counts = {}
    for a, b, c in mesh["tris"]:
        for e in ((a, b), (b, c), (c, a)):
            key = (min(e), max(e))
            counts[key] = counts.get(key, 0) + 1
    naked = sum(1 for n in counts.values() if n == 1)
    excess = sum(1 for n in counts.values() if n > 2)
    return {"edges": len(counts), "naked_edges": naked, "overused_edges": excess,
            "closed": naked == 0 and excess == 0}


def components(mesh):
    """Number of loose pieces (triangles connected through shared vertices)."""
    parent = list(range(len(mesh["verts"])))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(i, j):
        ri, rj = find(i), find(j)
        if ri != rj:
            parent[ri] = rj

    used = set()
    for a, b, c in mesh["tris"]:
        union(a, b)
        union(b, c)
        used.update((a, b, c))
    return len({find(i) for i in used})


def mesh_report(mesh):
    """Everything inspect_model needs, in one pass."""
    bb = bbox(mesh)
    er = edge_report(mesh)
    vol = volume(mesh)
    return {
        "name": mesh["name"],
        "triangles": len(mesh["tris"]),
        "vertices": len(mesh["verts"]),
        "bbox_mm": {"x": bb["size"][0], "y": bb["size"][1], "z": bb["size"][2]},
        "bbox_min": bb["min"], "bbox_max": bb["max"],
        "volume_mm3": abs(vol),
        "inverted_winding": vol < 0,
        "surface_area_mm2": surface_area(mesh),
        "closed_solid": er["closed"],
        "naked_edges": er["naked_edges"],
        "overused_edges": er["overused_edges"],
        "loose_pieces": components(mesh),
    }


# ── overhangs, footprint, raft ───────────────────────────────────────

def slope_degrees(normal):
    """Surface slope from the bed, the way Bambu measures it: a vertical wall
    is 90, a flat ceiling is 0. Only meaningful for downward-facing faces."""
    n = _unit(normal)
    if n == (0., 0., 0.):
        return 90.0
    return math.degrees(math.acos(max(-1.0, min(1.0, -n[2]))))


def overhang_faces(mesh, threshold_deg=DEFAULT_SUPPORT_THRESHOLD_DEG,
                   floor_tolerance=CONTACT_TOLERANCE_MM):
    """Downward-facing triangles too shallow to print unsupported. Faces lying
    on the bed are excluded — they are supported by the plate."""
    v = mesh["verts"]
    zmin = min(p[2] for p in v) if v else 0.0
    out = []
    for i, tri in enumerate(mesh["tris"]):
        n = triangle_normal(mesh, tri)
        if n[2] >= 0:
            continue
        if slope_degrees(n) >= threshold_deg:
            continue
        pts = [v[k] for k in tri]
        if max(p[2] for p in pts) <= zmin + floor_tolerance:
            continue                               # sitting on the plate
        out.append(i)
    return out


def overhang_islands(mesh, face_indices):
    """Group overhanging triangles into connected patches, with the area and
    lowest point of each. 'Many small islands' is what tree supports are for."""
    tris = mesh["tris"]
    vert_to_face = {}
    for fi in face_indices:
        for vi in tris[fi]:
            vert_to_face.setdefault(vi, []).append(fi)
    seen, islands = set(), []
    for start in face_indices:
        if start in seen:
            continue
        stack, group = [start], []
        seen.add(start)
        while stack:
            fi = stack.pop()
            group.append(fi)
            for vi in tris[fi]:
                for nb in vert_to_face.get(vi, ()):
                    if nb not in seen:
                        seen.add(nb)
                        stack.append(nb)
        area = sum(triangle_area(mesh, tris[fi]) for fi in group)
        pts = [mesh["verts"][k] for fi in group for k in tris[fi]]
        islands.append({
            "faces": len(group),
            "area_mm2": area,
            "z_min": min(p[2] for p in pts),
            "centroid": (sum(p[0] for p in pts) / len(pts),
                         sum(p[1] for p in pts) / len(pts)),
            "span_mm": max(max(p[0] for p in pts) - min(p[0] for p in pts),
                           max(p[1] for p in pts) - min(p[1] for p in pts)),
        })
    islands.sort(key=lambda d: -d["area_mm2"])
    return islands


# A downward face with material this close underneath prints onto what is
# already there — a screw thread onto the turn below, a chamfer onto the wall.
# Only a face with a real drop under it needs supporting.
SELF_SUPPORTING_GAP_MM = 1.5
_GRID_CELL_MM = 4.0


def build_xy_grid(mesh, cell=_GRID_CELL_MM):
    """Bucket triangles by their footprint, so a downward ray only has to test
    the few triangles near it instead of the whole mesh."""
    v, grid = mesh["verts"], {}
    for i, tri in enumerate(mesh["tris"]):
        pts = [v[k] for k in tri]
        x0 = int(math.floor(min(p[0] for p in pts) / cell))
        x1 = int(math.floor(max(p[0] for p in pts) / cell))
        y0 = int(math.floor(min(p[1] for p in pts) / cell))
        y1 = int(math.floor(max(p[1] for p in pts) / cell))
        for gx in range(x0, x1 + 1):
            for gy in range(y0, y1 + 1):
                grid.setdefault((gx, gy), []).append(i)
    return {"cell": cell, "cells": grid}


def highest_below(mesh, xy, z, grid=None, skip=()):
    """The z of the nearest bit of the model directly under (xy, z), or None.
    The bed counts as being at z = 0."""
    grid = grid or build_xy_grid(mesh)
    cell = grid["cell"]
    key = (int(math.floor(xy[0] / cell)), int(math.floor(xy[1] / cell)))
    v, tris = mesh["verts"], mesh["tris"]
    best = None
    for i in grid["cells"].get(key, ()):
        if i in skip:
            continue
        a, b, c = (v[k] for k in tris[i])
        top = max(a[2], b[2], c[2])
        if top >= z - 1e-4:
            continue
        if not _point_in_triangle_xy(xy, a, b, c):
            continue
        hit = _z_on_triangle(xy, a, b, c)
        if hit is None or hit >= z - 1e-4:
            continue
        if best is None or hit > best:
            best = hit
    return best


def _z_on_triangle(p, a, b, c):
    """Height of the plane through a, b, c above p."""
    n = _cross(_sub(b, a), _sub(c, a))
    if abs(n[2]) < 1e-12:
        return None
    return a[2] - (n[0] * (p[0] - a[0]) + n[1] * (p[1] - a[1])) / n[2]


def unsupported_faces(mesh, face_indices, max_gap=SELF_SUPPORTING_GAP_MM,
                      grid=None):
    """
    Of the downward-facing triangles, the ones with a real drop underneath.

    Angle alone is not enough: the underside of a printed thread is shallow,
    but it lands on the turn below, so it needs no support. A shelf at the same
    angle with 30 mm of air under it does. This is what tells them apart.
    """
    grid = grid or build_xy_grid(mesh)
    skip = set(face_indices)
    v, tris = mesh["verts"], mesh["tris"]
    out = []
    for i in face_indices:
        pts = [v[k] for k in tris[i]]
        cx = sum(p[0] for p in pts) / 3.0
        cy = sum(p[1] for p in pts) / 3.0
        cz = min(p[2] for p in pts)
        below = highest_below(mesh, (cx, cy), cz, grid, skip)
        floor = 0.0 if below is None else below
        if cz - floor > max_gap:
            out.append(i)
    return out


def geometry_below(mesh, xy, z, skip_faces=()):
    """Is there any of the model directly under this point, below height z?
    Used to tell 'supports can stand on the plate' from 'they have to stand on
    the part itself'."""
    v, tris = mesh["verts"], mesh["tris"]
    skip = set(skip_faces)
    for i, tri in enumerate(tris):
        if i in skip:
            continue
        a, b, c = (v[k] for k in tri)
        if max(a[2], b[2], c[2]) >= z - 0.05:
            continue
        if _point_in_triangle_xy(xy, a, b, c):
            return True
    return False


def _point_in_triangle_xy(p, a, b, c):
    d1 = (p[0] - b[0]) * (a[1] - b[1]) - (a[0] - b[0]) * (p[1] - b[1])
    d2 = (p[0] - c[0]) * (b[1] - c[1]) - (b[0] - c[0]) * (p[1] - c[1])
    d3 = (p[0] - a[0]) * (c[1] - a[1]) - (c[0] - a[0]) * (p[1] - a[1])
    neg = (d1 < 0) or (d2 < 0) or (d3 < 0)
    pos = (d1 > 0) or (d2 > 0) or (d3 > 0)
    return not (neg and pos)


def footprint(mesh, tolerance=CONTACT_TOLERANCE_MM):
    """What actually touches the bed: contact area and the extent of it."""
    v = mesh["verts"]
    if not v:
        return {"area_mm2": 0.0, "x": 0.0, "y": 0.0, "min_dim_mm": 0.0,
                "pieces": 0}
    zmin = min(p[2] for p in v)
    area, xs, ys, pieces = 0.0, [], [], 0
    for tri in mesh["tris"]:
        pts = [v[k] for k in tri]
        if max(p[2] for p in pts) > zmin + tolerance:
            continue
        n = triangle_normal(mesh, tri)
        area += abs(n[2]) / 2.0                  # area projected onto the bed
        pieces += 1
        xs += [p[0] for p in pts]
        ys += [p[1] for p in pts]
    if not xs:
        return {"area_mm2": 0.0, "x": 0.0, "y": 0.0, "min_dim_mm": 0.0,
                "pieces": 0}
    dx, dy = max(xs) - min(xs), max(ys) - min(ys)
    return {"area_mm2": area, "x": dx, "y": dy, "min_dim_mm": min(dx, dy),
            "pieces": pieces}


def flat_face_candidates(mesh, limit=6, tolerance_deg=1.0):
    """Distinct face directions with the most area behind them — the faces
    worth considering as 'largest flat face on the bed'."""
    groups = []
    for tri in mesh["tris"]:
        n = triangle_normal(mesh, tri)
        a = _norm(n) / 2.0
        if a <= 0:
            continue
        u = _unit(n)
        for g in groups:
            if _dot(u, g["normal"]) > math.cos(math.radians(tolerance_deg)):
                g["area"] += a
                break
        else:
            groups.append({"normal": u, "area": a})
    groups.sort(key=lambda g: -g["area"])
    return groups[:limit]
