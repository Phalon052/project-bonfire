# Catalog

Project files and reference library for Project Bonfire. Read it before designing, to reuse proven parts and design around hardware on hand.

- **model library/**: One folder per project, named `<friend>_<file type>_<project name>` (e.g. `alex_stl_letter_board_letters_arial`). Each has `stl/`, `blend/`, and `references/` (with `drawings_images/` and `specifications.md` when applicable), plus `3mf/` when prepared for printing. `data/projects.csv` indexes all projects; `projects.md` is a readable view of it. `_TEMPLATE_part.md` is the template for `specifications.md`. See `Project Bonfire/01_blender_basics.md` → section 2.
- **hardware inventory/**: Hardware on hand, sorted into `screws`, `bolts`, `nuts`, `washers`, `magnets`, and `misc`. Add items with `/bf-add` (see the command list in `USER_GUIDE.md`). Counts, reservations, and the shopping list are kept in `hardware inventory/data/*.csv`; `inventory_count.md` is a readable view regenerated from them (don't edit it). Item names follow `hardware inventory/_NAMING_GUIDE.md`.

**Naming:** lowercase with underscores; friend projects start with the friend's name. Inventory: one file per item, named after the item, e.g. `hardware inventory/screws/screw_m3x10_socket_head.md`.
