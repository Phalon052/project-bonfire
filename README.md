# Project Bonfire

> [!WARNING]
> **Pre-1.0: under rapid change.** Project Bonfire is being actively reworked and reconfigured. Expect major refactors to make it easier to use, use fewer tokens, simplify the folder structure, and add centralized configuration files. Example projects are on the way too.
> It will be considered stable at the **1.0 release**, when this notice is removed.

**How it works:** see [`USER_GUIDE.md`](USER_GUIDE.md) for setup, commands, drawing marks and folder layout. Claude's rules are in [`PROJECT_INSTRUCTIONS.md`](PROJECT_INSTRUCTIONS.md) and the numbered `0x_*.md` files.

---

## Current State
A Claude (Cowork) workspace for designing 3D-printable parts in **Blender** and printing them on a **Bambu Lab P1S**.

1. Hand Claude a dimensioned sketch or a request, and it models the part(s) for a given project.
2. Automatically sets up file storage and naming conventions.
3. Adjusts tolerances based on the filament brand, filament type and use case.
4. Exports versioned STLs.
5. Commands for:
    1. Project administration
    2. Included hardware inventory management
    3. Prototyping with 3D-printed hardware before purchasing
6. Hosts a hardware database that tracks your inventory, commits hardware to current/queued projects, and notifies you when you're running short on key components.
7. Blender plugin support, plus plugin-specific tool usage and prompting.

## What's inside

| Path | What it is |
|---|---|
| `01`–`04_*.md` | Standing rules: Blender, drawings, materials and fit clearances, Bambu printing |
| `catalog/model library/` | One folder per project (`blend/`, `stl/`, `3mf/`, `references/`) |
| `catalog/hardware inventory/` | Hardware on hand, reservations and shopping list |
| `tools/` | `paths.py` (folders and file names), `inventory.py` (hardware counts) |
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
- Bambu Lab P1S with AMS (Bambu Studio MCP in progress; see the roadmap below)

## Roadmap

Status: **Done** · **Working on** · **Planned** · **Potential** · **Rejected**

| Feature | Planned Usage | Status |
|---|---|---|
| **New commands** | • `quick-fix`: optimizes face vertex counts and repairs objects that aren't closed<br>• `verify`: programmatically verifies part specifications<br>• `queue`: queues projects for printing; waits for confirmation when material, plates or nozzles need swapping<br>• `research`: describe a model and it searches online sources in your configured order of preference; if nothing suitable is found or approved, it asks for design specifications and models it itself | Planned |
| **Bambu Studio MCP integration** | • Converts STLs into print-ready 3MFs<br>• Configures settings to maximize strength and reduce material use:<br>&emsp;◦ Finds and applies the best orientation for how the part will be used<br>&emsp;◦ Generates supports/rafts based on your configuration and printer<br>&emsp;◦ *(Potential)* Adjusts speed/strength/quality<br>• Slices and packs objects for optimal print time and plate count<br>• Enable/disable/configure scheduled checks of the P1S camera | Working on |
| **Remote usage** | • Enable Claude Dispatch once it's available for my account, or design/integrate remote access functionality<br>• Send drawings, or snap photos of the desired object next to an object of known size, to kick off the modelling/printing workflow | Potential |
| **Closed network mode / refactor** | • Decouple from Claude desktop for more configurability and integration compatibility<br>• Run with local models for security and cost optimization | Potential |
| **Specialized features** | • Image to carvable 3D template: converts images into objects with topology, e.g. Dremel or router pantograph guides<br>• 3D scan support | Planned |
| **Ease of use** | • Improved user guide<br>• Examples folder + documentation<br>• More centralized configuration files for preferences/integrations/plugins | Planned |
