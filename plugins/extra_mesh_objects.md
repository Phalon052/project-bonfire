# Extra Mesh Objects (gears)

- **Status:** Installed · version 0.4.1 (Apr 2026), Blender 5.2.2. Tested 2026-09-17.
- **Get it:** https://extensions.blender.org/add-ons/extra-mesh-objects/ (or in Blender: Edit → Preferences → Get Extensions → search "Extra Mesh Objects").
- **Where it is in Blender:** Add → Mesh → Gears (Gear, Worm). Operators: `bpy.ops.mesh.primitive_gear`, `bpy.ops.mesh.primitive_worm_gear`.
- **Use it for:** Visual or loose-fit gears, quick prototypes, non-critical motion.
- **Don't use it for:** Gears that must mesh smoothly at the correct centre distance. Use the scripted involute fallback (`plugins/README.md` → *Fallback*) instead.
- **License:** GPL (free).

## What it can make

| Feature | Setting | Notes |
|---|---|---|
| Spur gear | `number_of_teeth`, `radius` (pitch radius) | Basic straight-tooth gear |
| Helical-style gear | `skew` (angle) | Teeth twisted across the width |
| Bevel / conical gear | `conangle` (angle) | Teeth taper toward one face |
| Crown (face) gear | `crown` (length), or a negative `radius` | Teeth point along the axis |
| Worm | Worm Gear: `number_of_teeth`, `number_of_rows`, `row_height`, `skew` per row | Screw-like worm; `number_of_teeth` = teeth around, `number_of_rows` = rows along the length |
| Tooth shape | `addendum`, `dedendum`, `angle` (pressure angle) | See the tooth profile note below |
| Hub | `base` | Material kept inside the root circle; the rest is a centre bore |

The extension also adds non-gear objects under Add → Mesh: pipe joints (elbow, T, Y, cross, N-way), round cube, twisted torus, supertoroid, torus knot, gems and diamonds, star, step pyramid, regular solids, teapot, and math-function surfaces.

## How the settings map to real sizes (mm, scene unit scale 0.001)

- `radius` = pitch radius = module × teeth ÷ 2. Tip radius = `radius` + `addendum`; root radius = `radius` − `dedendum`.
- Standard teeth: `addendum` = module, `dedendum` = 1.25 × module, `angle` = 20° (in radians).
- **`width` is half the thickness.** The gear goes from −`width` to +`width` on Z. For an 8 mm gear, set `width` = 4 and move it up 4 mm so it sits on the bed.
- `base` is measured inward from the **root** circle. Bore radius = `radius` − `dedendum` − `base`. There is always a centre bore; to get a solid gear, set `base` so the bore is tiny, then fill or cut the bore yourself.
- The gear is created with a tooth centred at half a tooth pitch from +X. When placing two gears in mesh, rotate one by half a tooth so a tooth faces a gap.

## Instructions specific to this plugin

- **Always close the mesh before exporting.** The centre bore has no inner wall, so the gear isn't a closed solid. Fix: `bmesh.ops.bridge_loops` on the boundary edges (tested: gives a closed solid). The worm has open ends the same way; fill them.
- **The teeth are not involute.** Each flank is a straight radial line from root to pitch circle, then a straight chamfer to the tip. Tooth thickness at the pitch circle is exactly half the pitch, so there is no backlash.
- **Meshing test (module 2, 20T + 10T, 16 mm thick):** at the correct centre distance (30 mm) the teeth overlap by 0.6–2.6 mm³ through the whole mesh cycle. At 30.5 mm there is still slight overlap; at 31 mm there is none. So these gears only run if spread about 1 mm apart, which gives sloppy, noisy motion.
- For gears that must mesh, use the scripted involute fallback and add backlash from `../03_materials_tolerances.md` §3 *Gear backlash* (Overture PLA, measured 2026-09-24: **0.20 total** — each gear's teeth 0.10 thinner at the pitch circle, exact centre distance). Build them with `tools/gear.py` (below).

## Scripted involute gear: use `tools/gear.py`

For any gear that must mesh, don't use this add-on. Use `tools/gear.py` (the fallback `plugins/README.md`
asks for; proven on the tolerance tests' gear pair). It builds involute spur gears as closed solids, takes the
backlash and the centre-hole clearance from `03_materials_tolerances.md` §3 for the material, refuses a material
whose values are blank, places pairs at the exact centre distance, checks a pair for overlap through one tooth,
and measures a gear for the confirmation table. Usage is in the file's header; `tools/test_gear.py` tests the
maths without Blender.

## Known problems and workarounds

- Open centre bore / open worm ends → not a closed solid. Bridge or fill the boundary loops before export.
- Non-involute teeth interfere at the true centre distance → use the involute fallback for real gear trains.

## Alternative

- *Blender-Involute-gear* (https://github.com/dracir9/Blender-Involute-gear): a small free add-on for straight involute gears only. Its supported Blender version isn't stated.
