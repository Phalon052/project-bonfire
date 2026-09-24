# Project Bonfire — Project Instructions

> Paste the section below into the Cowork project's **Instructions** field.
> The reference files in this folder hold the details; the instructions only say when to read them.

---

This project is for designing 3D-printable parts, mainly in Blender (connected through the Blender MCP), and printing them on a Bambu Lab P1S.

**Read before working.** The reference files are in this project's folder. The catalog and all project folders are in its `catalog` subfolder.

| When | Read |
|---|---|
| Any modelling task | `01_blender_basics.md` |
| **Before creating a single object in Blender** | `01_blender_basics.md` → **section 0, *Before Blender*.** The request is saved verbatim into the project's `specifications.md` and expanded into criteria, and the structure of the part is confirmed, before any geometry exists |
| **Reading any dimension** off a photo, drawing or request — what *thick*, *tall*, *wide*, *horizontal*, *vertical* mean | `02_drawing_rules.md` → **A00, *Viewing angle and vocabulary*.** *thick / tall / deep* are always Z; every image is a top-down view unless obviously angled or labelled with a named view |
| **Anything is unclear and a question is needed** | `02_drawing_rules.md` → **A01, *Asking for clarification*.** Ask with a boxed image, never with a menu of interpretations of the geometry |
| A drawing, sketch, whiteboard photo, or photo with a ruler is provided | `02_drawing_rules.md` |
| A photo of a part on the mat with the four ArUco markers | `tools/photo.py` → `rectify()` first, then measure off the rectified picture (USER_GUIDE *Measuring from photos*) |
| Anything that has to fit, slide, press, rotate, or thread | `03_materials_tolerances.md` → **§1 first**: what a clearance is (a gap per mating surface, applied by offsetting the socket, never by scaling), which side and which surfaces get it, and the untested cases to flag. Then §3 for the value |
| Printing: slicer settings, supports, orientation, splitting parts, getting ready to print | `04_bambu_basics.md` |
| Using a Blender add-on/extension | `plugins/README.md`, then `plugins/<plugin>.md` if one exists |
| Designing anything that could reuse a known part | Search `catalog/model library/data/projects.csv` first (`paths.py` → `find_projects()`), then read the matching project's `references/specifications.md` |
| Designing around hardware (screws, bolts, nuts, washers, magnets, inserts) | Search `catalog/hardware inventory/data/inventory.csv` (`inventory.py` → `search()`), then the item files for details; `_NAMING_GUIDE.md` for item names. Prefer items on hand. List the hardware in the project's `specifications.md`, and say if anything is short (add it to the shopping list) |

`development/TODO.md` is the project's open-work list (it lives in `development/`, which is git-ignored). Check it when asked what's left or what to work on next. When an item is finished, check it off; when new work comes up or is deferred, add it under the right heading. Update its *Last updated* date on each change.

`USER_GUIDE.md` in this folder is the full how-to for people, not rules. When commands, drawing marks, clearances, or folder rules change, update it to match. `README.md` is a short public overview; update it only when the project's scope or headline commands change.

**Data files: CSV for lookups, Markdown views for people**

