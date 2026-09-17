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

## 2. Materials

| Material | Treat as | Notes |
|---|---|---|
| **Bambu PLA Basic** | PLA | Default material. Most dimensionally stable of the list. Shrinkage about 0.3%. |
| **Overture PLA** | **Same as Bambu PLA Basic** | Confirmed to print the same on this printer. |
| **Bambu PLA Matte** | PLA, with caution for press fits | Weaker than PLA Basic between layers (Bambu data sheet: Z tensile 22 MPa vs 31 MPa; Z elongation about 4.8%). Press-fit bosses and thin walls are more likely to crack along layer lines. |
| **Bambu PETG Basic** | PETG | Needs more clearance than PLA (about +0.05 mm/side). Shrinkage about 0.5%. Tougher and more flexible, so press fits are more forgiving. |

## 3. Default clearances (per side, mm)

| Fit | Drawing colour | PLA Basic / Overture | PLA Matte | PETG Basic |
|---|---|---|---|---|
| Exact | Black | 0 | 0 | 0 |
| **Press fit** (firm push, friction holds) | Red | **0.05** | **0.10** ¹ | **0.10** |
| Snug (tight, removable by hand) | — | 0.10 | 0.10 | 0.15 |
| **Sliding fit** (moves freely, little play) | Green | **0.20** | **0.20** | **0.25** |
| Loose / easy fit | — | 0.35 | 0.35 | 0.40 |
| Rotating / print-in-place | — | 0.40 | 0.40 | 0.55 |

Ranges these came from: PLA press 0.00–0.15, slide 0.15–0.30, loose 0.30–0.40, rotating 0.30–0.60; PETG press 0.05–0.15, slide 0.20–0.30, loose 0.30–0.50, rotating 0.50–0.70. Defaults are picked from the middle of the overlapping ranges.

¹ **Judgment call, not from a source:** PLA Matte uses a slightly looser press fit because of its weaker layer bonding. No source gives Matte-specific clearances; for sliding fits there's no evidence it differs from PLA Basic.

## 4. When to ask anyway

- The material isn't in the table.
- The fit type isn't clear from the drawing colour or the request.
- The part carries load, must seal, or is safety-related.
- The fit is critical and no measured value exists yet: build it, but suggest a small test piece first.

## 5. Measured results from this printer [Fill out]

Fill this in from a tolerance test print (pegs and holes at clearances from 0.05 to 0.50 mm). These override section 3.

| Material | Press (per side) | Slide (per side) | Loose (per side) | Hole compensation used | Date / notes |
|---|---|---|---|---|---|
| PLA Basic / Overture | | | | | |
| PLA Matte | | | | | |
| PETG Basic | | | | | |

## 6. Adding a new material [Fill out as needed]

For each new filament, record: brand and type, what it behaves like, press/slide/loose values, anything special (brittleness, flexibility, drying needs).

---

### Sources

- 3D Print Calcs — common tolerances by material (per side): https://3dprintcalcs.uk/reference/common-tolerances/
- Sovol — FDM tolerances and clearances: https://www.sovol3d.com/blogs/news/fdm-3d-printing-tolerances-clearances-how-to-design-parts-that-fit
- X3D Studios — tolerances guide (hole oversize, elephant foot chamfer, threads, shrinkage): https://x3dstudios.com/blog/3d-printing-tolerances-guide
- GrandpaCAD — fit calculator (FDM ranges, on diameter): https://grandpacad.com/en/tools/tolerance-fit-calculator
- Bambu Lab Wiki — X-Y hole/contour compensation: https://wiki.bambulab.com/en/software/bambu-studio/xy-hole-contour-compensation
- Bambu Lab Wiki — print shrinkage (starting compensation values): https://wiki.bambulab.com/en/knowledge-sharing/3d-prints-shrinkage
- Bambu PLA Matte technical data sheet: https://store.bblcdn.com/s7/default/5b061f2feeac4ba88f355a33248bbda7/Bambu_PLA_Matte_Technical_Data_Sheet.pdf
- 3D Mag — Matte PLA (PLA Basic vs Matte strength): https://www.3dmag.com/3d-wikipedia/matte-pla-filament-print-settings-strength-finish/
