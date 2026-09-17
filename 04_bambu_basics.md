# 04 — Bambu Basics

Standing rules for printing: the printer, slicer settings in Bambu Studio, print orientation, splitting parts, and getting parts ready to print.
**Status key:** ✅ = decided · **[Fill out]** = not decided yet (ask when it matters, and suggest adding the answer here).

---

## 1. Printer ✅

- Bambu Lab **P1S**, **AMS** with 4 slots, **0.4 mm** nozzle.
- Build volume: **256 × 256 × 256 mm**. Warn if a part won't fit, and propose how to split it (see section 5).
- Material defaults and fit clearances: see `03_materials_tolerances.md`.

## 2. Slicer settings ✅

- **Always use the current Bambu Studio default values** for the printer, filament, and process, unless requested otherwise.
- **Never change** these unless specifically requested: **wall thickness, infill, speed, temperatures, flow rate.**
- The **only** settings that may be changed without asking are in the approved list below. Anything else: ask first.

### Approved settings (change without asking)

| Setting (Bambu Studio) | Change to | When | Don't use when |
|---|---|---|---|
| **Enable support** | On | The model has overhangs that would cause print errors. | No problem overhangs. |
| **Support type** | `normal(auto)` | The model has **large overhang surfaces**. | — |
| **Support type** | `tree(auto)` | The model has **many small or thin overhangs**. | — |
| **Support type** | `normal(auto)` | The model has **both** large and many small overhangs. | — |
| **On build plate only** | On | Supports only need to stand on the bed, not on the part. | Some overhangs can only be supported from the part itself. |
| **Raft** (Raft layers) | On | The footprint on the bed is **thin, or small compared to the part's height**. | The footprint is large enough to be stable on its own (see examples). |

**Raft examples**

| Use a raft | Don't use a raft |
|---|---|
| A screw with a head **under 15 mm** in diameter and a height of **35 mm or more** | A bearing **15 mm or smaller** in diameter whose height is **less than 1.5 × its diameter** |
| A part standing on feet **under 10 mm square** | A part with a base **larger than about 30 × 30 mm**, even if it is about **3× as tall** as the base is wide |

- ✅ **Raft layers: 2** when a raft is on (Bambu's default is 0, meaning off).

### Other support settings to consider approving [Fill out]

Leave these at their defaults until filled in. For each one, write **when** to change it and **to what**, or "never".

| Setting (Bambu Studio) | What it does | Rule |
|---|---|---|
| **Threshold angle** | Overhangs steeper than this angle get support. A lower angle means less support. | |
| **Support style** | For normal: Default / Grid / Snug. For tree: Tree Slim / Tree Strong / Tree Hybrid / Organic. | |
| **Support critical regions only** | Supports only sharp tails and cantilevers, not all overhangs. | |
| **Remove small overhangs** | Skips support for tiny overhangs. | |
| **Don't support bridges** | Lets the printer bridge gaps instead of supporting them. | |
| **Top Z distance** | Gap between the support and the part. Larger = easier removal, rougher surface. | |
| **Support/raft interface filament** | Uses a different filament from the AMS for the contact layer, which makes supports easier to remove (e.g. PETG interface under PLA). | |
| **Brim type / width** | Adds a flat rim around the base to help small or tall parts stick. Often an alternative to a raft. | |

## 3. Print orientation ✅

Always orient parts for printing before export; don't leave it for manual orientation. Apply in this order:

1. **Strength:** if the part looks load-bearing, orient it so the layer lines suit the load, even if that means not using the largest flat face. Example: "this looks like a shelf bracket, so layers should run along the arm."
2. **Largest flat face on the bed**, when strength doesn't decide it.
3. **Minimize supports**, as long as that doesn't compromise strength. Supports may go on the bed or on the part, whichever works best.

## 4. Getting parts ready to print ✅

When requested to get something ready to print:

- Make a **.3MF**, named the same as the STLs, in the project's `3mf/` folder (see `01_blender_basics.md` → section 2).
- **Place each part as many times as its Quantity** in `specifications.md` (identical parts have one STL, so the copies are made here). If the copies don't fit on one plate, say so and ask. Quantity `n`: place one unless a number is given in the request.
- Use **default** print settings, changing only what the approved list in section 2 allows.
- **Assign each part's filament** from the drawing's `MAT:` marker, or the default material.
- ✅ **AMS slots:** read what's loaded in the AMS each time and map each part's filament to a slot holding that material. If a needed material isn't loaded, say which one and ask. (Needs the printer connection; see section 7.)
- **Commit the project's hardware.** If the project's `specifications.md` lists hardware, reserve it in the inventory with `inventory.py` → `commit("<project folder>")`. Don't edit the tables by hand.
- In the report, also list:
  - any approved settings that were changed, and why
  - the hardware committed, and anything short (the tool adds it to the shopping list)

## 5. Splitting parts and assembly

- ✅ **Split with plain straight cuts**, unless a dovetail or another joining method is specified.
- ✅ Warn when a part is larger than the build volume, and propose where to split it.
- **[Fill out] Where to cut.** Preferences for cut placement: hidden faces, flat areas, away from load paths? Keep pieces a similar size?
- **[Fill out] Alignment.** Add alignment pins or holes to straight cuts? If so, what size and fit (see `03_materials_tolerances.md`)?
- **[Fill out] How pieces are joined.** Glue (leave a glue gap?), screws or bolts from hardware inventory, magnets, friction?
- **[Fill out] Labelling.** Emboss part numbers or arrows on hidden faces so pieces are easy to match?
- **[Fill out] Plate layout.** All pieces on one plate when they fit, or one plate per piece?
- **[Fill out] Naming.** How split pieces are named, e.g. `<object name>_a`, `<object name>_b`.

## 6. Printable minimums [Fill out]

Preferred minimums on the P1S with 0.4 mm nozzle, used to flag features too thin to print:

- Minimum wall or feature thickness
- Minimum pin or text size
- Default chamfer or fillet on outside edges (or none)

## 7. Allowed actions in Bambu Studio ✅

Applies to the Bambu Studio MCP (plan: `BAMBU_MCP_PLAN.md`).

**Allowed without asking**

- Generate **supports and rafts** (within the approved list in section 2).
- **Orient** objects (following section 3; the reason goes in the report).
- **Arrange / pack the plate** (Bambu Studio's *Arrange* button), including adjusting the spacing between items.
- **Slice.**
- **Save the sliced file** (`.gcode.3mf`) in the project's `3mf/` folder, named like the 3MF (`<name>_<n>.gcode.3mf`).

**Needs approval every time**

- **Starting a print.** Show the summary first (file, plate, filament per AMS slot, print time, filament used), then wait for a yes. Never start one without it, even if asked earlier in the conversation.
- Pausing is fine when asked; **stopping** a print needs a yes.

**Printer connection (Developer Mode)**

- ✅ Developer Mode may be used. It is switched on and off with the `/bf-printer-mode` command.
- It can only be changed on the printer's screen (Settings → WLAN/Network: turn on **LAN-only Mode**, then **Developer Mode**). The command checks the current state and gives the steps. While it's on, cloud printing and the Bambu Handy app don't work.
- When Developer Mode is off: slicing still works; to print, open the sliced file in Bambu Studio for you to send.

