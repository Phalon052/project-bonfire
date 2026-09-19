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
- ✅ **Supports and rafts print in the part's own filament** (2026-09-19) — never a second filament or colour. Set per part (`support_filament` / `support_interface_filament` = the part's filament) whenever supports or a raft are on.

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
- **Place each part as many times as its Quantity** in `specifications.md` (identical parts have one STL, so the copies are made here). If the copies don't fit on one plate, they go on as many plates as it takes, in the same 3MF (fewest plates by default; *shortest time* groups tall parts). Quantity `n`: place one unless a number is given in the request.
- ✅ **One filament per plate — no multicolour by default** (2026-09-19). Parts in different filaments (type, brand **or** colour, e.g. *Overture PLA black* vs *PLA yellow*) go on separate plates, so the AMS never swaps mid-print (no purge waste or extra time). A multicolour plate only when asked for.
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

**Needs approval every time** — enforced by the tools themselves (2026-09-19), because the Claude app auto-approves tool calls in this project: `print_preview` shows the summary and hands out a one-time code, valid 10 minutes for that file and plate only, and `start_print` refuses without it. `stop_print` refuses without an explicit yes. This can be switched off with `print_needs_approval: false` in `tools/bambu_config.json`, but then nothing stands between a request and a moving print head.


- **Starting a print.** Show the summary first (file, plate, filament per AMS slot, print time, filament used), then wait for a yes. Never start one without it, even if asked earlier in the conversation.
- Pausing is fine when asked; **stopping** a print needs a yes.

**Printer connection (Bambu Cloud)** ✅

- ✅ **Decided 2026-09-18: the printer is reached through Bambu Cloud**, not over the LAN. The printer stays signed in to the Bambu account, with **LAN-only Mode off** and **Developer Mode off** — either one turns the cloud off. The Handy app and printing from away keep working.
- This replaces the earlier Developer Mode decision. There is no `/bf-printer-mode` command.
- **What cloud can do:** printer status and the AMS contents. (Pause, resume, stop and starting a file on the SD card worked over the cloud until the 2026 firmware lockdown; see below.)
- **What cloud cannot do:** there is no way to send a sliced file to the printer over the cloud — no such endpoint exists. Sliced files reach the printer through Bambu Studio or the Handy app. The camera is also LAN-only on a P1S.
- So the flow is: this project builds and slices the file, you send it with Bambu Studio, and the MCP watches and controls the print from there. If sending files automatically ever matters more than the Handy app does, that needs the printer's LAN address and access code, and the LAN path would have to be built.
- Signing in uses the account email and password and usually an emailed verification code. The token lasts about three months and cannot be refreshed, so signing in again is a hands-on step.

**Getting a print to the printer (2026-09-19)** ✅

- **Route `lan_cloud` (default):** the sliced file is copied onto the printer's SD card over the home network (FTPS, port 990, user `bblp`, the printer's access code), then started through Bambu Cloud. The printer stays in normal cloud mode. Its address is found from the printer's own network announcement (or `BAMBU_PRINTER_IP` in `.env`); the access code comes from Bambu Cloud (or `BAMBU_ACCESS_CODE` in `.env`) and is never stored or shown.
- ⚠️ **It has (2026-09-19).** The first start sent from the tools was refused with `err_code 84033543` — *MQTT command verification failed*: this P1S's firmware now only accepts print commands signed by Bambu's own software. The home-network upload itself worked (address found automatically, access code from the cloud). **Prints now start from Bambu Studio**: the tools build, slice and preview the file and open it in Studio, and you press Print. Pause / resume / stop over the cloud are refused the same way (confirmed 2026-09-19 with a pause) — use Studio's Device tab, Handy, or the printer's screen. After the first refusal the tools don't send them any more; they answer straight away with where to do it (`--retry` checks whether a firmware update lifted it). Reading status over the cloud still works.
- ⚠️ **Bambu Studio must be 2.0 or newer to start prints (2026-09-19).** Studio 01.09.07.52 sent the job to the cloud fine — it showed in Handy's history as "printing" — but the printer ignored the start, because that version predates the signed commands. Keep Studio updated; `bambu_setup_check` and `start` warn when it's too old. The only ways around it are Developer Mode (turns the cloud off, ruled out in section 7) or signing commands with keys taken out of Bambu's software (not done here).
- If Bambu Connect gets installed, `print_route bambu_connect` makes starts open there instead.
- **If Bambu's lockdown reaches the P1S** (network print starts only through Bambu Connect — already the case on the X1 series), the printer will refuse a start; the tool then switches the route to `bambu_connect` by itself, opens Bambu Connect with the file, and records why. `print_route` switches it back or forward by hand.
- **Start options:** bed levelling on; flow calibration, timelapse, vibration calibration and first-layer inspection off.
- **AMS slots:** each filament goes to a slot with exactly the same material (PLA-CF is not PLA), same colour first; a different colour is used with a note; a material that isn't loaded stops the print. Slots can be chosen by hand in the preview.
- **MakerWorld files set up for an X1:** `retarget_to_p1s` swaps in the P1S's 69 machine settings (start/end G-code, nozzle, limits, bed no-print area) from `tools/bambu_template.3mf` and keeps the process and filament choices, like switching printers in Studio. The original isn't touched; a file already sliced for the X1 has that G-code removed and must be sliced again. It warns about abrasive filament on the P1S's stainless nozzle.

## 8. Building the print file ✅

The Bambu MCP (`tools/bambu.py`, `tools/bambu_slice.py`, `tools/bambu_mcp.py`) applies sections 2, 3, 4 and 7 itself. Worth knowing:

- **Supports are judged by the drop underneath, not just the angle.** A surface shallower than 30 degrees only gets support when there is a real gap under it. The underside of a printed thread is shallow but lands on the turn below, so a screw printed upright gets no support. Lettering, hole facets and other patches under about 2 mm² are ignored.
- **Orientation follows section 3 in order:** a load-bearing name keeps the orientation it was modelled in; otherwise the largest flat face goes down, and fewest supports only decides between ways up that sit on a comparable amount of bed.
- **`tools/bambu_template.3mf`** is a project saved from Bambu Studio with the P1S presets selected. Every setting this project doesn't touch is copied from it, so the file matches Bambu's defaults exactly. Without it the presets are built from scratch — workable, but not identical, and the report says so.
- **Plate layout** uses Bambu Studio's own Arrange when Studio is installed and no part has a raft, keeping each part's way up. With a raft, a custom spacing, or no Studio, the project's own packer lays the plate out instead: centred, with room for each part's brim and raft, and clear of the P1S's no-print corner (18 × 28 mm, front-left). Studio's command-line Arrange ignores a raft's spread, which makes rafted parts' first layers collide.
- ✅ **PLA and the bed temperature (2026-09-19):** the bed temperatures are set deliberately and are not to be changed. Studio warns on every PLA slice that the bed is above PLA's softening point and suggests opening the door; that warning is not wanted and is hidden in slice reports. No door rule.
- **Sliced files** go in the project's `3mf/` folder as `<name>_<n>.gcode.3mf`, never overwriting. The slice report gives print time, filament per slot in grams and metres, whether support was generated, and whether any toolpath falls outside the printable area.
- **Preset names:** machine `Bambu Lab P1S 0.4 nozzle`, process `0.20mm Standard @BBL X1C` (the P1S shares the X1C process family — there are no `@BBL P1S` process presets). Filament preset names differ between Studio versions, so each material lists the names it might have and the one actually installed is used.