- Lookup data lives in CSV files. Read and search these (or use the tools); they are the only source of truth:
  - `catalog/hardware inventory/data/inventory.csv`: items, name parts (type, dimensions, specifiers, Lowe's code), counts, committed, available, reorder level
  - `catalog/hardware inventory/data/commitments.csv`: hardware reserved for projects, with status
  - `catalog/hardware inventory/data/shopping_list.csv`: items to buy (`source` = auto or manual)
  - `catalog/model library/data/projects.csv`: project index (folder, friend, parts and latest export versions, specs, drawings, hardware)
- `catalog/hardware inventory/inventory_count.md` and `catalog/model library/projects.md` are **generated views for people**. Never read them for lookups and never edit them; the tools overwrite them on every change.
- Change the CSVs only through the tools. If a CSV was edited by hand (e.g. in Excel), run `inventory.py` → `refresh()` or `paths.py` → `index_projects()` before using it.
- After creating a project, exporting, or editing `specifications.md`, run `paths.py` → `index_projects()` so the index stays current.

**How to work**

- Follow the rules in those files without asking for confirmation. They are standing decisions.
- Ask before building when something needed is missing, unreadable, or contradictory (a dimension, a unit, a fit type, which side is which). Ask all open questions at once, not one at a time. **Ask with a boxed image, and never by offering a menu of readings of the geometry** (`02_drawing_rules.md` → A01).
- **Understanding the structure is a separate job from collecting the numbers.** Having every dimension does not mean the part is understood — a wrong mental model parses all the numbers happily. Before modelling, state in plain words what the part is and what each feature is *for*, and get a yes.
- If an assumption is small and covered by a default in these files, use the default and state it in the summary instead of asking.
- Save previews, renders, screenshots and other outputs in the project's `references/` folder (`paths.py` → `next_reference_path()`). Never create a separate output folder (e.g. `Claude outputs/`); see `01_blender_basics.md` → section 2.
- After building, measure the result in Blender and report the real dimensions. Do not report intended dimensions. **Measuring is not confirming:** the report must compare every measurement against the project's *Expanded criteria*, row for row, with a pass or fail on each (`01_blender_basics.md` → section 5). A row also fails when the feature cannot do what the requirement says it is for, even if the number is right. No STL is exported for a part with a failing row.
- When a correction should apply every time, offer to add it to the right reference file.
- When a part is proven, offer to add it to the model library using `_TEMPLATE_part.md`.
- Inventory counts change only through the `/bf-` commands below or when a project is made ready to print (see `04_bambu_basics.md`). Never edit counts otherwise unless requested.

**Priority when files disagree:** the current request → `02_drawing_rules.md` (for what a drawing means) → `03_materials_tolerances.md` measured values → `03` default values → `04_bambu_basics.md` → `01_blender_basics.md`.

**Tools**

- Each program used in this project gets its own `<tool>_basics.md` file with its rules. Current files: Blender → `01_blender_basics.md`, Bambu Studio → `04_bambu_basics.md`.
- When a new tool is added, create its basics file from the same pattern (✅ decided rules, **[Fill out]** open questions) before relying on it.
- [Fill out] Any programs not to use in this project.
- **`tools/paths.py`**: use it for project folders, export file names, and backup names instead of working them out by hand. Run it inside Blender through the Blender MCP:

```python
import os, runpy
BONFIRE = os.environ.get("BONFIRE_HOME") or os.path.expanduser(r"~\Desktop\Project Bonfire")
bp = runpy.run_path(os.path.join(BONFIRE, "tools", "paths.py"))
p = bp["create_project"]("shelf bracket", friend=None, ftype="stl", drawings=False, specs=False)
bp["next_export_path"](p["root"], "prod_lid")          # stl/lid_<next n>.stl
bp["next_export_path"](p["root"], "prod_lid", "3mf")   # 3mf/lid_<next n>.3mf
bp["next_reference_path"](p["root"], "shelf bracket preview", "png")  # references/shelf_bracket_preview_<next n>.png
bp["next_backup_name"]("lid", "big", [o.name for o in bpy.data.objects])
bp["match_title"]("LB letters")                               # drawing title vs existing projects
bp["match_title"]("lid hinge", "part", [o.name for o in bpy.data.objects])
bp["find_projects"]("bracket")                                # search the project index
bp["index_projects"]()                                        # rebuild projects.csv and projects.md
bp["resolve_project"]("shelf bracket")                         # folder from a partial name
bp["cleanup_exports"]("shelf bracket", dry_run=True)          # old STL versions (preview)
```

  Set `drawings=True` when there are drawings or photos, and `specs=True` when there are specs. It never overwrites existing files.
- **`tools/export_gate.py`**: the only way an STL is exported. `export_part("prod_lid", "shelf bracket")` checks the part with 3D Print Toolbox and exports it to `stl/<name>_<n>.stl` only if it passes (non-manifold, flipped normals, self-intersections, degenerate geometry and loose pieces block the export; thin walls, overhangs and sharp edges are warnings). `check_part("prod_lid")` checks without exporting. Runs inside Blender the same way as `paths.py`. Needs the 3D Print Toolbox extension (`plugins/print3d_toolbox.md`).
- **`tools/gear.py`**: involute spur gears for anything that must mesh (never the Extra Mesh Objects add-on). `make_gear("prod_gear", module=2, teeth=20, thickness=8, axle=12, material="Overture PLA")` takes the backlash and the centre-hole clearance from `03` §3 and refuses a blank (untested) material; `make_pair(...)` places two gears at the exact centre distance, meshed; `check_mesh(a, b)` confirms no overlap through one tooth; `measure_gear(obj)` gives the real dimensions for the confirmation table. Runs inside Blender the same way as `paths.py`; `tools/test_gear.py` tests the maths without Blender.
- **`tools/bambu_modes.py`**: the print watch's monitoring modes. `write_config(three_mf, mode, **overrides)` saves `<name>.monitor.json` beside a 3MF; the watch finds it from the job name. Modes: default, early, complex, tall, overnight, quick, watch_only (`04_bambu_basics.md` §4 says which to pick). Also the free checks that need no picture (HMS codes, a stalled layer count, a cold nozzle) and the project's `Error Report/` entries. MCP: `monitor_mode`.
- **`tools/bambu_studio_ui.py`**: presses Bambu Studio's own Stop button (the firmware refuses stop/pause from here), by matching a picture of the button the person pointed at once. Refuses unless it sees exactly one clear match. MCP: `studio_stop` (needs confirm=true, and asking first). Stopping a print is never done on Claude's own initiative except by a mode that acts first (overnight) or a confirmed review.
- **`tools/photo.py`**: measuring from photos. `rectify(photo, part_height_mm=...)` finds the four ArUco markers (layout in `tools/photo_markers.json`), fits a homography and writes a straight-down `_rectified.png` (10 px/mm), a `_rectified_grid.png` and a `_rectified.json` beside the photo. `measure(report_json, points, "rectified" | "photo")` turns pixels into mm. Read `fit_rms_mm` and `warnings` before using any number; sizes are true on the marker plane only (`plane_mm`), so a part's top face above it reads big. Same tools in the Bambu MCP: `photo_rectify`, `photo_measure`, `photo_layout`, `photo_marker_sheet`.
- **`tools/inventory.py`**: use it for every inventory change (add, restock, rename, commit, complete, cancel, refresh, status). `search(words, item_type, low_only)` is the fast lookup; `find_item(name or Lowe's code)` finds one exact item. Each change updates the CSVs, recalculates committed / available and the automatic shopping-list rows, regenerates `inventory_count.md`, and returns a short report to include in the reply.

```python
inv = runpy.run_path(os.path.join(BONFIRE, "tools", "inventory.py"))
print(inv["commit"]("stl_shelf_bracket"))      # hardware from the project's specifications.md
print(inv["complete"]("stl_shelf_bracket"))
print(inv["search"]("m4 socket"))                # fast lookup
```

**Commands**

Commands are account-wide skills, all starting with `bf-` (e.g. `/bf-done`). Each skill finds this folder and runs the matching tool itself. Plain words at the start of a message (`done`, `add`, …) are **not** commands anymore; treat them as normal requests. When a `/bf-` command runs, the command is the approval, so don't ask for confirmation. Reply with the tool's report only.

| Command | What it does | Tool call |
|---|---|---|
| `/bf-done <project>` | The project is finished and its hardware was used. Subtracts the committed hardware from Quantity and marks the commitment complete. Also adds a history row to the project's `specifications.md`. | `inventory.py` → `complete(project)` |
| `/bf-cancel <project>` | Releases the project's hardware without using it. | `inventory.py` → `cancel(project)` |
| `/bf-commit <project>` | Reserves the project's hardware now, without preparing it for printing. | `inventory.py` → `commit(project)` |
| `/bf-add <qty> <item>` | Adds a new item: a row in `inventory.csv` and an item file in its type folder, filled with any details given. If the item already exists (same name or Lowe's code), adds to its count instead. Example: `/bf-add 50 M4 x 12 socket head screws, reorder at 10`. | `inventory.py` → `add_item(name, qty=..., reorder_at=..., details=...)` |
| `/bf-restock <item or Lowe's code> <qty>` | Adds to an existing item's count, e.g. `/bf-restock 1234567 25`. If the item isn't in the inventory yet, add it instead. | `inventory.py` → `restock(item, qty)` |
| `/bf-inventory` | Shows what's committed and the shopping list. | `inventory.py` → `status()` |
| `/bf-find <words>` | Searches the inventory, e.g. `/bf-find m4 socket`, `/bf-find low` (items at reorder level). | `inventory.py` → `search(words)` / `search(low_only=True)` |
| `/bf-cleanup [project]` | Deletes every STL except the newest version of each part (all projects, or only the one named). Permanent. | `paths.py` → `cleanup_exports(project)` |

- **Item names:** always convert the item described into its name from `catalog/hardware inventory/_NAMING_GUIDE.md` (e.g. "M4 x 12 socket head screws" → `screw_m4x12_socket_head`) before calling the tool. The tool rejects names that don't follow the guide.
- **Photos:** `/bf-add` or `/bf-restock` may come with a photo of a package, bin label, or Lowe's part number instead of a typed item. Read the label, build the name with the guide, and follow its *Adding from a photo* steps: look up by Lowe's code first, restock if found, otherwise add it with details from the label. Quantity comes from the message, else the package count; ask only for loose hardware with no count, or for any part of the label that can't be read.
- A photo whose Lowe's code matches an item saved without a code adds the code to that item's name automatically (the tool renames its file and project references).
- `<project>` can be part of the folder name (e.g. `/bf-done shelf bracket`). Match it with `paths.py` → `resolve_project()`, and ask only if more than one matches.
- `/bf-done` with no project: if exactly one project has hardware committed, use it; otherwise ask which.
- If a CSV in `data/` was edited by hand, run `refresh()` before the next command.

