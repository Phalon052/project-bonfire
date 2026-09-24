"""
Tests for tools/gear.py that run without Blender:  python tools/test_gear.py
The overlap tests need shapely (pip install shapely); they're skipped without it.
"""
import math
import os
import runpy
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
gr = runpy.run_path(os.path.join(HERE, "gear.py"))

failures = []


def check(name, cond, detail=""):
    print(("ok    " if cond else "FAIL  ") + name + (("  " + detail) if detail else ""))
    if not cond:
        failures.append(name)


def pitch_thickness(points, rp, teeth):
    """Tooth widths (arc at the pitch circle), measured from the outline itself."""
    cross = []
    n = len(points)
    for i in range(n):
        (x1, y1), (x2, y2) = points[i], points[(i + 1) % n]
        r1, r2 = math.hypot(x1, y1), math.hypot(x2, y2)
        if (r1 - rp) * (r2 - rp) < 0:
            t = (rp - r1) / (r2 - r1)
            cross.append((math.atan2(y1 + t * (y2 - y1), x1 + t * (x2 - x1)) % (2 * math.pi), r1 < rp))
    cross.sort()
    widths = []
    for i, (a, rising) in enumerate(cross):
        if rising:                                  # going outward: start of a tooth
            b = cross[(i + 1) % len(cross)][0]
            widths.append(((b - a) % (2 * math.pi)) * rp)
    return widths


# ── values from 03 ──
tol = gr["tolerance"]
check("03 press, Overture", abs(tol("press", "Overture PLA") - 0.05) < 1e-9)
check("03 slide, Overture", abs(tol("slide", "overture pla") - 0.10) < 1e-9)
check("03 rotate = slide", tol("rotate", "Overture PLA") == tol("slide", "Overture PLA"))
check("03 thread, Overture", abs(tol("thread", "Overture PLA") - 0.30) < 1e-9)
check("03 gear backlash, Overture", abs(tol("gear_backlash", "Overture PLA") - 0.20) < 1e-9)
for bad in (("gear_backlash", "PETG Basic"), ("slide", "Nylon"), ("loose", "Overture PLA")):
    try:
        tol(*bad)
        check("03 refuses %s / %s" % bad, False)
    except gr["ToleranceMissing"]:
        check("03 refuses %s / %s" % bad, True)

# ── dimensions ──
d = gr["gear_dims"](2, 20)
check("dims m2 z20", (d["pitch_d"], d["tip_d"], d["root_d"]) == (40, 44, 35), str(d))
check("centre distance", gr["centre_distance"](2, 20, 30) == 50.0)
check("mesh rotation even", abs(gr["mesh_rotation"](20) - math.pi / 20) < 1e-12)
check("mesh rotation odd", gr["mesh_rotation"](21) == 0.0)

# ── tooth thickness = pi m / 2 - backlash per gear, and even spacing ──
for m, z, bl in ((2, 20, 0.10), (1.5, 33, 0.10), (1, 60, 0.05), (2, 20, 0.0)):
    pts, info = gr["gear_outline"](m, z, bl)
    w = pitch_thickness(pts, m * z / 2, z)
    want = math.pi * m / 2 - bl
    check("tooth thickness m%s z%d bl%.2f" % (m, z, bl),
          len(w) == z and max(abs(x - want) for x in w) < 0.01,
          "%d teeth, %.4f..%.4f, want %.4f" % (len(w), min(w), max(w), want))

# ── the proven tolerance-test gear ──
pts, info = gr["gear_outline"](2, 20, 0.10)
check("proven gear: tip / root", abs(info["tip_r"] - 22) < 1e-9 and abs(info["root_r"] - 17.5) < 1e-9)
check("proven gear: no warnings", gr["warnings_for"](2, 20, info) == [], str(gr["warnings_for"](2, 20, info)))
check("warns under 17 teeth", any("teeth" in w for w in gr["warnings_for"](2, 12, gr["gear_outline"](2, 12, 0.1)[1])))
check("warns module under 1", any("Module" in w for w in gr["warnings_for"](0.8, 20, gr["gear_outline"](0.8, 20, 0.1)[1])))

try:
    from shapely.geometry import Polygon
    from shapely import affinity
except ImportError:
    Polygon = None
    print("skip  overlap tests (pip install shapely)")

if Polygon:
    # outlines are simple (no self-crossing) across the range, both sides of z = 42 (root vs base circle)
    for m in (1, 2):
        for z in (8, 12, 17, 20, 30, 41, 42, 43, 60, 100):
            p = Polygon(gr["gear_outline"](m, z, 0.1)[0])
            check("valid outline m%d z%d" % (m, z), p.is_valid and p.area > 0)

    def worst_overlap(m, za, zb, backlash_total, steps=24, spread=0.0):
        pa = Polygon(gr["gear_outline"](m, za, backlash_total / 2)[0])
        pb = Polygon(gr["gear_outline"](m, zb, backlash_total / 2)[0])
        cd = gr["centre_distance"](m, za, zb) + spread
        rot_b = math.degrees(gr["mesh_rotation"](zb))
        worst, gap = 0.0, 1e9
        for i in range(steps):
            t = 360.0 / za * i / steps
            a = affinity.rotate(pa, t, origin=(0, 0))
            b = affinity.translate(affinity.rotate(pb, rot_b - t * za / zb, origin=(0, 0)), cd, 0)
            worst = max(worst, a.intersection(b).area)
            gap = min(gap, a.distance(b))
        return worst, gap

    for za, zb in ((20, 20), (15, 30), (17, 41), (21, 33), (12, 50)):
        ov, gap = worst_overlap(2, za, zb, 0.20)
        check("pair m2 %d:%d, 0.20 backlash: no overlap" % (za, zb), ov < 1e-6, "overlap %.5f mm2, min gap %.3f" % (ov, gap))
    ov, gap = worst_overlap(2, 20, 20, 0.20)
    check("pair 20:20 has real play (gap > 0.05)", gap > 0.05, "min gap %.3f" % gap)
    ov, _ = worst_overlap(2, 20, 20, -0.20)
    check("sensitivity: negative backlash overlaps", ov > 0.01, "overlap %.4f mm2" % ov)

print()
print("%d failed" % len(failures) if failures else "all checks passed")
sys.exit(1 if failures else 0)
