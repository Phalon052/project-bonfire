# 01 — Blender Basics

Standing rules for all modelling work in this project. Follow them without asking.
**Status key:** ✅ = decided · **[Fill out]** = not decided yet (ask when it matters, and suggest adding the answer here) · **[Confirm]** = interpretation of notes, still to be confirmed.

---

## 0. Before Blender ✅

**Nothing is created in Blender until every step below is done, in order.** These steps exist to catch
a wrong understanding of the *structure* of a part. Collecting every dimension will not catch it —
a wrong mental model parses all the numbers happily and builds the wrong object.

1. **Save the request, verbatim.** Create the project (`paths.py` → `create_project`) and copy the
   user's request into `references/specifications.md` → *Original prompt request*, exactly as written:
   no paraphrase, no reordering, no tidying of typos or spelling. Later messages that add or change a
   requirement are appended in order, each noted with when it arrived. This file gets read as a
   reference while modelling, so it has to carry the original words, not a summary of them.
2. **Save the images.** Every supplied photo, drawing or screenshot goes into
   `references/drawings_images/` before anything else. Do it now — it is easy to reach the end of a
   build and find the reference was never saved.
3. **Read the reference files** the task needs (`PROJECT_INSTRUCTIONS.md` → *Read before working*).
   Always `02_drawing_rules.md` → A00 when a photo, drawing or written dimension is involved.
4. **Census the reference** (`02_drawing_rules.md` → A02). Enumerate every distinct region, number
   them on the image, and give each one a *why*. Unconditional for any part built from a photo or
   drawing.
5. **Expand the request into criteria.** Fill *Expanded criteria* in `specifications.md`: one row per
   requirement, and **every number in the request gets a row**. Each row records the quoted words, the
   feature, the **axis** and the **datum it is measured from** (`02_drawing_rules.md` → A00), the
   value, what it is for, and the source — `stated` / `derived` / `measured` / `assumed`. Classify
   every limiting instruction while doing this (`02_drawing_rules.md` → A03).
6. **Fill the mates and motion table.** Every feature that touches something else gets a row. This is
   where a requirement's *purpose* becomes a dimension, and it catches what a list of numbers cannot.

   | Feature | Mates with | Fixed or moving | Range of movement | What that constrains |
   |---|---|---|---|---|

   Worked example — a levelling set screw: mates with a threaded hole in the plastic → **moving** →
   range is the full levelling adjustment → therefore the hole must be *under* the screw's major
   diameter, **and** the head needs somewhere to sit at both ends of its travel. Both requirements
   fall out of one row. An empty *range of movement* cell is an unfinished row, and unlike a
   paragraph it is visibly unfinished.

