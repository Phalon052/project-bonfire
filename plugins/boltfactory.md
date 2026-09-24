# BoltFactory

- **Status:** Installed and enabled (`bl_ext.blender_org.boltfactory`) · Blender 5.2.2 · first used 2026-09-16
- **Get it:** https://extensions.blender.org/add-ons/boltfactory/ (or in Blender: Edit → Preferences → Get Extensions → search "BoltFactory").
- **Where it is in Blender:** Add → Mesh → Bolt
- **Use it for:** Bolts, screws, and nuts with metric presets (head type, drive type, thread length, pitch). Existing bolts can be edited from the right-click menu.
- **License:** GPL-3.0 (free).

## Instructions specific to this plugin

- Use it as-is (default rule).
- The listing says it creates bolts at real-world size regardless of the scene settings. **After adding one, measure it** and confirm it is in mm (e.g. an M8 bolt should measure about 8 mm across the thread) before using it.

## Tested behaviour

- **Units:** output is in real mm with the project's unit settings (scale 0.001, mm). An M-size or #-size input in mm comes out at that size; no rescaling needed.
- **Operator:** `bpy.ops.mesh.bolt_add(...)`, run with a 3D-view context override. Key options: `bf_Model_Type` (`bf_Model_Bolt` / `bf_Model_Nut`), `bf_Head_Type` (`bf_Head_Pan`, `bf_Head_Hex`, `bf_Head_Cap`, `bf_Head_Dome`, `bf_Head_CounterSink`, `bf_Head_12Pnt`), `bf_Bit_Type` (`bf_Bit_Philips`, `bf_Bit_Allen`, `bf_Bit_Torx`, …), `bf_Nut_Type` (`bf_Nut_Hex`, `bf_Nut_Lock`, `bf_Nut_12Pnt`), `bf_Major_Dia`, `bf_Minor_Dia`, `bf_Pitch`, `bf_Thread_Length`, `bf_Shank_Length`, `bf_Pan_Head_Dia`, `bf_Hex_Nut_Flat_Distance`, `bf_Hex_Nut_Height`, `bf_Philips_Bit_Dia`, `bf_Phillips_Bit_Depth`, `bf_Div_Count`.
- **Imperial sizes:** convert to mm first. Major Ø = size × 25.4; pitch = 25.4 / TPI; minor Ø (external) = (major − 1.299038 / TPI) in inches × 25.4.
- **Output:** the bolt's thread tip is at z = 0 and the head on top; the nut sits on z = 0. Both are closed solids.
- **Nut threads** use the same major and minor diameters as the bolt, so there is no clearance between them.

## Known problems and workarounds

- **Pan head too short:** there is no pan-head height option; a #10 head came out 2.36 mm tall (the standard is 3.10–3.38). Workaround: after generating, scale the vertices above the thread length in Z to the right height. Set `bf_Phillips_Bit_Depth` to (wanted depth ÷ that scale factor) first so the recess ends up the right depth.
- **Printed threads:** nominal threads won't fit when printed. Use `../03_materials_tolerances.md` §3 *Thread* (Overture PLA, measured 2026-09-24: **0.30 per side on the nut**). Build the nut with `bf_Major_Dia` and `bf_Minor_Dia` each + 2 × the value; keep the bolt nominal.
