# 03 — Materials and Fit Tolerances

Reference for choosing clearances **without asking**.
Setup: **Bambu Lab P1S, 0.4 mm nozzle, AMS**. Default material: **Bambu PLA Basic**.

> Every value in this file was **measured on this printer** with a tolerance test print (§5). A blank cell means
> that material has never been tested: don't fill it from the guides at the bottom — settle it with the user (or a
> test print) when a plan first uses that material.

---

## 1. What a clearance is, and how to apply it ✅

**Definition.** A clearance is the **gap between two mating surfaces, measured straight out from the surface
(along its normal), in mm.** "Per side" means per mating surface: every surface that touches the other part
gets this gap once.

- **Round parts:** the gap is radial, so the diameter changes by **2×** the value.
  Example: a 10.00 peg with the 0.10 sliding fit → hole Ø10.20.
- **Any other shape** (hex, square, D-shaft, slot, star, custom outline): **offset the socket's outline outward
  by the value, uniformly, on every contact surface.** A hex socket for a 10.00 across-flats key with the 0.10
  fit → 10.20 across flats; a slot for a 4.00 × 20.00 tab → 4.20 × 20.20.
- **Never scale** a part or a cutter to make a clearance. Scaling changes the gap with size, opens some faces
  more than others, and moves off-centre features. Printer error is mostly a fixed amount (line width,
  extrusion), not a percentage.
- **In Blender:** grow the socket cutter by the value — for circles, change the radius; for any other shape, use
  *Shrink/Fatten* with **Offset Even** on (`bpy.ops.transform.shrink_fatten(value=…, use_even_offset=True)`) or
  an inset/outset of the 2D outline. Then **measure the gap** on the result (§5 of `01_blender_basics.md`).

**Which side gets it.** Default: **the hole or socket is made bigger**; the peg, key or tab stays at its nominal
size. Only when the request or drawing says so does the peg get smaller instead (or the gap get split). Always
say in the report which side was changed.

**Which surfaces get it.** Only surfaces that **touch the mating part and slide, turn or press against it.**
Not: the floor of a blind pocket, a face held by a screw, a face that never meets the other part. If it isn't
clear which surfaces mate, that is a question (§4).

**Fit names.** "Exact" (black marker) = no gap. **Sliding and rotating are the same fit**: use the sliding
clearance for anything that slides *or* turns. The values are in §3.

### Where the per-side value is not enough on its own

The values in §3 were measured with a **Ø12.00 vertical peg in a vertical hole** (§5). These cases were **not**
tested, so treat them as warnings: model with the §3 value, then name the case in the report and suggest a
small test piece if the fit matters.

| Case | What happens | What to do |
|---|---|---|
| **Gaps in Z** (up–down, between layers) | Layers are 0.20 mm, so a 0.10 gap in Z can round to 0 or 0.20. | Make Z gaps a multiple of the layer height; say which way it was rounded. |
| **Surfaces on the bed** | The first layer squishes wider (elephant foot) and can close a gap at the bottom edge. | Add a small chamfer (≈0.4 mm) on the mating edge that touches the bed, if the request allows it. |
| **Small holes (under ~5 mm)** | Small holes print tighter than the 12 mm test. | Flag it; the 12 mm value may be too tight. |
| **Holes printed on their side** (axis horizontal) | The top of the hole droops; it comes out slightly oval. | Flag it; orient the hole vertically if the part allows. |
| **Inside corners** (square pegs in square sockets) | The nozzle can't make a sharp inside corner, so the peg binds on the corner even with the right gap. | Round the socket's inside corners, or add small corner reliefs. |
| **Long parts (over ~150 mm)** | Shrinkage (~0.3% PLA) starts to add up along the length. | Flag it for long mating lengths. |

## 2. Materials

| Material | Treat as | Notes |
|---|---|---|
| **Bambu PLA Basic** | PLA | Default material. Most dimensionally stable of the list. Shrinkage about 0.3%. |
| **Overture PLA** | PLA | |
| **Bambu PLA Matte** | PLA | |
| **Bambu PETG Basic** | PETG | Tougher and more flexible than PLA. |
| **Bambu ABS** | ABS | |
| **Bambu ABS-CF** | ABS-CF | |

## 3. Default clearances (per side, mm)

| Fit | Drawing colour | Overture PLA | Bambu PLA Basic | PLA Matte | PETG Basic | Bambu ABS | Bambu ABS-CF |
|---|---|---|---|---|---|---|---|
| Exact | Black | 0 |  |  |  |  |  |
| **Press fit** (firm push, friction holds) | Red | **0.05** |  |  |  |  |  |
| **Sliding / rotating fit** (moves freely, little play; also for parts that turn — gears on pegs, hinges, axles) | Green | **0.10** |  |  |  |  |  |
| **Thread** — printed bolt in a printed nut (applied to the internal thread) | — | **0.30** |  |  |  |  |  |
| **Gear backlash** — total play between two printed gears, at the pitch circle | — | **0.20** |  |  |  |  |  |

Blank = never tested. Values come from §5; settle a blank material's values when a plan first uses it.

### How the thread and gear rows are applied

- **Thread:** the value goes on the **internal** thread (the nut or threaded hole); the bolt stays nominal. Both
  the major and the minor diameter of the internal thread grow by 2 × the value (M12 × 1.75 nut at 0.30 →
  major 12.60, minor 10.45). Tested with M12 × 1.75 (BoltFactory, `plugins/boltfactory.md`), bolt printed
  head-down, nut printed flat. Fine threads (pitch under ~1 mm) and small sizes (under ~M6) weren't tested — flag them.
