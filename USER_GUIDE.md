# Project Bonfire — User Guide

How to use Project Bonfire day to day. It's a cheat sheet for people; the project overview is in `README.md`. The numbered files and `PROJECT_INSTRUCTIONS.md` are the full rules Claude follows.

## Before starting

- **Blender** open. The MCP add-on server starts by itself a second after Blender does
  (Preferences → Add-ons → MCP → *Auto Start*, on by default). If it ever doesn't, that
  panel has a **Start MCP Bridge Server** button, and *Online access* must be on in
  Preferences → System.
- **Cowork project** folder attached: `Desktop/Project Bonfire` (the catalog is inside it).
- **First time on a PC:** copy `.env.example` to `.env`, fill in the paths for that
  machine, then run `tools/env.py` → `apply_command()` and do what it prints (it puts
  `BLENDER_PATH` in the user environment so Blender also works with its window closed).
- **From a phone:** *not available yet (Dispatch is still rolling out).* Once it is, use Dispatch and name the project ("In Project Bonfire, …"). The PC must be awake with the Claude desktop app open. Approval prompts time out after 10 minutes.

## Commands

Account-wide slash commands (skills). Type `/bf-` to see them. They run right away, without a confirmation step. Plain words like `done` no longer trigger anything.

| Command | Does |
|---|---|
| `/bf-add <qty> <item>` | Adds a new inventory item and creates its file, e.g. `/bf-add 50 M4 x 12 socket head screws, reorder at 10` |
| `/bf-restock <item or Lowe's code> <qty>` | Adds to an item's count, e.g. `/bf-restock 1234567 25` (adds the item if it's new) |
| `/bf-commit <project>` | Reserves a project's hardware |
| `/bf-done <project>` | Project finished: subtracts its reserved hardware |
| `/bf-cancel <project>` | Releases reserved hardware without using it |
| `/bf-inventory` | Shows reserved hardware and the shopping list |
| `/bf-find <words>` | Searches the inventory, e.g. `/bf-find m4 socket` or `/bf-find low` |
| `/bf-cleanup [project]` | Deletes all but the newest STL of each part (every project, or just one). Permanent |

- The commands find this folder by themselves (connected folder, Desktop, or OneDrive Desktop). If it ever moves somewhere else, set `BONFIRE_HOME` to its path in `.env` (and in the Windows user environment, via `tools/env.py` → `apply_command()`).
- They work best with Blender open (MCP server running). Without it, the inventory commands still work through a copy that's synced back; `/bf-cleanup` needs Blender to delete files.
- **Photos work:** send `/bf-add` or `/bf-restock` with a picture of the package, bin label, or Lowe's part number. The quantity comes from the message, or from the package count.
- `<project>` can be part of the name, e.g. `/bf-done shelf bracket`.
- Quantities can be a number, or `plenty` / `few`.
- `inventory_count.md` and `projects.md` are read-only views, regenerated on every change. To edit data by hand, open the CSV files in the `data/` folders (e.g. in Excel), close them when done, and say so, so the totals get recalculated.

### Command examples