7. **Resolve the gaps before any of them becomes a question.** A gap is a blank *why* from the census,
   an `assumed` row, or a missing value. **Most gaps are resolvable.** Work the ladder in order and
   only what survives every rung is asked:

   1. **Vocabulary** — is it unclear only because the axis or datum was not read per A00, or because
      the request's own wording elsewhere already defines the term? Re-read first.
   2. **Neighbouring geometry** — is the value fixed by the features around it? A wall between two
      known faces has a known thickness; a bay between two dimensioned features has a known width.
   3. **Symmetry and repetition** — does the reference show the same feature elsewhere with a value?
   4. **The mating part** — is it set by what it fits? A threaded hole is set by its screw; a board in
      a recess is set by the recess.
   5. **A standard** — a thread, bearing, magnet, fastener or stock size. Identify it and cite the
      tolerance band that makes the identification safe (3.88 mm major sits inside the M4×0.7 class 6g
      band of 3.838–3.978; #8-32 would be 4.166 and M5 4.8 — so 3.88 *is* M4, it is not a choice).
   6. **A project default** — `03_materials_tolerances.md` clearances, `04_bambu_basics.md` print
      settings, `01` naming and orientation rules.
   7. **Consequence test** — still no value? Ask what breaks if it is wrong. Cosmetic, small
      consequence → state an assumption and carry on. Decides whether the part **fits, mates or
      functions** → it is a question, every time, however small the number.

   **Everything resolved at rungs 2–6 is written into the criteria table as `derived`, with the
   derivation shown.** That is what makes not-asking safe: a shown derivation can be checked in
   seconds and rejected one line at a time; a silent assumption is invisible until the part is wrong.
   **Deriving without showing the derivation is guessing.**

   An omission in the request is not automatically an oversight. If the value is derivable, it was
   left out because it is derivable — derive it. If it is neither derivable nor cosmetic, it was
   probably forgotten — ask.

8. **Ask what survived, with boxes, in one message** (`02_drawing_rules.md` → A01), together with the
   census image for a plain yes or a correction.
   - **Ask for measurements, not for rulings on an interpretation.** "Caliper the thread major
     diameter" costs seconds and has one answer. "Which of these three do you think it is" makes the
     user rebuild the modeller's reasoning, and their answer then carries the modeller's mistake.
   - **Structural questions block; cosmetic gaps do not.** Do not start modelling while the structure
     is unconfirmed. Do start while a small cosmetic value is outstanding — model it on the stated
     assumption and flag it — rather than idling on a round trip.
   - **The number of questions is not a target and is never to be minimised for its own sake.** The
     thing to reduce is the number of gaps that reach this step: better reading, more derivation,
     shown work. A suppressed question is a defect; a resolved one is the goal.

**Nothing is modelled that has no row.** Every feature in a `prod_` object traces to a row in
*Expanded criteria*. A feature visible in the reference with no dimension is a gap to resolve or ask,
never a licence to invent a simplified stand-in and move on.

Only then open Blender.

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

### What `specifications.md` may say ✅

This file is read as a reference while modelling — sometimes in a later session, by someone who no
longer has the original conversation. What goes in it has to be trustworthy.

- **It is a record, not an authority.** *Original prompt request* outranks everything else in the
  file. Where the file and the request disagree, the request wins and the file is wrong — fix the file.
- **Never edit *Original prompt request*.** Append later messages in order; never rewrite, summarise,
  reorder or correct what the user wrote.
- **Every value carries its source:** `stated` (quote it), `derived` (show the derivation), `measured`
  (say from what, and how), `assumed` (say so, and why it was not asked). An unsourced value is not
  allowed in this file.
- **Never write an assumption as a fact.**
- **Never record your own mistake as an open design question.** "Nothing threads into these holes yet"
  reads as a decision the user still has to make; if the hole is the wrong size, the file says the
  hole is the wrong size.
- **The file may not introduce a requirement the user never gave.** Ideas, improvements and
  alternatives go to the user in the message — they do not appear in the file as if they were settled.
- **Corrections are additive.** When a value changes, update the row *and* add a *History* row saying
  what it was, what it is now, and why. Never silently overwrite.
- **When a part is dropped**, remove its rows and leave one *History* row saying what was removed and why.
- Anything known to be wrong is fixed the moment it is known. A stale spec is worse than no spec,
  because the next session will believe it.

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

The report is the self-check. Its job is to **confirm the output against the input** — not to display
numbers. "Confirmation" is the whole point of this section; it is not a formatting instruction.

### Confirmation table — required

One row per row of *Expanded criteria*, in the same order:

| # | Requirement (as written) | Expected | Measured in Blender | Pass / Fail |
|---|---|---|---|---|

- Measured values come from the model, never from the intent. A row with no measurement is a **Fail**.
- A row **fails** when the measured value differs from the requirement, **or when the modelled feature
  cannot do what the requirement says it is for**, even if the number is arithmetically right.
  Worked example: a Ø4.28 hole for a Ø3.88 screw that threads into the plastic is a correct
  application of a clearance rule and a failed requirement — the screw falls through it.
- Every **Fail** is stated first, before anything else in the message.
- **No STL is exported for a part with a failing or unmeasured row.**
- Printing measured dimensions without comparing them to the request does **not** satisfy this
  section. Neither does labelling them "measured, not intended" — that asserts the number is real,
  not that it is right.

### Also include

- **File:** `<project>/<file name>`
- **Assumptions made**, each tied to the criteria row it affects
- **Changes** (for edits)
- **Orientation reasoning:** which face is on the bed, and why (strength, largest flat face, or fewer supports)

### Mesh validity is a separate check ✅

Manifold edges, loose geometry, bounding-box size and volume prove the mesh is *printable*. They
prove nothing about whether it is the *right part*. Run both checks; never report the first in place
of the second.
