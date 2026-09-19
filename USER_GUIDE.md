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
- **Bambu printer:** one-time setup per PC in [Bambu printer setup](#bambu-printer-setup-once-per-pc) below.
- **From a phone:** *not available yet (Dispatch is still rolling out).* Once it is, use Dispatch and name the project ("In Project Bonfire, …"). The PC must be awake with the Claude desktop app open. Approval prompts time out after 10 minutes.

## Bambu printer setup (once per PC)

Lets Claude build, slice and check print files, and read the printer's status. Paths below
are examples: use wherever your Project Bonfire folder and Python actually are.

1. **Bambu Studio 2.0 or newer.** Install from bambulab.com/download (or Help → Check for
   updates) and sign in. Older versions (1.9.x) send the job, and Handy even lists it as
   "printing", but the printer ignores it.
2. **Python packages.** In PowerShell, from the Project Bonfire folder:
   ```powershell
   python -m pip install paho-mqtt curl_cffi "mcp[cli]<2"
   ```
   Keep `mcp` below version 2; version 2 renamed parts of it and the server isn't tested on it.
3. **Sign in to Bambu Cloud.**
   ```powershell
   python tools\bambu_cloud.py login <your Bambu account email>
   ```
   Type the password (and the emailed or 2FA code, if asked) in the terminal, never in a
   chat. The sign-in is saved in `tools/bambu_cloud.local.json` (git-ignored) and lasts about
   3 months; run `login` again when status says it has run out.
4. **Save the preset template.** In Bambu Studio, open any project with the P1S, 0.4 nozzle and
   your usual process selected, then **Save Project As** → `tools\bambu_template.3mf`. Every
   file Claude builds copies its untouched settings from this, so they match Studio's defaults.
   It's git-ignored (Studio writes your Bambu account ID into it), so each PC saves its own.
   Save it again after a major Studio update.
5. **Register the MCP server** so Claude can use the tools. In the Claude app:
   **Settings → Developer → Edit Config**, and add `"mcpServers"` at the **top level** of
   the file, next to the other top-level keys and **not inside `"preferences"`**:
   ```json
   {
     "mcpServers": {
       "bambu": {
         "command": "C:\\Users\\<you>\\AppData\\Local\\Programs\\Python\\Python311\\python.exe",
         "args": ["C:\\Users\\<you>\\Desktop\\Project Bonfire\\tools\\bambu_mcp.py"],
         "env": {"BONFIRE_HOME": "C:\\Users\\<you>\\Desktop\\Project Bonfire"}
       }
     },
     "preferences": { ...leave as it was... }
   }
   ```
   `py -0p` lists the full path to each installed `python.exe`. Save, quit Claude from the
   system tray (not just the window), and reopen it. **Settings → Developer** should show
   `bambu` as *running*. A Cowork task that was already open may need a new task to see it.
6. **Check it.**
   ```powershell
   python tools\test_bambu.py
   python -c "import runpy; m=runpy.run_path('tools/bambu_mcp.py'); print(m['bambu_setup_check']())"
   python tools\bambu_cloud.py status
   ```
   The tests end with `all checks passed`, the setup check with `"ok": true` and an empty
   `missing` list, and status shows the printer and what's in each AMS slot.
7. **On the printer** (Bambu Studio → Device tab → **AMS Settings**):
   - **Insertion update** and **Update remaining capacity** on. Bambu RFID spools then
     report roughly how much is left (it's an estimate); third-party spools never do.
   - **AMS filament backup** on, to switch to a second roll when one runs out. Both rolls must
     be set to the same filament and colour.
   - For third-party rolls, set the slot to the brand's own preset (e.g. *Overture PLA*), not
     *Generic PLA*, so the tools can tell what's loaded.

8. **Print watch (optional).** While a print runs, takes a camera picture every 5 minutes, has
   a failure detector look at it, and pops up a window on this PC if something looks wrong.
   The detector is Obico's open-source spaghetti detector, running locally in Docker: free, no
   account, nothing leaves the PC.
   1. Install **Docker Desktop** (docker.com), start it, and in its Settings → General tick
      *Start Docker Desktop when you sign in*.
   2. Optional: put a long random string in `.env` as `OBICO_ML_TOKEN=` so only the watch can
      use the detector.
   3. From the Project Bonfire folder:
      ```powershell
      python tools\bambu_watch.py obico up     # first time: downloads ~1-2 GB, a few minutes
      python tools\bambu_camera.py snapshot    # a picture to test with
      python tools\bambu_watch.py obico test   # the detector scores it (0 = nothing wrong)
      python tools\bambu_watch.py install      # start the watch hidden with Windows, and now
      python tools\bambu_watch.py status       # installed? running? detector answering?
      ```
   The watch sleeps while the printer is idle. It can't pause the print itself (the firmware
   refuses), so the pop-up says to pause in Studio's Device tab, Handy or on the screen, and
   *Yes* opens the picture and Studio. Pictures go to `tools\camera_snapshots\` (git-ignored),
   problem pictures to its `problems\` folder, and a log to `watch.log` there. Timing and
   sensitivity: `camera_watch` in `tools\bambu_config.json` (`interval_min`, `alert_score`,
   `spike_score`; lower scores = more sensitive).

Optional, in `.env` (see `.env.example`): `BAMBU_PRINTER_SERIAL` if the account has more
than one printer, `BAMBU_PRINTER_IP` if the printer isn't found on the network by itself,
and `BAMBU_STUDIO_PATH` if Studio isn't in the usual place.

## Printing

- Ask in plain words, e.g. *"Get the shelf bracket ready to print."* Claude picks the
  orientation, supports and raft (within `04_bambu_basics.md`), lays out the plate, slices,
  and reports print time, filament per slot and anything Studio warned about.
- **Starting:** the file opens in Bambu Studio and **you press Print**. The P1S firmware
  (2025 on) only accepts start, pause, resume and stop commands signed by Bambu's own apps,
  so the tools can't send them.
- **Pause / resume / stop:** Studio's Device tab, the Handy app, or the printer's screen.
- **Status and AMS contents** can be asked for any time.
- **MakerWorld files set up for an X1:** ask to retarget them to the P1S. A copy is made
  with the P1S's machine settings; the original isn't changed.
- **Before committing:** 3MFs saved from Studio carry your Bambu account ID
  (`DesignerUserId` in `3D/3dmodel.model`). Ask Claude to blank it, or leave those 3MFs out.

### When something's off

| What you see | Why / fix |
|---|---|
| Studio says it sent, Handy shows "printing", printer does nothing | Studio older than 2.0. Update it |
| `err_code 84033543` / "MQTT command verification failed" | The firmware refusing an unsigned command. Use Studio, Handy or the screen |
| Status says the sign-in ran out | `python tools\bambu_cloud.py login <email>` again |
| `bambu` missing from Settings → Developer | `"mcpServers"` isn't at the top level of the config, or a comma/brace is off |
| `No module named 'mcp.server.fastmcp'` | `mcp` 2.x installed: `python -m pip install "mcp[cli]<2"` |
| Setup check says Studio is too old right after updating | Run it again; if it persists, check `bambu-studio.exe` → Properties → Details |

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
- Bambu Studio: supports, raft, orienting, arranging the plate and slicing happen without asking; sliced files go in `3mf/`. **Prints are started by you**, with Studio's Print button.

## Still to fill in

- `01_blender_basics.md`: backup version numbering (**[Confirm]**)
- `02_drawing_rules.md` §F: diameters, holes, fillets, views, reference points, photos
- `03_materials_tolerances.md`: measured results
- `04_bambu_basics.md`: other support settings, splitting and assembly, minimum sizes
- `PROJECT_INSTRUCTIONS.md`: programs not to use
