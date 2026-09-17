# 01 — Blender Basics

Standing rules for all modelling work in this project. Follow them without asking.
**Status key:** ✅ = decided · **[Fill out]** = not decided yet (ask when it matters, and suggest adding the answer here) · **[Confirm]** = interpretation of notes, still to be confirmed.

---

## 1. Units ✅

- Always use metric. **All dimensions are in mm** unless a drawing's `UN:` marker says otherwise (see `02_drawing_rules.md`).
- Scene setup: Scene Properties → Units → Unit System **Metric**, Unit Scale **0.001**, Length **Millimeters**. Then 1 Blender unit = 1 mm.
- If a file isn't set up this way, set it before modelling and say so.
- Report all dimensions in mm.

## 2. Projects, folders, and files ✅

### Project names

- **One project = one drawing.** How a drawing names its project and parts: see `02_drawing_rules.md` → *Titles*.
- **All project, folder, and file names are lowercase, with underscores instead of spaces.** Convert names given in any other form.
- **No name given:** if the project name can be worked out from the request, use it and state it in the report. Otherwise ask.
- **For a friend:** when a project is requested for a friend (e.g. "this is for a friend") without naming them, **ask for the friend's name**. Start the project name with it: `<friend>_<project name>`, e.g. `alex_letter_board_letters_arial`.

### Folders

- **Every project lives in** `Desktop/Project Bonfire/catalog/model library/`.
- **Project folder name:** `<friend>_<file type>_<project name>`. Leave out `<friend>_` when the project isn't for a friend. The file type is the main export, usually `stl`.
  - Example for a friend: `alex_stl_letter_board_letters_arial`
  - Example not for a friend: `stl_shelf_bracket`
- **Inside the project folder:**

```
Desktop/Project Bonfire/catalog/model library/
└── alex_stl_letter_board_letters_arial/
    ├── stl/                    STL exports
    ├── blend/                  <project name>.blend and its .blend1 backup
    ├── 3mf/                    only when getting parts ready to print
    └── references/
        ├── <project name>_<description>_<n>.png   Claude's outputs: previews, renders, screenshots, reports
        ├── drawings_images/    only when there are drawings, photos, or images
        └── specifications.md   only when there are part specs (from _TEMPLATE_part.md)
```

- Save any drawings or photos provided for a project into `references/drawings_images/`.
- **Claude's own outputs** (previews, renders, screenshots, comparison images, reports) go in that project's `references/` folder, named `<project name>_<description>_<n>.<ext>` (e.g. `pla_tolerance_test_preview_1.png`). Get the path from `paths.py` → `next_reference_path(root, "<project name> <description>", ext)`; never overwrite.
- **Never create an output folder anywhere else** in Project Bonfire (no `Claude outputs/`, `output/`, `temp/` …). Scratch files stay outside the folder. Output that isn't tied to a project is shown in the chat only; ask if it should be saved.
- **Create folders and export names with the tool, not by hand:** `Project Bonfire/tools/paths.py` (see `PROJECT_INSTRUCTIONS.md` → *Tools*).

### Files

| File | Name | Where | When |
|---|---|---|---|
| Blender file | `<project name>.blend` (no file type), e.g. `alex_letter_board_letters_arial.blend`. One per project; always edit this same file. | `blend/` | Save automatically when a task is finished. |
| STL (one per unique part) | `<object name>_<n>.stl`: first export `_1`, then `_2`, `_3`, … Identical copies share one STL (see section 3). | `stl/` | **Only after the models are confirmed complete.** Every re-export gets the next number; never overwrite an earlier STL. |
| 3MF | Same naming as the STL | `3mf/` | Only when requested to get it ready to print (see `04_bambu_basics.md`). |
| Claude's outputs | `<project name>_<description>_<n>.<ext>`, e.g. `pla_tolerance_test_preview_1.png` | `references/` | Whenever a preview, render, screenshot or report is made for the project. Never overwritten. |
| Specifications | `specifications.md`, copied from `model library/_TEMPLATE_part.md` | `references/` | When the project has specs worth recording (dimensions, fits, quantities). |

