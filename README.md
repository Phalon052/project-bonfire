# Project Bonfire

> [!WARNING]
> **Pre-1.0: under rapid change.** Project Bonfire is being actively reworked and reconfigured. Expect major refactors to make it easier to use, use fewer tokens, simplify the folder structure, and add centralized configuration files. Example projects are on the way too.
> It will be considered stable at the **1.0 release**, when this notice is removed.

**How it works:** see [`USER_GUIDE.md`](USER_GUIDE.md) for setup, commands, drawing marks and folder layout. Claude's rules are in [`PROJECT_INSTRUCTIONS.md`](PROJECT_INSTRUCTIONS.md) and the numbered `0x_*.md` files.

---

## Current State
A Claude (Cowork) workspace for designing 3D-printable parts in **Blender** and printing them on a **Bambu Lab P1S**. Working today:

- **Design:** sketches, photos or plain requests become modelled parts, with specs captured and every dimension checked against them before an STL is exported.
- **Files:** project folders, versioned exports and a searchable project index are handled automatically.
- **Fit:** clearances are set from the filament and the fit type.
- **Hardware:** an inventory with reservations per project and an automatic shopping list, driven by `/bf-` commands.
- **Printing:** a Bambu MCP turns STLs into sliced, print-ready 3MFs (orientation, supports, raft, multi-plate packing, AMS filament matching), reads printer status and the AMS, and takes camera snapshots. You press Print in Bambu Studio.

## What's inside

| Path | What it is |
|---|---|
| `01`–`04_*.md` | Standing rules: Blender, drawings, materials and fit clearances, Bambu printing |
| `catalog/model library/` | One folder per project (`blend/`, `stl/`, `3mf/`, `references/`) |
| `catalog/hardware inventory/` | Hardware on hand, reservations and shopping list |
| `tools/` | `paths.py` (folders and file names), `inventory.py` (hardware counts), `env.py` (machine-local settings), `bambu_*.py` (the Bambu MCP: build, slice, printer status; `bambu_mcp.py` is the server) |
| `.env.example` | Template for `.env`: where this folder and Blender live on your machine. `.env` itself is gitignored |
| `plugins/` | Notes on the Blender add-ons used (BoltFactory, Extra Mesh Objects) |

## Quick examples

Ask in plain words:

```text
Make a 6 mm × 20 mm peg that press-fits into a matching hole, in PLA Basic.
This drawing is for a friend: a letter board letter set.
Get the shelf bracket ready to print.
```

Or use a command:

```text
/bf-add 50 M4 x 12 socket head screws, reorder at 10
/bf-find m4 socket
/bf-commit shelf bracket
/bf-done shelf bracket
```

## Requirements

