"""
Checks for the Bambu tools, using shapes whose right answer is known from
04_bambu_basics.md. Run it from anywhere:  python3 tools/test_bambu.py
"""
import os
import runpy
import struct
import sys
import base64
import json
import tempfile
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
bm = runpy.run_path(os.path.join(HERE, "bambu_mesh.py"))
b3 = runpy.run_path(os.path.join(HERE, "bambu_3mf.py"))
bb = runpy.run_path(os.path.join(HERE, "bambu.py"))
bs = runpy.run_path(os.path.join(HERE, "bambu_slice.py"))
bc = runpy.run_path(os.path.join(HERE, "bambu_cloud.py"))
bl = runpy.run_path(os.path.join(HERE, "bambu_lan.py"))
bpr = runpy.run_path(os.path.join(HERE, "bambu_print.py"))
bpre = runpy.run_path(os.path.join(HERE, "bambu_presets.py"))

FAILURES = []


def check(name, got, want):
    ok = got == want
    print("  %s %-46s got %r" % ("ok  " if ok else "FAIL", name, got))
    if not ok:
        FAILURES.append("%s: wanted %r, got %r" % (name, want, got))


def note(name, value):
    print("       %-46s %s" % (name, value))


# ── shape builders (boxes are enough to test the rules) ──────────────

def box(x0, y0, z0, x1, y1, z1):
    v = [(x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0),
         (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)]
    f = [(0, 2, 1), (0, 3, 2), (4, 5, 6), (4, 6, 7),
         (0, 1, 5), (0, 5, 4), (1, 2, 6), (1, 6, 5),
         (2, 3, 7), (2, 7, 6), (3, 0, 4), (3, 4, 7)]
    return [tuple(v[i] for i in tri) for tri in f]


def write_stl(path, tris):
    with open(path, "wb") as fh:
        fh.write(b"\0" * 80)
        fh.write(struct.pack("<I", len(tris)))
        for a, b, c in tris:
            fh.write(struct.pack("<3f", 0, 0, 0))
            for p in (a, b, c):
                fh.write(struct.pack("<3f", *p))
            fh.write(struct.pack("<H", 0))
    return path


SLICE_INFO_FIXTURE = """<?xml version="1.0" encoding="UTF-8"?>
<config>
  <header>
    <header_item key="X-BBL-Client-Type" value="slicer"/>
    <header_item key="X-BBL-Client-Version" value="01.09.07.52"/>
  </header>
  <plate>
    <metadata key="index" value="1"/>
    <metadata key="printer_model_id" value="C12"/>
    <metadata key="nozzle_diameters" value="0.4"/>
    <metadata key="timelapse_type" value="0"/>
    <metadata key="prediction" value="4823"/>
    <metadata key="weight" value="18.46"/>
    <metadata key="outside" value="true"/>
    <metadata key="support_used" value="true"/>
    <metadata key="label_object_enabled" value="true"/>
    <object identify_id="286" name="machine_screw.stl" skipped="false" />
    <filament id="1" tray_info_idx="GFA00" type="PLA" color="#00AE42" \
used_m="6.18" used_g="18.46" used_for_object="true" used_for_support="false"/>
    <filament id="3" tray_info_idx="GFG00" type="PETG" color="#0086D6" \
used_m="1.02" used_g="3.11" used_for_object="false" used_for_support="true"/>
    <warning msg="the_actual_nozzle_hrc_smaller_than_the_required_nozzle_hrc" \
level="1" error_code ="1000C001"  />
  </plate>
  <plate>
    <metadata key="index" value="2"/>
    <metadata key="prediction" value="600"/>
    <metadata key="weight" value=""/>
    <metadata key="outside" value="false"/>
    <metadata key="support_used" value="false"/>
  </plate>
</config>
"""


FAKE_STUDIO = r'''#!/usr/bin/env python3
"""Stands in for bambu-studio on the command line, behaving the way
BambuStudio.cpp does: the export name is joined onto --outputdir, result.json
is written there, and a failing run exits with the low byte of a negative code.
FAKE_MODE=fail | dropsettings changes what it does."""
import json, os, re, shutil, sys, zipfile
a = sys.argv[1:]
def opt(name):
    return a[a.index(name) + 1] if name in a else ""
outdir, export, src = opt("--outputdir"), opt("--export-3mf"), a[-1]
mode = os.environ.get("FAKE_MODE", "")
dest = outdir + "/" + export if outdir else export     # the real join
res = {"return_code": 0, "error_string": "Success.", "sliced_plates": []}
if mode == "fail":
    res = {"return_code": -21, "error_string": "Arrange failed."}
    json.dump(res, open(os.path.join(outdir, "result.json"), "w"))
    sys.exit(-21 if os.name == "nt" else 256 - 21)   # Windows keeps 32 bits
with zipfile.ZipFile(src) as zin, zipfile.ZipFile(dest, "w") as zout:
    for n in zin.namelist():
        data = zin.read(n)
        if mode == "dropsettings" and n == "Metadata/model_settings.config":
            data = re.sub(rb'\s*<metadata key="raft_layers" value="[^"]*"/>', b"", data)
        zout.writestr(n, data)
if "--slice" in a:
    res["sliced_plates"] = [{"id": 1, "warning_message":
        "It seems object hex_nut has floating regions. Please re-orient the "
        "object or enable support generation."}]
json.dump(res, open(os.path.join(outdir, "result.json"), "w"))
'''


def _fake_studio(tmp):
    """The stand-in, runnable the way the OS runs programs: a script with a
    shebang on Unix, a .cmd that hands it to this Python on Windows."""
    script = os.path.join(tmp, "bambu-studio.py" if os.name == "nt" else "bambu-studio")
    with open(script, "w") as fh:
        fh.write(FAKE_STUDIO)
    if os.name != "nt":
        os.chmod(script, 0o755)
        return script
    path = os.path.join(tmp, "bambu-studio.cmd")
    with open(path, "w") as fh:
        fh.write('@"%s" "%s" %%*\r\n' % (sys.executable, script))
    return path


def _write_sliced_fixture(path):
    """A 3MF shaped like one Bambu Studio just sliced. The odd bits are
    deliberate: `error_code ` really does carry a trailing space in the
    writer, `weight` really can be empty, and filament ids really are sparse."""
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("Metadata/slice_info.config", SLICE_INFO_FIXTURE)
        z.writestr("Metadata/plate_1.gcode", "; not real gcode\n")