- `<object name>` is the object's name without its collection prefix (see section 4), e.g. object `prod_lid` → `lid_1.stl`.
- **Quantities:** `specifications.md` lists how many of each part the whole project needs. Use `n` for independent (modular) parts like letters. The number of identical copies lives **only** in the Quantity column, never in extra objects or files.
- **Old versions:** `/bf-cleanup` deletes every STL except the newest version of each part.

## 3. Parts ✅

- Every separate part is its own object and gets its own STL.
- **Identical parts are modelled once.** When a request asks for several copies of the same part (e.g. "3 identical 20 mm pegs"), make **one** object and **one** STL, and put the count in `specifications.md` → *Quantities*.
  - Example: 3 identical pegs → object `prod_peg`, file `peg_1.stl`, Quantity `3`. Not `prod_peg_a`/`_b`/`_c`, and not "1 each".
  - Don't letter or number copies. Make separate objects only when the parts differ in some way (size, fit, label, hole, …); name those by what differs, e.g. `prod_block_press`, `prod_block_snug`.
  - Copies for printing are added at the 3MF stage (see `04_bambu_basics.md` → section 4).
- Each part must be a single closed (manifold) solid with no stray internal faces, loose pieces, or holes in the surface. Check before export.
- **Before export, orient each part for printing** following `04_bambu_basics.md` → *Print orientation*.
- If a part is too big for the printer or needs splitting, follow `04_bambu_basics.md` → *Splitting parts and assembly*.

## 4. Scene organization and naming ✅

- **Keep original geometry.** Never delete source objects after booleans or other destructive edits. Hide them in the right collection instead.
- Create these collections as needed. **All names are lowercase, with underscores instead of spaces.**

| Collection | Holds | Object name pattern | Example |
|---|---|---|---|
| `prod` | Final objects that become STLs | `prod_<object name>` | `prod_lid` |
| `mod` | Working objects for modifiers and booleans | `mod_<operation>_<object name>` | `mod_diff_lid` |
| `ref` | Reference images | `ref_<object name>` | `ref_lid_sketch` |
| `back` | Backups made before big or hard-to-undo changes | `back_<object name>_<version id>` (see below) | `back_lid_0.0.1` |
| `temp` | Temporary models added by hand | `temp_<object name>` | `temp_test_block` |

**Standard operation words for `mod_` names:**

| Word | Use for |
|---|---|
| `union` | Boolean union (adding a shape) |
| `diff` | Boolean difference (cutting a shape away) |
| `inter` | Boolean intersect (keeping only the overlap) |
| `join` | Merging objects into one (Ctrl+J) |
| `cut` | Splitting or bisecting with a plane |
| `clip` | Trimming a shape to another shape's outline |
| `mirror` | Mirror modifier or mirrored copy |
| `array` | Array or repeated copies |
| `solid` | Solidify or thickening |
| `bevel` | Bevel, chamfer, or fillet |
| `subsurf` | Subdivision Surface: smoothing, or adding detail to rounded or detailed models |

Add new words here when a new operation comes up.

### Backups (`back_`)

- **Before any big or hard-to-undo change:** copy the object, move the copy to the `back` collection, and rename the copy `back_<object name>_<version id>`.
- The version id has the form `x.y.z`. Starting from no backups (`0.0.0`):

| Change | Bump | First backup example |
|---|---|---|
| Big change | `z` + 1 | `back_lid_0.0.1` |
| Hard-to-undo change | `y` + 1 | `back_lid_0.1.0` |
| Version id already taken | `x` + 1 | From `0.0.1`, a hard-to-undo change gives `0.1.1`. If `0.1.1` already exists, use `1.1.1`. |

- **[Confirm]** Your notes said "hard-to-undo: x + 1" and "big changes: y + 1", but the examples bump the middle and last digits. This table follows the examples.

## 5. Reporting after a task ✅

Keep it short. Include:

- **File:** `<project>/<file name>`
- **Final dimensions**, measured from the model, as confirmation
- **Assumptions made**
- **Changes** (for edits)
- **Orientation reasoning:** which face is on the bed, and why (strength, largest flat face, or fewer supports)