- **Gear backlash:** make **each** gear's teeth thinner at the pitch circle by **half** the backlash (0.10 for
  0.20), and put the gears at the **exact** centre distance (sum of the pitch radii) — never spread the centres
  apart to make play. Teeth must be **involute** (20° pressure angle); the Extra Mesh Objects add-on's teeth are
  not, and jam (`plugins/extra_mesh_objects.md`). A gear's centre hole on its axle or peg uses the **sliding /
  rotating** row. Tested with module 2, 20 teeth, 8 mm thick, on Ø12.00 pegs; much smaller modules (under ~1)
  weren't tested — flag them.

### When only one side is printed

Every value above was measured with **both** parts printed. A printed part mating with a bought or natural part
(a steel dowel in a printed hole, a printed bolt in a hardware-store nut, a wooden dowel in a printed socket)
behaves differently: only one side carries printing error, so the printed-to-printed value can't be reused
as is. These rows stay **blank until tested**; until then, treat any such fit as untested (§4).

| Fit (one side printed) | Drawing colour | Overture PLA | Bambu PLA Basic | PLA Matte | PETG Basic | Bambu ABS | Bambu ABS-CF |
|---|---|---|---|---|---|---|---|
| **Press** — printed hole, bought part (steel pin, bolt shank, bearing, magnet) | Red |  |  |  |  |  |  |
| **Sliding / rotating** — printed hole, bought part | Green |  |  |  |  |  |  |
| **Thread** — printed part with a bought nut or bolt | — |  |  |  |  |  |  |

- **Size the bought part from calipers, not its label.** Its measured size is the nominal the clearance is added
  to. Record the reading in the project's `specifications.md`.
- **Wood and other natural parts** (dowels, rods) vary along their length and swell with humidity. Caliper
  several spots and use the largest; say in the report that the fit depends on the part.
- Expect the difference to run one way: printed pegs and bolts tend to come out slightly fat, so a true-to-size
  bought part usually fits **looser** than a printed one in the same hole. That's a warning, not a value.

✅ **Three fits only (2026-09-24):** exact, press, sliding / rotating. On the Overture PLA tolerance test the
0.10 hole slid and turned the way wanted; the only catch was the seam. A request for a "rotating" or
"loose" fit gets the sliding / rotating clearance.

## 4. When to ask anyway

- The material isn't in the table.
- The fit type isn't clear from the drawing colour or the request.
- The part carries load, must seal, or is safety-related.
- The fit is critical and no measured value exists yet: build it, but suggest a small test piece first.
- The material's column in §3 is blank (never tested).
- Only one side of the fit is printed (a bought or wooden part) and that row in §3 is blank.
- It isn't clear which surfaces of a non-round part mate with the other part.

## 5. Measured results from this printer ✅ Overture PLA · [Fill out] PLA Basic, Matte, PETG, ABS, ABS-CF

Fill this in from tolerance test prints (`Project Bonfire/tolerance tests/`, run as in `USER_GUIDE.md` → *Tolerance tests*: test 1 fits — Ø12.00 peg in holes at each clearance; test 2 threads — M12 bolt in nuts at several clearances; test 3 gears). These override section 3.

- **Never tested:** the whole row stays blank.
- **Date** is `YYYY-MM-DD (Completed)` when every fit was tested and worked, or `YYYY-MM-DD (Partial)` when it was tested but only some fits worked.

| Material | Exact | Press (per side) | Slide / rotating (per side) | Thread (per side, on the nut) | Gear backlash (total) | Hole compensation used | Date |
|---|---|---|---|---|---|---|---|
| **Overture PLA** | 0 — good | **0.05 — good** | **0.10 — good** | **0.30 — good** | **0.20 — good** | none (X-Y hole compensation off) | 2026-09-24 (Completed) |
| Bambu PLA Basic | | | | | | | |
| PLA Matte | | | | | | | |
| PETG Basic | | | | | | | |
| Bambu ABS | | | | | | | |
| Bambu ABS-CF | | | | | | | |

**One side printed** (printed part with a bought or natural part; see §3)

| Material | Press — printed hole, bought part | Slide / rotating — printed hole, bought part | Thread — with a bought nut or bolt | Date |
|---|---|---|---|---|
| Overture PLA | | | | |
| Bambu PLA Basic | | | | |
| PLA Matte | | | | |
| PETG Basic | | | | |
| Bambu ABS | | | | |
| Bambu ABS-CF | | | | |

## 6. Adding a new material [Fill out as needed]

For each new filament, record: brand and type, what it behaves like, press/slide values, anything special (brittleness, flexibility, drying needs).

---

### Sources

- 3D Print Calcs — common tolerances by material (per side): https://3dprintcalcs.uk/reference/common-tolerances/
- Sovol — FDM tolerances and clearances: https://www.sovol3d.com/blogs/news/fdm-3d-printing-tolerances-clearances-how-to-design-parts-that-fit
- X3D Studios — tolerances guide (hole oversize, elephant foot chamfer, threads, shrinkage): https://x3dstudios.com/blog/3d-printing-tolerances-guide
- GrandpaCAD — fit calculator (FDM ranges, on diameter): https://grandpacad.com/en/tools/tolerance-fit-calculator
- Bambu Lab Wiki — X-Y hole/contour compensation: https://wiki.bambulab.com/en/software/bambu-studio/xy-hole-contour-compensation
- Bambu Lab Wiki — print shrinkage (starting compensation values): https://wiki.bambulab.com/en/knowledge-sharing/3d-prints-shrinkage
