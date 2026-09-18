# 02 — Rules for Interpreting Drawings

Applies to hand drawings, whiteboard photos, and photos of objects.
**Status key:** ✅ = decided · **[Fill out]** = not decided yet.

---

## A00. Viewing angle and vocabulary ✅

Read this before reading any number off a photo, drawing, or written request. Every dimension word
below names a fixed axis. None of them is a judgement call.

### The default view ✅

- **Every photo and every drawing is a top-down view** — looking straight down at the object, seeing
  the face that is toward the camera.
- The only exceptions: the object is *obviously* photographed at an angle, or a drawing is divided
  into labelled sections such as **"front view"** / **"side view"**. Without a label, it is top-down.
- "The face facing camera" means the face toward the viewer in the supplied image. On a part that
  installs face-down, that is the *underside* of the finished part — say which is which in the report.

### Dimension words ✅

Relative to the view above:

| Word | Axis | Means |
|---|---|---|
| **thick / thickness** | **Z** | **Out of the image plane.** Always. Never a lateral dimension. Applies to any feature — a plate, a board, a tab, a wall, a rib. |
| **tall / height** | **Z** | Same axis as thickness. "3.85 mm tall off of the top's thickness" = 3.85 mm in Z, measured from the datum named (the top's thickness). |
| **deep / depth** | **Z** | Same axis, measured down from the named face. |
| **wide / width** | lateral | In the image plane, across the part's short axis unless another axis is named. |
| **long / length** | lateral | In the image plane, along the part's long axis unless another axis is named. |
| **horizontal / horizontally** | lateral | In the image plane, left–right **as the image is shown**. "The first supports past that gap horizontally" = move left and right from the gap in the image. |
| **vertical / vertically** | lateral | In the image plane, up–down **as the image is shown**. It does **not** mean out of the plane. "The curvature of the vertical ends" = the ends at the top and bottom of the image. |
| **in horizontal alignment with** | lateral | At the same position along the image's up–down axis: the two regions sit in the same band across the part. |

- **A number is never reassigned to a different axis to make an interpretation work.** If "3.85 mm
  thick" will not fit the structure as understood, the *structure* is misunderstood — stop and ask
  (section A01). Do not quietly turn a thickness into a width.
- Before modelling, write down every number in the request with its axis and the datum it is measured
  from (this is the *Expanded criteria* table, `01_blender_basics.md` → section 0). Anything that
  cannot be written down goes to the resolution ladder (`01_blender_basics.md` → section 0, step 6)
  before it is allowed to become a question.
- **The request is its own glossary.** Before treating a word as ambiguous, look at how the same
  person used that word — and its contrasting words — elsewhere in the same request. A request that
  says "2.7 mm thick" of a plate, "3.85 mm thick" of a board, and "horizontally" of a lateral
  direction has already defined all three. Reading one term in isolation and calling it unclear is a
  reading failure, not a gap in the request.

## A01. Asking for clarification ✅

- **Ask with a picture, always.** Never describe a region in words alone.
  - A reference photo or drawing exists → draw a labelled box on it around the region in question.
  - A model exists → render it from the same view as the reference and draw the box on that.
  - No model yet, or the question is about the *structure* rather than a region of the photo →
    write the part spec (`references/part_spec.json`, template in `catalog/model library/`) and
    generate the three views with `tools/sketch.py`, one `questions` entry per open question. The
    drawing is then the statement of the structure believed correct — a wrong reading shows up
    before any geometry exists, and redrawing after a correction costs one call. Run
    `sketch.py` → `audit(spec)` first: it lists every number and flags features off the part,
    pockets deeper than the part, overlaps, and numbers with no source.
  - One box per question, each a different colour; name the colour in the question text
    ("the orange box — is this section top thickness only, with no border?").
  - Save the marked image, or the generated `.svg`, with `paths.py` → `next_reference_path()` and
    show it in the message.
- **Do not offer a menu of interpretations of the geometry.** Multiple choice is for decisions the
  user owns — which fit, which material, which of two real options. It is not for "what does this
  part look like". When the shape is uncertain, state the single structure believed to be correct,
  show it boxed, and ask for a yes or a correction.
- **Never mark an option "Recommended" when the reading behind it is unconfirmed.** A recommendation
  signals confidence and invites a rubber stamp; a wrong reading presented that way gets approved,
  and the approval then looks like the user's decision instead of the modeller's mistake.
- If the user answers in their own words instead of picking an offered option, treat that as a signal
  that the offered framing was wrong. Re-state the structure in plain words and confirm before modelling.
- Ask all open questions in one message (see section G), each with its own box.
- **These boxes are not drawing marks.** A clarification box outlines a *region* and carries no number,
  so it never means a height (section C), and its colour identifies the question, not a fit type
  (section D). The same applies in reverse when the user boxes a region on a returned image: a
  coloured box with no number inside it points at a region, it does not dimension it. Take the region
  from the box and the dimensions from the request.

## A02. Region census — reading a reference ✅

**Do this for every part whose geometry comes from a photo or drawing. It is not conditional on
feeling uncertain** — the failure this catches is confident misreading, and a gate that fires on
self-assessed doubt cannot catch that.

1. Go over the reference and **enumerate every distinct region**: every area that differs from its
   neighbours in depth, in what fills it, or in whether it is open. Not every rib — every *kind* of area.
2. **Number them on the image.** Draw and label the boxes, save with `paths.py` →
   `next_reference_path()`, and put the table in `specifications.md` → *Reference regions*.
3. For each one, fill this in:

| # | What it is | Why it is there (function) | How its dimensions are known |
|---|---|---|---|
| | | | stated / derived / measured / **unknown** |

4. **State the count.** "Twelve regions" is auditable by the user at a glance; a paragraph is not.
5. A blank *why*, or an **unknown** in the last column, is a gap. It goes to the resolution ladder
   (`01_blender_basics.md` → section 0, step 6) — not straight to a question.

The numbered image doubles as the structure sign-off and as the clarification ask (A01). One image,
one round trip.

> Worked example — on the Kobalt insert, a census produces: rim · left lattice bay · plain bay ·
> blade slot · support each side of the slot · narrow right bay · four bosses · finger hole · end tab ·
> two pins on the tab · **the break in the right border** · **the section with no lattice**. The last
> three are exactly the ones that were built wrong or skipped, and all three would have come back with
> an empty *why*.

## A03. "Don't", "just", "not exact" — limiting instructions ✅

A negative or limiting instruction is not automatically permission to simplify. Classify every one
before modelling:

| Flavour | Example | What it means |
|---|---|---|
| **Cosmetic simplify** | "Latus does not need to be exact in width or pattern" | Build a simple version. Form is free. |
| **Functional simplify** | "Finger hole doesn't need to be fancy, just an 18.7 mm hole" | Form is relaxed, **function is not**. It still has to be a through hole a finger fits, in the right place. |
| **A fact about the real object** | "Do not include the latus in that triangle section" | There is nothing there because there is **no material** there. This is structure, told as an instruction. |
| **Deferred, not dropped** | "Use sliding fit param as thread tolerance is not setup yet" | Name precisely what is deferred (the tolerance rule) and what is still required (that the screw threads into the plastic). Deferring the rule never defers the requirement. |

- **When something classifies as *a fact about the real object*, ask what else is different about that
  region.** Material missing in one respect usually means material missing in others — a section with
  no lattice turned out to have no border either.
- If a limiting instruction cannot be classified, that is a question, and it is a cheap one.

## A0. Titles: project and part ✅

| Where | Written as | Meaning |
|---|---|---|
| Top of the drawing | `<title>` | **Project name**, converted to lowercase with underscores (see `01_blender_basics.md` → *Project names*). Add the work to that project if its folder exists; otherwise create the project. |
| Directly under the top title | `<title>` | **New part (file) to make**, named `<title>`. |
| Directly under the top title | `<title> +` | **Edit** of the existing part `<title>` in that project. |

- Project folders and file naming: see `01_blender_basics.md` → sections 2 and 4.
- If a drawing has no top title, ask for the project name before saving.

### Matching titles to existing projects and parts ✅

Before creating anything, check whether a title refers to something that already exists. Titles are often shortened, abbreviated, or slightly misspelled (e.g. `LBLA` or `lb letters arial` for `letter_board_letters_arial`, `shelf brkt` for `shelf_bracket`).

1. **Compare** the project title with the folders in `model library`, and each part title with the `prod_` objects in that project's .blend. Use `tools/paths.py` → `match_title()`.
2. **Decide** from how close the names are:

| Result | Example | Action |
|---|---|---|
| Exact match | `desk hook` → `stl_desk_hook` | Use the existing project or part. |
| One clear match (close spelling, abbreviation, or initials) and nothing else close | `LBLA` → `alex_stl_letter_board_letters_arial` | Use it, and state the match in the report. |
| Several close matches, or only a partial match | `desk` → `stl_desk_hook` or `sam_stl_desk_organizer`; `hinge` → `lid_hinge`; `LB letters` → `letter_board_letters_arial` (missing `arial`) | **Ask before modelling.** |
| Nothing close | `gear box` | Create a new project or part. |

3. **When asking**, list the candidates and ask which applies:
   - **Project title:** "Does this belong to the existing project `<name>`, or is it a new project?"
   - **Part title without `+`:** "Is this an edit of the existing part `<name>`, or a new part?"
   - **Part title with `+`:** "Which existing part is this an edit of?" If nothing matches at all, ask before creating it as a new part.
4. Ask about project and part matches together in the same message as any other open questions about the drawing.

## A. Markers in the corner ✅

| Marker | Meaning | Default if missing |
|---|---|---|
| `UN: <unit>` | Unit for **every** number in the drawing: `mm`, `in`, `ft`, etc. | **mm** |
| `MAT: <brand + material>` | Filament the part will be printed in. Use it to pick clearances from `03_materials_tolerances.md`. | **Bambu PLA Basic** |

- Convert everything to mm before modelling (1 in = 25.4 mm, 1 ft = 304.8 mm). Report in mm, and mention the original unit if it wasn't mm.
- If `MAT:` names a material that isn't in `03_materials_tolerances.md`, ask before choosing clearances.

## B. Dimension lines (length) ✅

- A **line with short perpendicular lines at both ends and a number in the middle** is the length of the part edge it sits next to.

## C. Boxed numbers (height) ✅

- A **number with a box around it and an arrow pointing to something** is the **height** of that object.
- If there are several, each one is the height of the particular section it points to.
- "Height" means the dimension out of the drawing plane (the extrusion or thickness direction).

## D. Marker colour (whiteboard / Expo) ✅

| Colour | Meaning |
|---|---|
| **Black** | Exact dimension. Model it as written. |
| **Green** | **Sliding fit.** Apply the slide clearance for the material in `03_materials_tolerances.md`. |
| **Red** | **Press fit.** Apply the press-fit clearance for the material in `03_materials_tolerances.md`. |

- A coloured dimension describes how that feature must fit its mating part. Say which side the clearance was applied to (hole made bigger, or peg made smaller).
- **[Fill out]** Which side gets the clearance by default: the hole, the peg, or split between them?
- **[Fill out]** Meaning of any other colours (blue, etc.), or "ask if seen".

## E. Angles ✅

- All lines are straight and meet at **90°**, unless a corner has an **arc drawn in it with a number and a degree symbol**. That corner is the angle written.

## F. Sections to fill out

### F1. Round features [Fill out]
How are diameters and radii written (`Ø`, `D`, `R`, or a line across a circle)? Is a circle drawn with one number assumed to be a diameter? Needed to avoid confusing radius and diameter.

### F2. Holes [Fill out]
How is a through-hole shown versus a blind hole with a depth? Countersinks or counterbores? Hole counts (e.g. `x4`)?

### F3. Curves and corners [Fill out]
How are rounded corners (fillets) and chamfers shown, with their sizes? Is a curve drawn freehand approximate or intended to be a true arc?

### F4. Hidden, centre, and symmetry lines [Fill out]
Do dashed lines mean hidden edges? Are centre lines or "symmetric" features marked? Needed for holes and features that aren't visible in the view drawn.

### F5. Views — partly settled, see A00 ✅ / [Fill out]

Settled in A00: every image is a **top-down view** unless the object is obviously photographed at an
angle, or a drawing is divided into labelled sections such as "front view" / "side view".
**[Fill out]** remains for: how the sections are divided on the page, and which view the boxed height
numbers (section C) are relative to when several views are drawn.

When there are multiple sketches, how are views labelled (top / front / side)? Which view is the "front" that the height boxes are relative to?

### F6. Reference point / where dimensions are measured from [Fill out]
Are positions measured from an edge, from a centre, or from the previous feature? Needed so hole and feature positions don't drift.

### F7. Explicit tolerances [Fill out]
Are `±` values ever written, and do they override the colour rules?

### F8. Multiple parts [Fill out]
How are separate parts marked in one drawing (labels, circled letters, separate boxes)? How should they be named in the files?

### F9. Photos of real objects ✅

- **A photo tells you what features exist and roughly where. It does not give you dimensions.**
  Numbers come from the request (calipers). Where the request gives no number, the photo gives an
  estimate that must be labelled as an estimate and confirmed before it is modelled.
- **Correct for perspective before reading any position off a photo.** A phone photo of a long part
  foreshortens the far end. If the part has a dimension that is constant along its length (an outline
  width, say), measure that width row by row and use it as a local scale; positions that disagreed by
  several mm before the correction come out symmetric after it. Say in the report that this was done.
- **Photo-derived positions are an interpretation.** Before modelling, mark them on the photo and get
  a yes (section A01). Do not settle the extent of a region by thresholding a cropped strip and then
  build on the result — that is a guess wearing a measurement's clothes.
- **A worn or dusty part hides structure.** A region that reads as "plain" may be a real feature — a
  break in a rim, a section that is top thickness only. If the request refers to a section that can
  only be located by looking ("the section on the right that has no latus"), box it and confirm which
  one is meant rather than inferring it.
- Expected accuracy of photo measurements: roughly ±0.5–1 mm for a straight-down photo, worse near
  the edges of frame and worse again along the long axis of a long part.
- **[Fill out]** How the ruler is shown (always in the same plane as the object?), and which
  measurements in a request are caliper readings versus read off the photo.

### F10. Notes and text [Fill out]
Any other shorthand used on drawings (e.g. "thru", "typ", "sym", part names).

## G. Handling unclear drawings

- Read all markers, dimensions, and colours first, then list anything that is missing, unreadable, or contradictory, and **ask about all of them in one message** before modelling, each with its own box (section A01).
- Check that dimensions add up (e.g. section lengths match the total). If they don't, ask.
- Don't guess a missing dimension from how the sketch looks, unless approximate values are requested. If that's allowed, say which values were estimated.
- **A feature that is visible in the reference but has no dimension in the request is a question, not a licence to approximate it.** Don't model a simplified stand-in for a real feature and carry on; a plain rectangle in place of a shaped latch is not "close enough", it is an invented part.
- **Understanding the structure is a separate job from collecting the numbers, and it comes first.** Having every dimension does not mean the part is understood. Before modelling, write back in plain words what the part *is* — which regions exist, what is solid, what is open, what sits at what depth, what mates with what — and get a yes. Dimension questions alone will not catch a wrong mental model, because the numbers all still parse.
- After modelling, list every dimension used and which rule it came from, so mistakes are easy to spot.
