# 3D Print Toolbox

- **Status:** Installed and enabled (`bl_ext.blender_org.print3d_toolbox`) · v1.4.1 · Blender 5.2.2 · set up 2026-09-20
- **Get it:** https://extensions.blender.org/add-ons/print3d-toolbox/ (or in Blender: Edit → Preferences → Get Extensions → search "3D Print Toolbox"). No longer bundled with Blender since 4.2.
- **Where it is in Blender:** 3D view → N sidebar → **3D-Print** tab (Analyze, Clean Up, Edit, Export)
- **Use it for:** checking a part is printable before it's exported — always through `tools/export_gate.py`, never by hand.
- **Don't use it for:** exporting (its Export panel skips the gate and the file naming), or automatic repair.
- **License:** GPL-3.0 (free).

## Instructions specific to this plugin

- **Every STL goes through `tools/export_gate.py` → `export_part(object, project)`.** It checks the
  object as it would be printed (modifiers applied, world position) and writes nothing on a failure.
  `check_part(object)` checks without exporting.
- **Blocking:** Solid (non-manifold edges, bad contiguous edges = flipped normals), Intersections,
  Degenerate (zero faces / zero edges), Shells > 1. **Warnings:** Thickness (< 0.8 mm too thin, 0.8–1.2 mm below recommended — `04_bambu_basics.md` §6), Overhang
  (> 45°, ignoring the faces on the bed), Sharp edges.
- `allow_shells=N` only for a deliberate multi-piece object (print-in-place), and only when asked.
- The gate sets the Toolbox's thresholds in mm for its own run and puts the panel's values back.
- **Cleanup (Make Manifold) moves geometry.** Don't run it automatically. After any cleanup, measure
  again and redo the confirmation table (`01_blender_basics.md` §5).
- To see *where* a failure is: in the 3D-Print panel run the same check, then click the result in edit
  mode to select the faces/edges.

## Tested behaviour (2026-09-20)

- **Driving it from Python:** each check is a class in
  `bl_ext.blender_org.print3d_toolbox.operators.analyze` with a static `main_check(obj, data)` that
  appends report items (`name`, `value`, `indices`). The gate calls those directly — no operator
  context needed. Operators exist too (`bpy.ops.mesh.print3d_check_solid`, `_intersect`, `_shells`,
  `_degenerate`, `_nonplanar`, `_thick`, `_sharp`, `_overhang`, `_all`); their results go to the
  module-level `report.get()`.
- **Units:** the Toolbox's thresholds are in Blender units. With this project's units (scale 0.001,
  mm) 1 BU = 1 mm, so its default `thickness_min` of 0.001 means 0.001 mm — the gate sets it itself.
- **Its Overhang check counts the bottom face** (it points straight down). The gate uses its own
  overhang count that skips faces on the bed.
- Tested on: a clean cube (passes), a cube with a missing face (blocked: 4 non-manifold edges), two
  loose cubes (blocked: 2 shells), two overlapping cubes (blocked: 6 intersecting faces), a 0.4 mm
  plate (passes, thin-wall warning), a bevelled cube (modifier applied in the export, position kept).

## Known problems and workarounds

- Intersections on very dense meshes (threads) can take a few seconds.
