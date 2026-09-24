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
- For gears that must mesh, use the scripted involute fallback and add backlash from `../03_materials_tolerances.md` §3 *Gear backlash* (Overture PLA, measured 2026-09-24: **0.20 total** — each gear's teeth 0.10 thinner at the pitch circle, exact centre distance). A working involute outline (20° PA, backlash as tooth thinning) is below, under *Scripted involute gear*.

## Scripted involute gear (the fallback for gears that must mesh)

Used for the tolerance tests' gear (module 2, 20 teeth, 8 mm thick). It returns a 2D outline: extrude it to the
gear's thickness, then cut the centre hole (axle Ø + 2 × the sliding / rotating clearance, `03` §3).
`backlash` is the thinning **per gear**, half the total backlash in `03` §3 (0.10 for Overture PLA's 0.20).

```python
def gear_outline(m=2.0, z=20, pa=20.0, backlash=0.10, n_inv=24, n_root=8):
    import math, numpy as np
    pa=math.radians(pa); rp=m*z/2; rb=rp*math.cos(pa); ra=rp+m; rf=rp-1.25*m
    inv=lambda a: math.tan(a)-a
    th0=(math.pi/(2*z) - backlash/(2*rp)) + inv(pa)   # half-tooth angle at the base circle
    rs=np.linspace(max(rb,rf), ra, n_inv); pts=[]
    for k in range(z):
        c=2*math.pi*k/z
        right=[(r, c-(th0-inv(math.acos(rb/r)))) for r in rs]
        left =[(r, c+(th0-inv(math.acos(rb/r)))) for r in rs]
        tip  =[(ra,a) for a in np.linspace(right[-1][1], left[-1][1], 6)[1:-1]]
        root =[(rf,a) for a in np.linspace(c+th0, c+2*math.pi/z-th0, n_root)[1:-1]]
        pts += [(rf,c-th0)] + right + tip + left[::-1] + [(rf,c+th0)] + root
    return [(r*math.cos(a), r*math.sin(a)) for r,a in pts]   # 2D outline, extrude to thickness
```

- Place meshing gears at the exact centre distance (m × (z1 + z2) / 2), one rotated by half a tooth (180°/z).
- Before exporting, check for overlap at the true centre distance: intersect the two gears (Boolean *Intersect*) at a few rotations across one tooth; the volume should be 0.

## Known problems and workarounds

- Open centre bore / open worm ends → not a closed solid. Bridge or fill the boundary loops before export.
- Non-involute teeth interfere at the true centre distance → use the involute fallback for real gear trains.

## Alternative

- *Blender-Involute-gear* (https://github.com/dracir9/Blender-Involute-gear): a small free add-on for straight involute gears only. Its supported Blender version isn't stated.