def main():
    tmp = tempfile.mkdtemp(prefix="bambu_test_")

    print("\nsupports — a T with a wide flat overhang (04 s2: normal(auto))")
    tee = box(-3, -3, 0, 3, 3, 20) + box(-20, -12, 20, 20, 12, 24)
    p = write_stl(os.path.join(tmp, "tee.stl"), tee)
    s = bb["suggest_supports"](p)
    check("enable_support", s["enable_support"], True)
    check("support_type", s["support_type"], "normal(auto)")
    note("reason", s["reason"])

    print("\nsupports — a comb of thin pins (04 s2: tree(auto))")
    comb = box(-30, -3, 0, 30, 3, 3)
    for i in range(8):                      # thin arms sticking out sideways
        x = -28 + i * 7
        comb += box(x, 3, 12, x + 2, 9, 14)
        comb += box(x, 3, 0, x + 2, 5, 12)   # a post under each, not the whole arm
    p = write_stl(os.path.join(tmp, "comb.stl"), comb)
    s = bb["suggest_supports"](p)
    check("enable_support", s["enable_support"], True)
    check("support_type", s["support_type"], "tree(auto)")
    note("islands", "%d small, %d large" % (s["small_islands"], s["large_islands"]))
    note("reason", s["reason"])

    print("\nsupports — a plain block (no supports)")
    p = write_stl(os.path.join(tmp, "block.stl"), box(0, 0, 0, 20, 20, 10))
    s = bb["suggest_supports"](p)
    check("enable_support", s["enable_support"], False)

    print("\nsupports — build-plate-only: a cantilever with nothing underneath")
    cant = box(0, 0, 0, 6, 20, 30) + box(6, 0, 26, 40, 20, 30)
    p = write_stl(os.path.join(tmp, "cantilever.stl"), cant)
    s = bb["suggest_supports"](p)
    check("enable_support", s["enable_support"], True)
    check("build_plate_only", s["support_on_build_plate_only"], True)

    print("\nsupports — on-part: a shelf with the model under it")
    shelf = box(0, 0, 0, 30, 20, 40) + box(30, 0, 30, 60, 20, 34) \
        + box(30, 0, 0, 60, 20, 10)
    p = write_stl(os.path.join(tmp, "shelf.stl"), shelf)
    s = bb["suggest_supports"](p)
    check("build_plate_only", s["support_on_build_plate_only"], False)

    print("\nraft — 04 s2's own four examples")
    # a screw: head under 15 mm across, 35 mm tall  -> raft
    p = write_stl(os.path.join(tmp, "screw.stl"),
                  box(-6, -6, 0, 6, 6, 3) + box(-3, -3, 3, 3, 3, 38))
    r = bb["suggest_raft"](p)
    check("screw head 12 mm, 38 mm tall", r["raft"], True)
    check("raft layers", r["raft_layers"], 2)

    # a bearing: 15 mm across, less than 1.5x as tall -> no raft
    p = write_stl(os.path.join(tmp, "bearing.stl"), box(-7.5, -7.5, 0, 7.5, 7.5, 20))
    r = bb["suggest_raft"](p)
    check("bearing 15 mm wide, 20 mm tall", r["raft"], False)

    # feet under 10 mm square -> raft
    p = write_stl(os.path.join(tmp, "feet.stl"),
                  box(-4, -4, 0, 4, 4, 5) + box(-25, -25, 5, 25, 25, 12))
    r = bb["suggest_raft"](p)
    check("8 mm feet", r["raft"], True)

    # a base bigger than 30 x 30, 3x as tall -> no raft
    p = write_stl(os.path.join(tmp, "tower.stl"), box(-20, -20, 0, 20, 20, 120))
    r = bb["suggest_raft"](p)
    check("40 mm base, 120 mm tall", r["raft"], False)

    print("\nbuild volume")
    p = write_stl(os.path.join(tmp, "huge.stl"), box(0, 0, 0, 300, 50, 50))
    i = bb["inspect_model"](p)
    check("fits_build_volume", i["fits_build_volume"], False)
    note("warning", i.get("warning"))

    print("\nmesh quality")
    p = write_stl(os.path.join(tmp, "closed.stl"), box(0, 0, 0, 10, 10, 10))
    i = bb["inspect_model"](p)
    check("closed_solid", i["closed_solid"], True)
    check("volume_mm3", round(i["volume_mm3"]), 1000)
    check("loose_pieces", i["loose_pieces"], 1)
    p = write_stl(os.path.join(tmp, "two.stl"),
                  box(0, 0, 0, 5, 5, 5) + box(20, 0, 0, 25, 5, 5))
    check("loose_pieces (two boxes)", bb["inspect_model"](p)["loose_pieces"], 2)
    p = write_stl(os.path.join(tmp, "open.stl"), box(0, 0, 0, 10, 10, 10)[:-2])
    check("open mesh flagged", bb["inspect_model"](p)["closed_solid"], False)

    print("\nthe settings guard (04 s2)")
    check("approved change allowed",
          bb["guard_settings"]({"support_type": "tree(auto)"}),
          {"support_type": "tree(auto)"})
    for bad, label in ((("support_type", "organic"), "unapproved support type"),
                       (("sparse_infill_density", "40%"), "infill"),
                       (("nozzle_temperature", "230"), "temperature"),
                       (("outer_wall_speed", "300"), "speed"),
                       (("raft_layers", "5"), "raft layers other than 0 or 2"),
                       (("something_new", "1"), "unknown setting")):
        try:
            bb["guard_settings"]({bad[0]: bad[1]})
            check("refuses " + label, False, True)
        except bb["SettingRefused"]:
            check("refuses " + label, True, True)
    check("locked allowed when the user asks",
          bb["guard_settings"]({"sparse_infill_density": "40%"},
                               user_requested="print it at 40% infill"),
          {"sparse_infill_density": "40%"})

    print("\npacking the plate")
    a = bb["arrange_plate"]([(20, 20)] * 9, spacing_mm=6)
    check("9 small parts fit", a["fits"], True)
    check("all placed", sum(1 for p in a["positions"] if p), 9)
    xs = [(p["x"], p["y"]) for p in a["positions"]]
    check("no two in the same place", len(set(xs)), 9)
    inside = all(4 <= p["x"] <= 252 and 4 <= p["y"] <= 252 for p in a["positions"])
    check("all inside the bed", inside, True)
    big = bb["arrange_plate"]([(120, 120)] * 6, spacing_mm=6)
    check("six 120 mm parts don't all fit", big["fits"], False)
    pl = bb["plan_plates"]([(120, 120)] * 6, spacing_mm=6)
    check("they need more than one plate", pl["plate_count"] > 1, True)
    check("every part lands somewhere",
          sum(len(p["items"]) for p in pl["plates"]), 6)

    print("\noverlap check on a real pack")
    def overlaps(a, b):
        return (abs(a["x"] - b["x"]) * 2 < (a["w"] + b["w"]) - 0.01 and
                abs(a["y"] - b["y"]) * 2 < (a["d"] + b["d"]) - 0.01)
    mixed = bb["arrange_plate"]([(40, 25), (60, 60), (15, 90), (30, 30),
                                 (80, 20), (25, 25)], spacing_mm=6)
    placed = [p for p in mixed["positions"] if p]
    bad = [(i, j) for i in range(len(placed)) for j in range(i + 1, len(placed))
           if overlaps(placed[i], placed[j])]
    check("nothing overlaps", bad, [])

    print("\nwriting a Bambu project 3MF")
    mesh = bm["load_mesh"](write_stl(os.path.join(tmp, "part.stl"),
                                     box(-10, -10, 0, 10, 10, 8)))
    settings = bb["bpre"]["minimal_project_settings"](["PLA", "PETG"])
    out = os.path.join(tmp, "project.3mf")
    b3["write_project"](out, [{"mesh": mesh, "name": "part",
                               "instances": [(100, 100, 0), (140, 100, 0)],
                               "settings": {"extruder": "1",
                                            "enable_support": "1",
                                            "support_type": "tree(auto)"}}],
                        settings)
    d = b3["describe"](out)
    check("opens as a Bambu project", d["is_bambu_project"], True)
    check("application tag", d["application"].startswith("BambuStudio-"), True)
    check("printer_model", d["printer_model"], "Bambu Lab P1S")
    check("has _rels/.rels", d["has_rels"], True)
    check("has project_settings", d["has_project_settings"], True)
    check("has model_settings", d["has_model_settings"], True)

    print("\nround trip: read our own 3MF back")
    back = bm["load_mesh"](out)
    r = bm["mesh_report"](back)
    check("two copies came back", round(r["volume_mm3"]), 2 * 20 * 20 * 8)
    check("still a closed solid", r["closed_solid"], True)
    bbx = bm["bbox"](back)
    check("first copy centred at x=100",
          round((bbx["min"][0] + 10)), 100)
    s2 = b3["read_project_settings"](out)
    check("filament slots survive", len(s2["filament_colour"]), 2)
    check("filament presets survive", s2["filament_settings_id"],
          ["Bambu PLA Basic @BBL P1S 0.4 nozzle",
           "Bambu PETG HF @BBL P1S 0.4 nozzle"])

    print("\npreset naming")
    check("machine preset", bb["bpre"]["MACHINE_PRESET"], "Bambu Lab P1S 0.4 nozzle")
    check("process preset", bb["bpre"]["PROCESS_PRESET"], "0.20mm Standard @BBL X1C")
    check("Overture PLA maps to PLA",
          bb["bpre"]["resolve_material"]("Overture PLA"), "PLA")
    check("unknown material falls back", bb["bpre"]["resolve_material"]("kryptonite"),
          "PLA")

    print("\norientation")
    # A flat slab that was modelled standing on edge should be laid down.
    slab = box(0, 0, 0, 3, 60, 40)
    p = write_stl(os.path.join(tmp, "slab.stl"), slab)
    o = bb["compare_orientations"](p, name="slab")
    check("slab is laid flat", round(o["chosen"]["height_mm"]), 3)
    note("reason", o["reason"])
    o2 = bb["compare_orientations"](p, name="shelf_bracket")
    check("a load-bearing name keeps its orientation",
          o2["chosen"]["mode"], "keep")
    note("reason", o2["reason"])

    print("\nslicing — reading a sliced 3MF back")
    sliced = os.path.join(tmp, "thing_1.gcode.3mf")
    _write_sliced_fixture(sliced)
    r = bs["read_slice_info"](sliced)
    check("recognised as sliced", r["sliced"], True)
    check("slicer named", r["sliced_by"], "Bambu Studio")
    check("print time in words", r["plates"][0]["print_time"], "1h 20m")
    check("print seconds", r["plates"][0]["print_seconds"], 4823)
    check("filament grams", r["plates"][0]["filament_g"], 18.46)
    check("support flagged", r["plates"][0]["support_used"], True)
    check("outside-plate flagged", r["plates"][0]["outside_plate"], True)
    check("sparse filament slots read by id",
          [f["slot"] for f in r["plates"][0]["filaments"]], [1, 3])
    check("support filament marked",
          r["plates"][0]["filaments"][1]["for_support"], True)
    check("warning turned into words",
          r["plates"][0]["warnings"][0]["message"],
          "This filament is more abrasive than the nozzle is rated for.")
    check("two plates totalled", r["total_seconds"], 4823 + 600)
    check("empty weight survives", r["plates"][1]["filament_g"], None)
    check("the PLA bed warning is hidden by choice",
          "bed_temperature_too_high_than_filament" in bs["IGNORED_WARNINGS"], True)
    check("the PLA door-open warning is translated",
          "front door" in bs["SLICE_WARNINGS"]["bed_temperature_too_high_than_filament"], True)
    note("report", bs["format_slice_report"](
        dict(r, ok=True, file=sliced)).splitlines()[0])

    print("\nslicing — an unsliced file is not mistaken for a sliced one")
    r2 = bs["read_slice_info"](out)
    check("plain project not sliced", r2["sliced"], False)

    print("\nslicing — exit codes and naming")
    if os.name == "nt":      # Windows keeps the full code, so 152 really is 152
        check("152 stays 152 on Windows", bs["signed"](152), 152)
    else:                    # Unix keeps only the low byte
        check("152 means -104", bs["signed"](152), -104)
        check("232 means -24", bs["signed"](232), -24)
    check("0 stays 0", bs["signed"](0), 0)
    check("Windows 32-bit 4294966939 means -357", bs["signed"](4294966939), -357)
    check("a crash is named",
          "access violation" in bs["explain_code"](bs["signed"](3221225477), {}), True)
    check("an unknown code without result.json points at the log",
          "log" in bs["explain_code"](-357, {}), True)
    check("-104 explained",
          "outside the printable area" in bs["EXIT_CODES"][-104], True)
    name = bs["next_sliced_path"](os.path.join(tmp, "thing_2.3mf"))
    check("sliced name", os.path.basename(name), "thing_2_1.gcode.3mf")
    open(name, "w").close()
    check("never overwrites",
          os.path.basename(bs["next_sliced_path"](
              os.path.join(tmp, "thing_2.3mf"))), "thing_2_2.gcode.3mf")

    print("\nslicing — missing slicer is reported, not crashed on")
    # Pretend nothing is installed, even on a PC where Studio really is.
    g = bs["slice_file"].__globals__
    real_find = g["find_studio"]
    g["find_studio"] = lambda configured="": ""
    try:
        r3 = bs["slice_file"](out, studio_exe="/nowhere/bambu-studio")
    finally:
        g["find_studio"] = real_find
    check("says Bambu Studio is missing", r3["ok"], False)
    check("names what it needs", r3.get("needs"), "bambu-studio.exe")

    print("\nslicing — plate picture")
    pv = bs["plate_preview"](out, 1, os.path.join(tmp, "preview.png"))
    check("pulled the plate png out", pv["ok"], True)
    check("png is real", open(pv["file"], "rb").read(8), b"\x89PNG\r\n\x1a\n")
    check("missing plate reported",
          bs["plate_preview"](out, 7)["ok"], False)

    print("\nStudio's Arrange, through the command line (stand-in slicer)")
    studio = _fake_studio(tmp)
    src = os.path.join(tmp, "arrange_me.3mf")
    b3["write_project"](src, [{"mesh": mesh, "name": "hex_nut",
                               "instances": [(10, 10, 0)],
                               "settings": {"extruder": "1", "raft_layers": "2"}}],
                        settings)
    dest = os.path.join(tmp, "out", "arranged_1.3mf")
    os.makedirs(os.path.dirname(dest))
    a = bs["studio_arrange"](src, out_path=dest, studio_exe=studio)
    check("arrange ok", a["ok"], True)
    check("file landed at the absolute path asked for",
          os.path.isfile(dest), True)
    check("orientation left alone (--orient 0)", "--orient" in a["command"]
          and a["command"][a["command"].index("--orient") + 1], "0")
    check("export given as a bare name, not a path",
          a["command"][a["command"].index("--export-3mf") + 1], "arranged_1.3mf")
    check("no settings lost", a.get("settings_lost"), [])
    check("still a Bambu project", b3["describe"](dest)["is_bambu_project"], True)

    os.environ["FAKE_MODE"] = "dropsettings"
    a2 = bs["studio_arrange"](src, out_path=os.path.join(tmp, "out", "d.3mf"),
                              studio_exe=studio)
    check("a dropped raft is reported",
          a2.get("settings_lost"), ["hex_nut raft_layers (was 2, now unset)"])
    os.environ["FAKE_MODE"] = "fail"
    a3 = bs["studio_arrange"](src, out_path=os.path.join(tmp, "out", "f.3mf"),
                              studio_exe=studio)
    check("a failed arrange says so", a3["ok"], False)
    check("its code comes from result.json", a3["return_code"], -21)
    os.environ["FAKE_MODE"] = ""
    before = open(src, "rb").read()
    a4 = bs["studio_arrange"](src, studio_exe=studio)
    check("in-place arrange ok", a4["ok"], True)
    check("no scratch file left beside it",
          os.path.exists(src + ".arranging"), False)

    print("\nslicing through the stand-in — the path-join bug stays fixed")
    sl = bs["slice_file"](src, studio_exe=studio)
    check("slice ok", sl["ok"], True)
    check("sliced file beside the project",
          os.path.dirname(sl["file"]), os.path.dirname(src))
    check("floating-regions warning read from result.json",
          "floating regions" in sl["slicer_warnings"][0], True)

    print("\nour own packer centres the plate")
    one = bb["arrange_plate"]([(11, 9.5), (9.3, 9.3)], spacing_mm=6)
    xs = [p["x"] for p in one["positions"]]
    ys = [p["y"] for p in one["positions"]]
    check("group centred in x", round((min(xs) + max(xs)) / 2) in (127, 128, 129), True)
    check("group centred in y", round(sum(ys) / len(ys)), 128)
    nine = bb["arrange_plate"]([(20, 20)] * 9, spacing_mm=6)
    check("nothing pushed off the bed",
          all(4 <= p["x"] - 10 and p["x"] + 10 <= 252 and
              4 <= p["y"] - 10 and p["y"] + 10 <= 252
              for p in nine["positions"]), True)

    print("\nthe P1S no-print corner (bed_exclude_area 0..18 x 0..28 mm)")
    def clear_of_corner(res):
        return all(not bb["_hits_excluded"](p["x"] - p["w"] / 2, p["y"] - p["d"] / 2,
                                            p["x"] + p["w"] / 2, p["y"] + p["d"] / 2,
                                            bb["BED_EXCLUDE_AREAS"], bb["BRIM_MARGIN_MM"])
                   for p in res["positions"] if p)
    full = bb["arrange_plate"]([(40, 40)] * 25, spacing_mm=6)
    check("a crowded plate keeps out of the corner", clear_of_corner(full), True)
    note("parts that fit", sum(1 for p in full["positions"] if p))
    small = bb["arrange_plate"]([(11, 9.5), (9.3, 9.3)], spacing_mm=6)
    check("the screw and nut keep out of the corner", clear_of_corner(small), True)
    check("and are still centred",
          round(sum(p["x"] for p in small["positions"]) / 2) in (126, 127, 128, 129, 130), True)
    none = bb["arrange_plate"]([(40, 40)] * 25, spacing_mm=6, exclude=[])
    check("with no corner, more fits", sum(1 for p in none["positions"] if p)
          >= sum(1 for p in full["positions"] if p), True)

    print("\nroom for brim and raft (Studio: gcode path conflicts, exit -101)")
    raft = bb["part_clearance"](raft=True)
    r2 = bb["arrange_plate"]([(11, 9.5), (9.3, 9.3)], spacing_mm=None,
                             clearances=[raft, raft])
    a_, b_ = r2["positions"]
    gap = max(abs(a_["x"] - b_["x"]) - (11 + 9.3) / 2 - 2 * raft,
              abs(a_["y"] - b_["y"]) - (9.5 + 9.3) / 2 - 2 * raft)
    # w/d in the result include the reach, so measure bare outlines instead
    bare_gap = max(abs(a_["x"] - b_["x"]) - (11 + 9.3) / 2,
                   abs(a_["y"] - b_["y"]) - (9.5 + 9.3) / 2)
    check("two rafted parts at least 2x(brim+raft) apart",
          bare_gap >= 2 * raft, True)
    note("bare gap between outlines", "%.1f mm (needs %.1f)" % (bare_gap, 2 * raft))
    check("rafted parts stay out of the corner, reach included",
          all(not bb["_hits_excluded"](p["x"] - p["w"] / 2, p["y"] - p["d"] / 2,
                                       p["x"] + p["w"] / 2, p["y"] + p["d"] / 2,
                                       bb["BED_EXCLUDE_AREAS"], 0)
              for p in bb["arrange_plate"]([(30, 30)] * 30, spacing_mm=None,
                                           clearances=[raft] * 30)["positions"] if p),
          True)

    print("\ncloud — sign-in, all three ways Bambu can answer (fake Bambu)")
    R = bc["_Response"]
    def fake_bambu(script):
        calls = []
        def fn(method, url, headers=None, body=None, cookies=None, timeout=30):
            calls.append((method, url.split(".com", 1)[-1], body, cookies))
            return script(url, body, cookies)
        fn.calls = calls
        return fn
    jwt = "x." + base64.urlsafe_b64encode(json.dumps(
        {"username": "u_42", "exp": 2000000000}).encode()).decode().rstrip("=") + ".y"

    direct = fake_bambu(lambda u, b, c: R(200, json.dumps({"accessToken": jwt}), {}))
    rec = bc["login"]("a@b.c", "pw", lambda p: "", http_fn=direct)
    check("straight token", rec["token"], jwt)
    check("mqtt username from the token", rec["username"], "u_42")
    check("expiry from the token", rec["expires_at"], 2000000000)
    check("password not kept", "pw" in json.dumps(rec), False)

    def code_flow(u, b, c):
        if u.endswith("/login") and "password" in b:
            return R(200, json.dumps({"accessToken": "", "loginType": "verifyCode"}), {})
        if u.endswith("/sendemail/code"):
            return R(200, "{}", {})
        if u.endswith("/login") and b.get("code") == "123456":
            return R(200, json.dumps({"accessToken": jwt}), {})
        return R(400, json.dumps({"code": 2}), {})
    codes = iter(["000000", "123456"])
    fb = fake_bambu(code_flow)
    rec = bc["login"]("a@b.c", "pw", lambda p: next(codes), http_fn=fb)
    check("emailed-code sign-in, after one wrong code", rec["token"], jwt)
    check("asked Bambu to send the code",
          any(c[1].endswith("/sendemail/code") for c in fb.calls), True)
    expired = fake_bambu(lambda u, b, c: R(400, json.dumps({"code": 1}), {})
                         if "code" in (b or {}) else code_flow(u, b, c))
    try:
        bc["login"]("a@b.c", "pw", lambda p: "111111", http_fn=expired)
        check("expired code reported", False, True)
    except bc["CloudError"] as e:
        check("expired code reported", "expired" in str(e), True)

    def tfa_flow(u, b, c):
        if u.endswith("/login"):
            return R(200, json.dumps({"loginType": "tfa", "tfaKey": "K"}), {})
        if u.endswith("/api/csrf"):
            return R(200, "{}", {"bbl_csrf_token": "CS"})
        if u.endswith("/sign-in/tfa") and b == {"tfaKey": "K", "tfaCode": "654321"} \
                and c == {"bbl_csrf_token": "CS"}:
            return R(200, "{}", {"token": jwt})
        return R(403, "no", {})
    ft = fake_bambu(tfa_flow)
    rec = bc["login"]("a@b.c", "pw", lambda p: "654321", http_fn=ft)
    check("two-factor sign-in, token from the cookie", rec["token"], jwt)
    check("uses the new /api/csrf address",
          any(c[1] == "/api/csrf" for c in ft.calls), True)
    cf = fake_bambu(lambda u, b, c: R(403, "Attention Required! | Cloudflare", {}))
    try:
        bc["login"]("a@b.c", "pw", lambda p: "", http_fn=cf)
    except bc["CloudError"] as e:
        check("a Cloudflare block says what to install", "curl_cffi" in str(e), True)

    print("\ncloud — reading the printer's report")
    report = {"gcode_state": "RUNNING", "mc_percent": 42, "layer_num": 60,
              "total_layer_num": 150, "mc_remaining_time": 38,
              "subtask_name": "no10_24_machine_screw_and_nut_4",
              "nozzle_temper": 219.8, "nozzle_target_temper": 220,
              "bed_temper": 55.1, "bed_target_temper": 55,
              "hms": [{"attr": 50331904, "code": 65543}], "fun": "3EC1AFFF9CFF",
              "ams": {"ams": [{"id": "0", "tray": [
                  {"id": "0", "tray_type": "PLA", "tray_color": "00AE42FF",
                   "remain": 80, "tray_sub_brands": "PLA Basic",
                   "tray_info_idx": "GFA00"},
                  {"id": "1", "tray_type": "PETG", "tray_color": "0086D6FF",
                   "remain": -1},
                  {"id": "2"}, {"id": "3"}]}]},
              "vt_tray": {"tray_type": ""}}
    st = bc["parse_status"](report, {"name": "P1S", "serial": "01P00A"})
    check("state in words", st["state"], "printing")
    check("HMS decoded to Bambu's code", st["errors"][0]["code"], "0300_0100_0001_0007")
    check("HMS links to the wiki", st["errors"][0]["help"].endswith("0300_0100_0001_0007"), True)
    check("AMS slots numbered as Studio shows them",
          [t["slot"] for t in st["ams"]], [1, 2, 3, 4])
    check("colour as #RRGGBB", st["ams"][0]["colour"], "#00AE42")
    check("unknown amount stays unknown", st["ams"][1]["remaining_pct"], None)
    check("empty slots marked empty", st["ams"][2]["loaded"], False)
    check("empty external spool left out", len(st["ams"]), 4)
    check("signed-command firmware flagged", st["commands_need_signing"], True)
    note("status", bc["format_status"](st).splitlines()[1])
    report2 = dict(report, fun="0", ams={"ams": [{"id": "1", "tray": [{"id": "2",
                   "tray_type": "ABS", "tray_color": "FFFFFFFF", "remain": 5}]}]})
    st2 = bc["parse_status"](report2)
    check("a second AMS starts at slot 5", st2["ams"][0]["slot"], 7)
    check("plain firmware not flagged", st2["commands_need_signing"], False)

    print("\ncloud — the token file and printer choice")
    tokfile = os.path.join(tmp, "tok.json")
    bc["save_token"]({"token": jwt, "email": "a@b.c", "expires_at": 2000000000},
                     tokfile)
    check("token round-trips", bc["load_token"](tokfile)["token"], jwt)
    now = 2000000000 - 3 * 86400
    a = bc["account_state"](bc["load_token"](tokfile), now=now)
    check("signed in", a["signed_in"], True)
    check("warns a week before it runs out", "warning" in a, True)
    a = bc["account_state"](bc["load_token"](tokfile), now=2000000001)
    check("an expired token counts as signed out", a["signed_in"], False)
    check("not signed in says how", "login" in bc["account_state"]({})["next"], True)
    devs = [{"serial": "A", "name": "P1S", "model": "P1S", "model_code": "C12"},
            {"serial": "B", "name": "A1", "model": "A1", "model_code": "N2S"}]
    check("the P1S is picked out", bc["pick_printer"](devs)["serial"], "A")
    check("a serial overrides", bc["pick_printer"](devs, "B")["serial"], "B")

    print("\nprinting — matching filaments to your AMS (as it was on 2026-09-18)")
    ams = [{"slot": 1, "loaded": True, "type": "PLA", "colour": "#000000"},
           {"slot": 2, "loaded": True, "type": "PLA", "colour": "#FFF144"},
           {"slot": 3, "loaded": True, "type": "PLA", "colour": "#000000"},
           {"slot": 4, "loaded": True, "type": "PETG", "colour": "#515151",
            "brand": "PETG HF"}]
    m = bpr["map_filaments"]([{"id": 1, "type": "PLA", "colour": "#FFF144"}], ams)
    check("yellow PLA goes to the yellow slot", m["slots"][1]["slot"], 2)
    check("an exact match needs no note", m["notes"], [])
    m = bpr["map_filaments"]([{"id": 1, "type": "PLA", "colour": "#00AE42"}], ams)
    check("green PLA with no green loaded still gets a PLA slot",
          m["slots"][1]["type"], "PLA")
    check("…and says the colour differs", len(m["notes"]), 1)
    m = bpr["map_filaments"]([{"id": 1, "type": "PETG", "colour": "#000000"}], ams)
    check("PETG goes to the PETG HF slot", m["slots"][1]["slot"], 4)
    m = bpr["map_filaments"]([{"id": 1, "type": "ABS", "colour": "#FFFFFF"}], ams)
    check("ABS isn't loaded — refused, not guessed", m["missing"] != [], True)
    m = bpr["map_filaments"]([{"id": 1, "type": "PLA-CF", "colour": "#000000"}], ams)
    check("PLA-CF is not plain PLA", m["missing"] != [], True)
    m = bpr["map_filaments"]([{"id": 1, "type": "PLA", "colour": "#000000"}], ams,
                             {1: "3"})
    check("the person can pick the slot", m["slots"][1]["slot"], 3)
    two = bpr["map_filaments"]([{"id": 1, "type": "PLA", "colour": "#000000"},
                                {"id": 3, "type": "PETG", "colour": "#515151"}], ams)
    check("printer mapping: one entry per project filament, -1 if unused",
          bpr["ams_mapping"](3, two["slots"]), [0, -1, 3])
    check("spool holder is 254",
          bpr["ams_mapping"](1, {1: {"slot": "external"}}), [254])

    print("\nprinting — the one-time approval code")
    g = bpr["issue_code"].__globals__
    g["APPROVALS_FILE"] = os.path.join(tmp, "approvals.json")
    g["CONFIG_PATH"] = os.path.join(tmp, "cfg.json")
    job = os.path.join(tmp, "job.gcode.3mf")
    _write_sliced_fixture(job)
    code = bpr["issue_code"](job, 1, [0])
    check("a code is issued", len(code), 6)
    try:
        bpr["redeem_code"](code, job, 2)
        check("wrong plate refused", False, True)
    except bpr["PrintError"]:
        check("wrong plate refused", True, True)
    code = bpr["issue_code"](job, 1, [0])
    with zipfile.ZipFile(job, "a") as z:
        z.writestr("changed.txt", "x")
    try:
        bpr["redeem_code"](code, job, 1)
        check("a file changed after the preview is refused", False, True)
    except bpr["PrintError"] as e:
        check("a file changed after the preview is refused", "changed" in str(e), True)
    code = bpr["issue_code"](job, 1, [0])
    data = json.load(open(g["APPROVALS_FILE"]))
    data[code]["expires"] = 1                      # long past, never rewritten
    json.dump(data, open(g["APPROVALS_FILE"], "w"))
    try:
        bpr["redeem_code"](code, job, 1)
        check("an expired code is refused", False, True)
    except bpr["PrintError"] as e:
        check("an expired code is refused", "expired" in str(e), True)
    code = bpr["issue_code"](job, 1, [0])
    check("the right code works", bpr["redeem_code"](code, job, 1)["mapping"], [0])
    try:
        bpr["redeem_code"](code, job, 1)
        check("and only once", False, True)
    except bpr["PrintError"]:
        check("and only once", True, True)

    print("\nprinting — start, with stand-ins for the printer")
    idle = lambda: {"state": "finished", "serial": "S1", "ams": ams, "errors": []}
    sent = []
    def fake_send(payload, serial="", wait_s=0):
        sent.append(payload)
        return {"echo": {"result": "success"}, "state": "PREPARE"}
    fake_up = lambda path, serial="": {"name": "job.gcode.3mf", "bytes": 1, "ip": "10.0.0.9"}
    code = bpr["issue_code"](job, 1, [0])
    r = bpr["start"](job, 1, code, _send=fake_send, _upload=fake_up, _status=idle)
    check("started", r["ok"], True)
    pr = sent[-1]["print"]
    check("command is project_file", pr["command"], "project_file")
    check("plate goes in param", pr["param"], "Metadata/plate_1.gcode")
    check("file is on the SD card", pr["url"], "file:///sdcard/job.gcode.3mf")
    check("carries a sequence_id", bool(pr["sequence_id"]), True)
    check("bed levelling on", pr["bed_leveling"], True)
    check("flow calibration and timelapse off", (pr["flow_cali"], pr["timelapse"]),
          (False, False))
    check("uses the AMS", (pr["use_ams"], pr["ams_mapping"]), (True, [0]))
    try:
        bpr["start"](job, 1, "", _send=fake_send, _upload=fake_up, _status=idle)
        check("no code, no start", False, True)
    except bpr["PrintError"]:
        check("no code, no start", True, True)
    busy = lambda: {"state": "printing", "serial": "S1", "ams": ams, "errors": []}
    code = bpr["issue_code"](job, 1, [0])
    try:
        bpr["start"](job, 1, code, _send=fake_send, _upload=fake_up, _status=busy)
        check("won't start over a running print", False, True)
    except bpr["PrintError"]:
        check("won't start over a running print", True, True)

    print("\nprinting — if Bambu's lockdown reaches the P1S")
    opened = []
    bpr["start"].__globals__["bambu_connect_installed"] = lambda: True
    bpr["start"].__globals__["open_bambu_connect"] = \
        lambda path: opened.append(path) or {"ok": True, "route": "bambu_connect"}
    refuse = lambda payload, serial="", wait_s=0: {
        "echo": {"result": "fail", "reason": "mqtt message verify failed"},
        "state": "FINISH"}
    code = bpr["issue_code"](job, 1, [0])
    r = bpr["start"](job, 1, code, _send=refuse, _upload=fake_up, _status=idle)
    check("the start is reported as refused", r["ok"], False)
    check("the route switches to Bambu Connect", bpr["route"](), "bambu_connect")
    check("…and Bambu Connect opens with the file", opened, [job])
    check("why it switched is recorded",
          "verify" in json.load(open(g["CONFIG_PATH"]))["print_route_changed"]["why"], True)
    r = bpr["start"](job, 1, "", _send=fake_send, _upload=fake_up, _status=idle)
    check("next start goes straight to Bambu Connect", r["route"], "bambu_connect")
    bpr["set_route"]("lan_cloud")
    check("and it can be switched back", bpr["route"](), "lan_cloud")
    print("\nprinting — the real refusal from this P1S (2026-09-19)")
    gl = bpr["start"].__globals__
    studio_opened = []
    gl["bs"]["open_in_studio"] = lambda path, exe="": studio_opened.append(path) or {"ok": True}
    gl["bambu_connect_installed"] = lambda: False
    bpr["set_route"]("lan_cloud")
    real = lambda payload, serial="", wait_s=0: {"echo": {"err_code": 84033543},
                                                 "state": None}
    code = bpr["issue_code"](job, 1, [0])
    r = bpr["start"](job, 1, code, _send=real, _upload=fake_up, _status=idle)
    check("err_code alone counts as a refusal, not silence",
          "verification failed" in r["error"], True)
    check("no Bambu Connect installed -> Studio route", bpr["route"](), "studio")
    check("...and Studio opens with the file", studio_opened, [job])
    check("the reason is recorded",
          "84033543" in json.load(open(g["CONFIG_PATH"]))["print_route_changed"]["why"], True)
    gl["bambu_connect_installed"] = lambda: True
    bpr["set_route"]("lan_cloud")
    code = bpr["issue_code"](job, 1, [0])
    bpr["start"](job, 1, code, _send=real, _upload=fake_up, _status=idle)
    check("with Bambu Connect installed -> Bambu Connect route", bpr["route"](), "bambu_connect")
    bpr["set_route"]("lan_cloud")
    gl2 = bpr["pause"].__globals__
    real_send = gl2["bc"]["send_command"]
    gl2["bc"]["send_command"] = lambda payload, serial="", wait_s=8: {
        "echo": {"err_code": 84033543}, "state": "RUNNING"}
    p_ = bpr["pause"]()
    check("a refused pause isn't reported as done", p_["ok"], False)
    check("...and says to use Studio, Handy or the screen", "Handy" in p_["error"], True)
    sends = []
    gl2["bc"]["send_command"] = lambda payload, serial="", wait_s=8: (
        sends.append(payload) or {"echo": {"err_code": 84033543}, "state": "RUNNING"})
    r_ = bpr["resume"]()
    check("once refused, the next one isn't sent", (r_["sent"], sends), (False, []))
    check("...and still says where to do it", "Handy" in r_["error"], True)
    gl2["bc"]["send_command"] = lambda payload, serial="", wait_s=8: (
        sends.append(payload) or {"echo": {"result": "success"}, "state": "PAUSE"})
    p2 = bpr["pause"](retry=True)
    check("--retry sends anyway, and a success clears the refusal",
          (p2["ok"], len(sends), "control_refused" in json.load(open(g["CONFIG_PATH"]))),
          (True, 1, False))
    gl2["bc"]["send_command"] = real_send
    url = bpr["bambu_connect_url"](r"C:\Users\x\Desktop\a b.gcode.3mf")
    check("Bambu Connect link is the documented form",
          url.startswith("bambu-connect://import-file?path=") and
          url.endswith("&version=1.0.0"), True)
    try:
        bpr["stop"](confirm=False)
        check("stop needs a yes", False, True)
    except bpr["PrintError"]:
        check("stop needs a yes", True, True)
    check("pause/resume/stop carry param and sequence_id",
          sorted(bc["command_payload"]("pause")["print"]), ["command", "param", "sequence_id"])

    print("\nlocal network — the printer's announcement and file names")
    pkt = (b"NOTIFY * HTTP/1.1\r\nHOST: 239.255.255.250:1990\r\n"
           b"Location: 192.168.1.42\r\nNT: urn:bambulab-com:device:3dprinter:1\r\n"
           b"USN: 01P00A123456789\r\nDevModel.bambu.com: C12\r\n"
           b"DevName.bambu.com: SCP 2000\r\nDevConnect.bambu.com: cloud\r\n\r\n")
    a = bl["parse_ssdp"](pkt)
    check("address read from the announcement", a["ip"], "192.168.1.42")
    check("serial and model", (a["serial"], a["model"]), ("01P00A123456789", "C12"))
    check("non-Bambu chatter ignored", bl["parse_ssdp"](b"NOTIFY * HTTP/1.1\r\nServer: TV\r\n"), None)
    check("safe name on the SD card", bl["safe_name"](r"C:\a\no10 24 nut_4_1.gcode.3mf"),
          "no10_24_nut_4_1.gcode.3mf")

    print("\nMakerWorld X1 file → P1S")
    x1 = os.path.join(tmp, "makerworld_x1.3mf")
    tpl = os.path.join(HERE, "bambu_template.3mf")
    if os.path.isfile(tpl):
        st_ = b3["read_project_settings"](tpl)
        xs = dict(st_, printer_model="Bambu Lab X1 Carbon",
                  printer_settings_id="Bambu Lab X1 Carbon 0.4 nozzle",
                  machine_start_gcode=";X1 start with lidar\nM400", nozzle_type="hardened_steel",
                  filament_type=["PLA-CF"])
        with zipfile.ZipFile(tpl) as zi, zipfile.ZipFile(x1, "w") as zo:
            for n in zi.namelist():
                d = zi.read(n)
                if n == "Metadata/project_settings.config":
                    d = json.dumps(xs).encode()
                if n == "Metadata/model_settings.config":
                    d = d.replace(b"<plate>", b'<plate>\n    <metadata key="gcode_file" value="Metadata/plate_1.gcode"/>')
                zo.writestr(n, d)
            zo.writestr("Metadata/plate_1.gcode", "; X1 gcode")
        before = open(x1, "rb").read()
        r = bpr["retarget_to_p1s"](x1)
        out_s = b3["read_project_settings"](r["file"])
        check("now a P1S", out_s["printer_model"], "Bambu Lab P1S")
        check("P1S start G-code swapped in",
              out_s["machine_start_gcode"] == st_["machine_start_gcode"], True)
        check("nozzle type is the P1S's", out_s["nozzle_type"], st_["nozzle_type"])
        check("process and filament left alone", out_s["filament_type"], ["PLA-CF"])
        names = zipfile.ZipFile(r["file"]).namelist()
        check("X1 G-code removed", "Metadata/plate_1.gcode" in names, False)
        check("and its plate reference", b"gcode_file" in zipfile.ZipFile(r["file"]).read(
            "Metadata/model_settings.config"), False)
        check("abrasive filament on a stainless nozzle flagged",
              any("abrasive" in n for n in r["notes"]), True)
        check("original untouched", open(x1, "rb").read() == before, True)
        check("output named beside it", os.path.basename(r["file"]), "makerworld_x1_P1S.3mf")
        check("a P1S file is left alone", bpr["retarget_to_p1s"](r["file"])["changed"], False)
        unsliced = os.path.join(tmp, "mw_unsliced.3mf")
        with zipfile.ZipFile(x1) as zi, zipfile.ZipFile(unsliced, "w") as zo:
            for n in zi.namelist():
                if n != "Metadata/plate_1.gcode":
                    zo.writestr(n, zi.read(n))
        r2 = bpr["retarget_to_p1s"](unsliced)
        check("an unsliced Studio file isn't called sliced",
              (r2["sliced_parts_removed"], any("sliced" in n for n in r2["notes"])), ([], False))
        note("report", bpr["format_retarget"](r).splitlines()[1])
    else:
        note("skipped", "no tools/bambu_template.3mf here")

    print("\n== more than one plate ==")
    pp = bb["plan_plates"]
    r_ = pp([(120, 120)] * 4 + [(50, 50)] * 4, heights=[5] * 4 + [80] * 4,
            goal="shortest_time")
    check("shortest_time puts the tall parts together",
          any(set(range(4, 8)) <= set(pl["items"]) for pl in r_["plates"]), True)
    check("tallest plate first", [pl["height_mm"] for pl in r_["plates"]], [80, 5])
    r_ = pp([(20, 20)] * 5, materials=list("ABCDE"))
    check("no plate needs more than 4 filaments",
          [len(pl["materials"]) for pl in r_["plates"]], [4, 1])
    r_ = pp([(300, 20), (20, 20)])
    check("a part bigger than the plate is reported, not dropped",
          (r_["unplaceable"], r_["plate_count"]), ([0], 1))
    r_ = pp([(120, 120)] * 3, clearances=[7.0] * 3)
    check("rafted parts get room for the raft (3 fit without, fewer with)",
          r_["plate_count"] > pp([(120, 120)] * 3)["plate_count"], True)
    check("plate grid columns", [b3["plate_columns"](n) for n in (1, 2, 3, 4, 5, 9, 10)],
          [1, 2, 2, 2, 3, 3, 4])
    check("plate 2 of 2 sits a bed and a fifth to the right",
          [round(v, 1) for v in b3["plate_origin"](1, 2)], [307.2, 0])
    check("plate 3 of 3 starts the next row, towards -y",
          [round(v, 1) for v in b3["plate_origin"](2, 3)], [0, -307.2])
    mp_path = os.path.join(tmp, "two_plates.3mf")
    b3["write_project"](mp_path, [{"mesh": mesh, "name": "cube",
                                   "instances": [(128, 128, 0, 0), (128, 128, 0, 1)],
                                   "settings": {"extruder": "1"}}],
                        {"filament_colour": ["#FFFFFF"], "printer_model": "Bambu Lab P1S"})
    with zipfile.ZipFile(mp_path) as z_:
        cfg_ = z_.read("Metadata/model_settings.config").decode()
        mdl_ = z_.read("3D/3dmodel.model").decode()
        names_ = z_.namelist()
    check("two <plate> blocks", cfg_.count("<plate>"), 2)
    check("each plate lists its one instance",
          [blk.count("<model_instance>") for blk in cfg_.split("<plate>")[1:]], [1, 1])
    check("second copy moved onto plate 2",
          "435.2 128 0" in mdl_ and " 128 128 0\"" in mdl_, True)
    check("a thumbnail per plate", "Metadata/plate_2.png" in names_, True)

    print("\n== more than one filament in project_settings (Studio 2.x layout) ==")
    proot = os.path.join(tmp, "presets")
    os.makedirs(proot)
    json.dump({"name": "base_pla", "nozzle_temperature": ["220"], "hot_plate_temp": ["55"],
               "filament_type": ["PLA"]}, open(os.path.join(proot, "base_pla.json"), "w"))
    json.dump({"name": "dual", "filament_extruder_variant": ["Std", "HF"],
               "nozzle_temperature": ["200", "200"]}, open(os.path.join(proot, "dual.json"), "w"))
    json.dump({"name": "PLA A", "inherits": "base_pla", "include": ["dual"],
               "nozzle_temperature": ["220", "225"]}, open(os.path.join(proot, "PLA A.json"), "w"))
    json.dump({"name": "PETG B", "inherits": "base_pla", "include": ["dual"],
               "nozzle_temperature": ["245", "250"], "hot_plate_temp": ["70"],
               "filament_type": ["PETG"]}, open(os.path.join(proot, "PETG B.json"), "w"))
    one = {"filament_settings_id": ["PLA A"], "filament_type": ["PLA"],
           "filament_colour": ["#00AE42"], "filament_ids": ["GFA00"],
           "filament_extruder_variant": ["Std", "HF"], "filament_self_index": ["1", "1"],
           "nozzle_temperature": ["220", "225"], "hot_plate_temp": ["55"],
           "filament_prime_volume": ["45"], "flush_volumes_matrix": ["0"],
           "flush_volumes_vector": ["140", "140"],
           "different_settings_to_system": ["p", "filament_prime_volume", ""],
           "bed_exclude_area": ["0x0", "18x0", "18x28", "0x28"]}
    two = bpre["expand_filaments"](dict(one), [
        {"preset": "PLA A", "id": "GFA00", "type": "PLA", "colour": "#000000"},
        {"preset": "PETG B", "id": "GFG02", "type": "PETG", "colour": "#FFFFFF"}], proot)
    check("variant lists get a block per filament",
          two["filament_extruder_variant"], ["Std", "HF", "Std", "HF"])
    check("PETG's block comes from its own preset", two["nozzle_temperature"],
          ["220", "225", "245", "250"])
    check("...including settings without the filament_ prefix", two["hot_plate_temp"], ["55", "70"])
    check("the template's filament keeps its tweaks", two["filament_prime_volume"][0], "45")
    check("self index maps each variant to its filament", two["filament_self_index"],
          ["1", "1", "2", "2"])
    check("flush matrix is n x n", two["flush_volumes_matrix"], ["0", "280", "280", "0"])
    check("per-preset diff list grows", len(two["different_settings_to_system"]), 4)
    check("printer settings untouched", len(two["bed_exclude_area"]), 4)
    same = bpre["expand_filaments"](dict(one), [
        {"preset": "PLA A", "id": "GFA00", "type": "PLA", "colour": "#00AE42"}], proot)
    check("one filament on the template's preset changes nothing", same, one)

    print("\n== matching project filaments to the rolls in the AMS ==")
    ams_now = [
        {"slot": 1, "loaded": True, "type": "PLA", "colour": "#161616", "filament_id": "GFA00"},
        {"slot": 2, "loaded": True, "type": "PLA", "colour": "#FFF144", "filament_id": "GFL99"},
        {"slot": 3, "loaded": True, "type": "PLA", "colour": "#000000", "filament_id": "GFL04"},
        {"slot": 4, "loaded": True, "type": "PETG", "colour": "#515151", "filament_id": "GFG02"}]
    mp = bpre["match_loaded_slots"]
    check("Bambu PLA Basic -> the Bambu roll", [r["slot"] for r in mp(["Bambu PLA Basic"], ams_now)], [1])
    check("Overture PLA -> the Overture roll", [r["slot"] for r in mp(["Overture PLA"], ams_now)], [3])
    check("PETG -> the PETG roll", [r["slot"] for r in mp(["PETG"], ams_now)], [4])
    check("two PLAs get two different rolls",
          [r["slot"] for r in mp(["Bambu PLA Basic", "PLA"], ams_now)], [1, 2])
    check("nothing loaded of that type", mp(["ABS"], ams_now), [None])
    check("a named colour picks that colour's roll", [r["slot"] for r in mp(["PLA yellow"], ams_now)], [2])
    check("Overture PLA black -> the Overture black roll",
          [r["slot"] for r in mp(["Overture PLA black"], ams_now)], [3])
    check("no roll in the named colour -> none", mp(["PLA red"], ams_now), [None])
    check("filament identity ignores case/spacing, keeps colour",
          (bpre["filament_key"]("overture  pla Black") == bpre["filament_key"]("Overture PLA black"),
           bpre["filament_key"]("PLA black") == bpre["filament_key"]("PLA white")), (True, False))
    check("colour word read from the name", bpre["colour_hint"]("Overture PLA grey"), "#808080")
    check("support filament may be set to the part's own",
          bb["guard_settings"]({"support_filament": "2", "support_interface_filament": "2"}),
          {"support_filament": "2", "support_interface_filament": "2"})
    check("empty slots are skipped",
          mp(["PLA"], [{"slot": 1, "loaded": False, "type": "", "colour": ""}]), [None])

    print("\n== AMS settings read from the report ==")
    st_ = bc["parse_ams_settings"]({"ams": {"ams": [], "calibrate_remain_flag": False,
                                           "insert_flag": True, "power_on_flag": True}})
    check("update-remaining off is seen", st_["update_remaining"], False)
    check("insert read is seen", st_["read_on_insert"], True)
    check("a report without the switch says unknown",
          bc["parse_ams_settings"]({})["update_remaining"], None)
    txt = bc["format_status"](bc["parse_status"]({"gcode_state": "IDLE", "ams": {
        "ams": [{"id": "0", "tray": [{"id": "0", "tray_type": "PLA", "tray_color": "FFFFFFFF",
                                     "remain": -1}]}],
        "calibrate_remain_flag": False, "insert_flag": True, "power_on_flag": True}}))
    check("status says where to turn it on", "AMS Settings" in txt, True)

    print("\n== Studio version that can start prints ==")
    _bs = runpy.run_path(os.path.join(HERE, "bambu_slice.py"))
    check("1.9.7.52 can't start prints", _bs["studio_can_print"]("01.09.07.52"), False)
    check("2.8.2.61 can", _bs["studio_can_print"]("02.08.02.61"), True)
    check("unknown version isn't guessed", _bs["studio_can_print"](""), None)
    check("warning names the version", "01.09.07.52" in _bs["STUDIO_TOO_OLD"] % "01.09.07.52", True)

    print("\n" + ("-" * 60))
    if FAILURES:
        print("%d FAILED:" % len(FAILURES))
        for f in FAILURES:
            print("  - " + f)
        return 1
    print("all checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
