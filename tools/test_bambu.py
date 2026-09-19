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
    sys.exit(256 - 21)
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
    path = os.path.join(tmp, "bambu-studio")
    with open(path, "w") as fh:
        fh.write(FAKE_STUDIO)
    os.chmod(path, 0o755)
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
    check("the PLA door-open warning is translated",
          "front door" in bs["SLICE_WARNINGS"]["bed_temperature_too_high_than_filament"], True)
    note("report", bs["format_slice_report"](
        dict(r, ok=True, file=sliced)).splitlines()[0])

    print("\nslicing — an unsliced file is not mistaken for a sliced one")
    r2 = bs["read_slice_info"](out)
    check("plain project not sliced", r2["sliced"], False)

    print("\nslicing — exit codes and naming")
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
    r3 = bs["slice_file"](out, studio_exe="/nowhere/bambu-studio")
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
    check("no settings lost", a["settings_lost"], [])
    check("still a Bambu project", b3["describe"](dest)["is_bambu_project"], True)

    os.environ["FAKE_MODE"] = "dropsettings"
    a2 = bs["studio_arrange"](src, out_path=os.path.join(tmp, "out", "d.3mf"),
                              studio_exe=studio)
    check("a dropped raft is reported",
          a2["settings_lost"], ["hex_nut raft_layers (was 2, now unset)"])
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
