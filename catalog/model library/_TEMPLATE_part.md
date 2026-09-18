# <Part name>

- **Category:** (peg, clip, hinge, insert hole, magnet pocket, bracket, ...)
- **Status:** Idea / Designed / Printed & tested / Proven
- **Use it for:**
- **Don't use it for:**

> Rules for what may be written in this file: `01_blender_basics.md` → section 2, *What
> `specifications.md` may say*. Every value carries a source, nothing is asserted that the user did
> not give, and the section below outranks the rest of the file.

## Original prompt request

Verbatim, exactly as the user wrote it — no paraphrase, reordering, or correction, typos included.
**Never edited.** Later messages that add or change a requirement are appended below in order, each
with a note of when it arrived. Filled in before any modelling (`01_blender_basics.md` → section 0).

> (paste the request here)

**Later messages**

| # | When | What it added or changed |
|---|---|---|
| | | |

## Reference regions

Census of the photo or drawing (`02_drawing_rules.md` → A02), with the numbered image saved in
`references/`. State the region count. A blank *why* or an **unknown** goes to the resolution ladder
(`01_blender_basics.md` → section 0, step 7), not straight to a question.

Numbered image: `references/…`  ·  Regions found: **N**

| # | What it is | Why it is there (function) | How its dimensions are known |
|---|---|---|---|
| | | | stated / derived / measured / unknown |

## Mates and motion

Every feature that touches something else. An empty *range of movement* cell is an unfinished row.

| Feature | Mates with | Fixed or moving | Range of movement | What that constrains |
|---|---|---|---|---|
| | | | | |

## Expanded criteria

One row per requirement taken apart from the request above. **Every number in the request gets a row.**
Axis and datum follow `02_drawing_rules.md` → A00 (*thick / tall / deep* = Z; *wide / long /
horizontal / vertical* = in the image plane). A row whose axis or datum cannot be filled in is a
question to ask, not an assumption to make.

This table is what the confirmation table in the end-of-task report is checked against, row for row
(`01_blender_basics.md` → section 5).

| # | Quoted from the request | Feature | Axis | Value | Measured from (datum) | What it is for | Source | Derivation (if derived) | Confirmed? |
|---|---|---|---|---|---|---|---|---|---|
| | | | | | | | stated / derived / measured / assumed | | |

A `derived` row with an empty *Derivation* cell is a guess, not a derivation.

**Gaps — resolved and asked**

Every gap, and which rung of the resolution ladder settled it (`01_blender_basics.md` → section 0,
step 7). A gap only reaches *Asked* after rungs 1–6 fail.

| # | What was missing | Settled by (rung 1–6, or asked) | Value / answer | Consequence if wrong |
|---|---|---|---|---|
| | | | | |

## Key dimensions (mm)

| Feature | Value | Exact / Slide / Press | Source | Notes |
|---|---|---|---|---|
| | | | stated / derived / measured / assumed | |

## Quantities

How many of each part to print for the whole project. Use **`n`** when the part is independent (modular, like letters), so any number can be printed.
Identical parts are one object and one STL; write the count here as a plain number (e.g. `peg` | `3`), not "1 each".

| Part (object name) | Quantity | Notes |
|---|---|---|
| | | |

## Hardware from hardware inventory

Hardware needed to assemble the whole project. The first column must match the item's `item` name in `hardware inventory/data/inventory.csv` exactly, so it can be committed automatically.

| Item (name in inventory.csv) | Quantity needed | Used for | On hand? |
|---|---|---|---|
| | | | |

## Mates with — as built and tested

*Mates and motion* above is the analysis done before modelling. This section records what actually
happened when the part was made and tried.

- (other part, hardware from hardware inventory, or a real-world object, e.g. "letter board groove")
- Clearance used (per side):
- How well it fit:

## Material and printing

- **Material(s) tested:**
- **Print orientation:**
- **Supports:** yes / no
- **Layer height:**
- **Other slicer settings that mattered:**

## Files

- **.blend:**
- **STL / 3MF:**
- **Photos / drawings:**

## Modelling instructions

- (how to reuse or adapt it, e.g. "keep hidden from the front", "scale depth, never width")

## History and lessons learned

| Date | Change / result |
|---|---|
| | |