| Type this | What happens |
|---|---|
| `/bf-inventory` | Lists committed hardware and the shopping list |
| `/bf-add 25 #10-24 1 1/2 Phillips head machine bolts, reorder at 10` | Adds `screw_no10-24x1.5in_phillips` with 25 on hand |
| `/bf-add 50 M4 x 12 socket head screws, stainless` | Adds `screw_m4x12_socket_head_stainless` |
| `/bf-add` + photo of a package | Reads the label (Lowe's code first) and adds or restocks it |
| `/bf-restock screw_no10-24x1.5in_phillips 10` | Adds 10 to that item |
| `/bf-restock 1234567 25` | Adds 25 to the item with that Lowe's code |
| `/bf-restock M3 flat washers 12` | Not in the inventory yet, so it gets added |
| `/bf-find 10-24` | Every item with 10-24 in its name |
| `/bf-find m4 socket` | Items matching both words |
| `/bf-find low` | Items at or below their reorder level |
| `/bf-commit shelf bracket` | Reserves the hardware in that project's `specifications.md` |
| `/bf-done shelf bracket` | Subtracts the reserved hardware and logs it in the project's history |
| `/bf-done` | Uses the only project with hardware reserved, or asks which |
| `/bf-cancel shelf bracket` | Releases the reserved hardware without using it |
| `/bf-cleanup tolerance` | Deletes old STL versions in `stl_pla_tolerance_test` only |
| `/bf-cleanup` | Deletes old STL versions in every project |

A partial project name that matches more than one project (e.g. `/bf-commit stl`) makes the command list the matches and ask which; nothing changes until you answer.

## Inventory item names

`<type>_<dimensions>_<specifiers>_<lowes code>`, all lowercase. Full guide: `catalog/hardware inventory/_NAMING_GUIDE.md`.

| Example | Item |
|---|---|
| `screw_m4x12_socket_head_stainless_1234567` | M4 × 12 socket head, stainless, Lowe's #1234567 |
| `bolt_0.25in-20x1in_hex_head_zinc` | 1/4"-20 × 1" hex bolt, zinc |
| `nut_m4_nylon_insert` | M4 nylon lock nut |
| `washer_m4_flat` | M4 flat washer |
| `magnet_d6x3_n52` | 6 × 3 mm disc magnet, N52 |
| `insert_m3x5.7_heat_set_brass` | M3 heat-set insert |

Fractions become decimals (`1/4` → `0.25`). The Lowe's code is left off when there isn't one.

## Drawing reference

| Mark | Meaning |
|---|---|
| Title at the top | Project name (added to that project, or a new one) |
| Title under it | Part to make |
| Title under it + `+` | Edit of an existing part |
| `UN: <unit>` in a corner | Unit for all numbers (default **mm**) |
| `MAT: <material>` in a corner | Filament (default **Bambu PLA Basic**) |
| Line with end ticks + number | Length of the edge beside it |
| Boxed number + arrow | Height of what it points to |
| **Black** marker | Exact dimension |
| **Green** marker | Sliding fit |
| **Red** marker | Press fit |
| Arc in a corner + number° | That angle; otherwise all corners are 90° |

Titles are matched against existing projects and parts first, so a clear abbreviation or typo (e.g. `LBLA` → `letter_board_letters_arial`) resolves to the existing one. If a title could mean more than one thing, or could be an edit rather than something new, you'll be asked.

Anything missing or unclear gets asked about in one message before modelling.

## Default clearances (per side, mm)

| Fit | PLA Basic / Overture | PLA Matte | PETG Basic |
|---|---|---|---|
| Press (red) | 0.05 | 0.10 | 0.10 |
| Slide (green) | 0.20 | 0.20 | 0.25 |

Starting values from online guides. Measured values in `03_materials_tolerances.md` §5 replace them once filled in.

## Where files go

```
Desktop/Project Bonfire/catalog/
├── model library/
│   ├── projects.md                 project list (read-only view)
│   ├── data/projects.csv           project index
│   ├── _TEMPLATE_part.md
│   └── <friend>_stl_<project>/        e.g. alex_stl_letter_board_letters_arial
│       ├── stl/          <part>_1.stl, <part>_2.stl …  (never overwritten; one STL per unique part)
│       ├── blend/        <friend>_<project>.blend
│       ├── 3mf/          when ready to print
│       └── references/
│           ├── <project>_<description>_<n>.png   Claude's previews, renders, reports
│           ├── drawings_images/
│           └── specifications.md   dimensions, quantities, hardware needed
└── hardware inventory/
    ├── inventory_count.md          counts, reservations, shopping list (read-only view)
    ├── data/                       inventory.csv, commitments.csv, shopping_list.csv
    └── screws/ bolts/ nuts/ washers/ magnets/ misc/
```

- Claude's previews, renders and screenshots go in the project's `references/` folder. There's no separate outputs folder.
- Identical parts get one STL; how many to print is the Quantity in `specifications.md` (3 identical pegs → `peg_1.stl`, Quantity 3).
- All names are lowercase with underscores. `<friend>_` is left off when the project isn't for a friend.
- In Blender, collections are `prod` (final parts), `mod` (boolean and modifier helpers), `ref` (images), `back` (backups, e.g. `back_lid_0.0.1`) and `temp` (your scratch models).

## Printing rules in short

- Bambu defaults always. Walls, infill, speed, temperatures and flow are never changed.
- Changed without asking only: supports (normal or tree), build-plate-only supports, raft.
- Orientation: strength first, then largest flat face, then fewest supports. The reason is given in each report.
- Raft: 2 layers when used. AMS: whatever is loaded is read each time.
- Bambu Studio (once its MCP is built, see `BAMBU_MCP_PLAN.md`): supports, raft, orienting, arranging the plate and slicing happen without asking; sliced files go in `3mf/`. **Starting a print always needs your yes.**

## Still to fill in

- `01_blender_basics.md`: backup version numbering (**[Confirm]**)
- `02_drawing_rules.md` §F: diameters, holes, fillets, views, reference points, photos
- `03_materials_tolerances.md`: measured results
- `04_bambu_basics.md`: other support settings, splitting and assembly, minimum sizes
- `PROJECT_INSTRUCTIONS.md`: programs not to use
