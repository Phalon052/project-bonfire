# 03 — Materials and Fit Tolerances

Reference for choosing clearances **without asking**.
Setup: **Bambu Lab P1S, 0.4 mm nozzle, AMS**. Default material: **Bambu PLA Basic**.

> The values below are **starting points gathered from online guides** (sources at the bottom), not measurements from this printer.
> Once a tolerance test print is done, record the results in section 5. **Measured values always override these.**

---

## 1. How to read the numbers

- All clearances are **per side (radial)**, in mm. The total gap on a diameter is **2×** the value.
  Example: a 10 mm peg with a 0.20 mm/side sliding fit → hole is 10.40 mm.
- **Default: apply the clearance to the hole or socket** and keep the peg at its nominal size, unless the drawing or request says otherwise.
- "Exact" (black marker) means no clearance is added.
- **Sliding and rotating are the same fit** (0.20 mm/side for Overture PLA): use the sliding clearance for anything that slides *or* turns.

## 2. Materials

| Material | Treat as | Notes |
|---|---|---|
| **Bambu PLA Basic** | PLA | Default material. Most dimensionally stable of the list. Shrinkage about 0.3%. **No clearances set (cleared 2026-09-24)** — when a plan uses it, settle its values then (test or decide) before modelling fits. |
| **Overture PLA** | PLA | **Measured on this printer** (§5, 2026-09-24). |
| **Bambu PLA Matte** | PLA | **No clearances set** (cleared 2026-09-24). |
| **Bambu PETG Basic** | PETG | **No clearances set (cleared 2026-09-24).** Tougher and more flexible than PLA. |
| **Bambu ABS** | ABS | **No clearances set** (added 2026-09-24). |
| **Bambu ABS-CF** | ABS-CF | **No clearances set** (added 2026-09-24). |

## 3. Default clearances (per side, mm)

| Fit | Drawing colour | Overture PLA (measured, §5) | Bambu PLA Basic | PLA Matte | PETG Basic | Bambu ABS | Bambu ABS-CF |
|---|---|---|---|---|---|---|---|
| Exact | Black | 0 | — | — | — | — | — |
| **Press fit** (firm push, friction holds) | Red | **0.05** | — | — | — | — | — |
| Snug (tight, removable by hand) | — | 0.10 | — | — | — | — | — |
| **Sliding / rotating fit** (moves freely, little play; also for parts that turn — gears on pegs, hinges, axles) | Green | **0.20** | — | — | — | — | — |

— = not set. Bambu PLA Basic, PLA Matte and PETG Basic values were cleared on 2026-09-24; Bambu ABS and ABS-CF have none yet. Address each when a plan first uses it.

✅ **Four fits only (2026-09-24):** exact, press, snug, sliding. *Loose* is dropped, and *rotating* uses
the sliding value — on the Overture PLA tolerance test, the sliding hole moved the way wanted for both sliding and
rotating parts. A request for a "rotating" or "loose" fit gets the sliding clearance.

Ranges these came from: PLA press 0.00–0.15, slide 0.15–0.30, loose 0.30–0.40, rotating 0.30–0.60. Defaults are picked from the middle of the overlapping ranges.

## 4. When to ask anyway

- The material isn't in the table.
- The fit type isn't clear from the drawing colour or the request.
- The part carries load, must seal, or is safety-related.
- The fit is critical and no measured value exists yet: build it, but suggest a small test piece first.

## 5. Measured results from this printer ✅ Overture PLA · [Fill out] PLA Basic, Matte, PETG, ABS, ABS-CF

Fill this in from a tolerance test print (Ø12.00 pegs in holes at each clearance). These override section 3.

| Material | Exact | Press (per side) | Snug (per side) | Slide / rotating (per side) | Hole compensation used | Date / notes |
|---|---|---|---|---|---|---|
| **Overture PLA** | 0 — good | **0.05 — good** | **0.10 — good** | **0.20 — good** | none (X-Y hole compensation off) | 2026-09-24 (Completed)|
| Bambu PLA Basic | | | | | | |
| PLA Matte | | | | | | |
| PETG Basic | | | | | | |
| Bambu ABS | | | | | | |
| Bambu ABS-CF | | | | | | |

## 6. Adding a new material [Fill out as needed]

For each new filament, record: brand and type, what it behaves like, press/snug/slide values, anything special (brittleness, flexibility, drying needs).

---

### Sources

- 3D Print Calcs — common tolerances by material (per side): https://3dprintcalcs.uk/reference/common-tolerances/
- Sovol — FDM tolerances and clearances: https://www.sovol3d.com/blogs/news/fdm-3d-printing-tolerances-clearances-how-to-design-parts-that-fit
- X3D Studios — tolerances guide (hole oversize, elephant foot chamfer, threads, shrinkage): https://x3dstudios.com/blog/3d-printing-tolerances-guide
- GrandpaCAD — fit calculator (FDM ranges, on diameter): https://grandpacad.com/en/tools/tolerance-fit-calculator
- Bambu Lab Wiki — X-Y hole/contour compensation: https://wiki.bambulab.com/en/software/bambu-studio/xy-hole-contour-compensation
- Bambu Lab Wiki — print shrinkage (starting compensation values): https://wiki.bambulab.com/en/knowledge-sharing/3d-prints-shrinkage