- Claude desktop app (Cowork) with this folder connected
- Blender with the Blender MCP add-on running
- Bambu Lab P1S with AMS, Bambu Studio 2.0+, and Python 3.11+ for the Bambu tools (setup in [`USER_GUIDE.md`](USER_GUIDE.md#bambu-printer-setup-once-per-pc))

## Feature Reference

Status: **Done** · **Working on** · **Planned** · **Potential** · **Rejected**

| Feature | Description | Status |
|---|---|---|
| **Request-to-model workflow** | • Requests are saved verbatim to `specifications.md` and expanded into criteria; the part's structure is confirmed before any geometry<br>• Reads dimensioned drawings and whiteboard marks: units, material, exact / slide / press fits by marker colour, heights, angles<br>• Drawing titles are matched to existing projects and parts, typos and abbreviations included<br>• Open questions are asked all at once, with boxed images<br>• After building, measures the part in Blender and passes or fails each criterion; no STL is exported with a failing row | Done |
| **Project and file management** | • `paths.py` creates project folders and names versioned STLs, 3MFs, references and Blender backups<br>• Project index (`projects.csv`) with search and partial-name matching<br>• Cleanup of old STL versions (`/bf-cleanup`) and old reference images | Done |
| **Material-aware tolerances** | • Per-side clearances by filament (PLA Basic / Overture, PLA Matte, PETG Basic) and fit type<br>• Measured values replace the defaults once recorded; a PLA tolerance test set is designed | Done |
| **Hardware inventory** | • CSV-backed inventory with reservations per project, available counts, reorder levels and an automatic shopping list<br>• `/bf-add`, `/bf-restock`, `/bf-find`, `/bf-commit`, `/bf-done`, `/bf-cancel`, `/bf-inventory`<br>• Standard item naming; items can be added from a photo of a package or Lowe's label | Done |
| **Part spec and sketch tool** | • `sketch.py`: a part spec as data, with linked values so one correction updates everything that depends on it<br>• Records caliper readings, checks spec coverage against the criteria, reports fits as arithmetic, and writes the dimensions table | Done |
| **Blender plugin support** | • Notes and usage rules per add-on (BoltFactory, Extra Mesh Objects) | Done |
| **Bambu Studio MCP: building and slicing** | • Converts STLs into real Bambu project 3MFs with P1S presets; the locked settings are enforced by code<br>• Orientation comparison, and supports/raft chosen from the rules in `04_bambu_basics.md`<br>• Plate packing across as many plates as needed (fewest plates or shortest time), one filament per plate by default, filament matched to the loaded AMS roll<br>• Slices through Bambu Studio's command line and reports time, filament and warnings<br>• Retargets MakerWorld files set up for an X1 to the P1S<br>• Opens the sliced file in Bambu Studio 2.x, where you press Print (the firmware refuses unsigned starts) | Done |
| **Printer status and camera** | • Printer state, current job, temperatures and AMS contents over Bambu Cloud<br>• Camera snapshots over the home network | Done |
| **Machine-local configuration** | • `.env` / `env.py` for folder, Blender and printer settings; secrets and tokens stay out of git<br>• Setup check and a test suite for the Bambu tools | Done |
| **Print watch** | • Background camera checks while printing, scored by a local spaghetti detector (Obico); pops up an alert and keeps the picture on a problem<br>• Enable/disable/configure the checks; tune alert thresholds after a few prints | Working on |
| **Bambu MCP: records and tuning** | • Print log and a helper for recording tolerance-test results<br>• *(Potential)* Adjusts speed/strength/quality | Planned |
| **Faster, leaner pre-modelling** | • Fewer questions and fewer tokens between the request and the sketch/modelling steps<br>• Sensible defaults and existing specs fill gaps before anything is asked | Planned |
| **Programmatic workflow steps** | • More of the workflow moved from instructions into tested code: building from the part spec, the confirmation table, export gates, cleanup | Planned |
| **RAG search for inventory and catalog** | • Retrieval over hardware items and project specification sheets, so similar parts, past decisions and on-hand hardware are found by meaning, not exact words | Planned |
| **Local models and decoupling from Claude desktop** | • Local models for scheduled camera monitoring and other routine checks<br>• Run the workflow outside Claude desktop for more configurability and integration compatibility, with lower cost and data kept on the network | Planned |
| **Structured AI decisions (TypeSafe AI)** | • Typed, schema-checked decisions for small judgement calls, e.g. combining detector score, stalled progress and printer error codes into "alert or not"<br>• Evaluation not yet started | Planned |
| **Phone connection** | • Start and follow the modelling/printing workflow from a phone, possibly independent of Claude Dispatch<br>• Send drawings, or photos of the object next to something of known size | Planned |
| **New commands** | • `quick-fix`: optimizes face vertex counts and repairs objects that aren't closed<br>• `verify`: programmatically verifies part specifications<br>• `queue`: queues projects for printing; waits for confirmation when material, plates or nozzles need swapping<br>• `research`: describe a model and it searches online sources in your configured order of preference; if nothing suitable is found or approved, it asks for design specifications and models it itself | Planned |
| **Specialized features** | • Image to carvable 3D template: converts images into objects with topology, e.g. Dremel or router pantograph guides<br>• 3D scan support | Planned |
| **Ease of use** | • Improved user guide<br>• Examples folder + documentation<br>• More centralized configuration files for preferences/integrations/plugins | Planned |
