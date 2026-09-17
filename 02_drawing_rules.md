# 02 — Rules for Interpreting Drawings

Applies to hand drawings, whiteboard photos, and photos of objects.
**Status key:** ✅ = decided · **[Fill out]** = not decided yet.

---

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

### F5. Views [Fill out]
When there are multiple sketches, how are views labelled (top / front / side)? Which view is the "front" that the height boxes are relative to?

### F6. Reference point / where dimensions are measured from [Fill out]
Are positions measured from an edge, from a centre, or from the previous feature? Needed so hole and feature positions don't drift.

### F7. Explicit tolerances [Fill out]
Are `±` values ever written, and do they override the colour rules?

### F8. Multiple parts [Fill out]
How are separate parts marked in one drawing (labels, circled letters, separate boxes)? How should they be named in the files?

### F9. Photos of real objects [Fill out]
- How the ruler is shown (always in the same plane as the object?).
- Which measurements are given with calipers versus read from the photo.
- Expected accuracy of photo measurements (roughly ±0.5–1 mm is realistic for a straight-down photo).

### F10. Notes and text [Fill out]
Any other shorthand used on drawings (e.g. "thru", "typ", "sym", part names).

## G. Handling unclear drawings

- Read all markers, dimensions, and colours first, then list anything that is missing, unreadable, or contradictory, and **ask about all of them in one message** before modelling.
- Check that dimensions add up (e.g. section lengths match the total). If they don't, ask.
- Don't guess a missing dimension from how the sketch looks, unless approximate values are requested. If that's allowed, say which values were estimated.
- After modelling, list every dimension used and which rule it came from, so mistakes are easy to spot.
