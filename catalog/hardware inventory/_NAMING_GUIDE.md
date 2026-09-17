# Inventory Item Naming Guide

Every inventory item has one name. It is used in three places, always identically:
- the `item` column in `data/inventory.csv`
- the item file name (`<name>.md` in its type folder)
- the hardware list in a project's `specifications.md`

## Format

```
<type>_<dimensions>_<specifiers>_<lowes code>
```

- **All lowercase.** Underscores separate words; no spaces or other symbols except `.` and `-` inside dimensions.
- The **type** is always the first part and the **dimensions** always the second, written with no underscores inside them.
- **Specifiers** can be several words, each separated by `_`.
- The **Lowe's code** is always last and only digits. Leave it off when there isn't one.

## 1. Type

One word. It also decides the folder.

| Type | Folder | Use for |
|---|---|---|
| `screw` | screws | Machine screws, wood screws, self-tapping screws |
| `bolt` | bolts | Hex bolts, carriage bolts, bolts used with a nut |
| `nut` | nuts | All nuts |
| `washer` | washers | Flat, lock, and fender washers |
| `magnet` | magnets | All magnets |
| `insert` | misc | Heat-set or press-in threaded inserts |
| `standoff` | misc | Threaded standoffs and spacers |
| `pin` | misc | Dowel pins, roll pins |
| `spring` | misc | Springs |
| `bearing` | misc | Ball bearings |
| other single word | misc | e.g. `ziptie`, `hook`, `hinge` |

## 2. Dimensions

Numbers only, joined with `x`. Units: metric in mm with an `m` thread prefix; imperial in inches with an `in` suffix.

| Item | Pattern | Examples |
|---|---|---|
| Metric screw / bolt | `m<diameter>x<length>` | `m3x10`, `m4x12`, `m5x20` |
| Metric, fine pitch | `m<diameter>-<pitch>x<length>` | `m8-1.0x20` (coarse pitch is assumed if no pitch is written) |
| Imperial screw / bolt | `<diameter>in-<tpi>x<length>in` | `0.25in-20x1in` (1/4"-20 × 1"), `0.3125in-18x1.5in` (5/16"-18 × 1-1/2") |
| Numbered imperial size | `no<size>-<tpi>x<length>in` | `no10-24x0.75in` (#10-24 × 3/4"), `no8-32x0.5in` |
| Wood / self-tapping screw | `no<size>x<length>in` or `m<diameter>x<length>` | `no8x1.25in`, `m3.5x16` |
| Nut | thread size only | `m4`, `m8-1.0`, `0.25in-20`, `no10-24` |
| Washer (standard) | the screw size it fits | `m4`, `0.25in`, `no10` |
| Washer (non-standard) | `id<inner>xod<outer>` | `id4.3xod12` |
| Magnet, disc | `d<diameter>x<thickness>` | `d6x3`, `d10x2` |
| Magnet, block | `<length>x<width>x<thickness>` | `10x5x2`, `20x10x3` |
| Magnet, ring | `od<outer>xid<inner>x<thickness>` | `od10xid4x3` |
| Heat-set insert | `m<thread>x<length>` | `m3x5.7`, `m4x8` |
| Standoff | `m<thread>x<length>` | `m3x10` |
| Pin | `d<diameter>x<length>` | `d3x20` |
| Bearing | `<id>x<od>x<width>` | `8x22x7` (608 size) |
| Spring | `od<outer>x<length>` | `od6x20` |

- Always convert fractions to decimals (`1/4` → `0.25`, `3/4` → `0.75`). Slashes can't be used in file names.
- Drop trailing zeros except for pitch: `m3x10`, not `m3.0x10.0`.

## 3. Specifiers

Only what tells two items apart. Put them in this order and use these exact words:

| Order | Group | Words |
|---|---|---|
| 1 | Head / style | `socket_head`, `button_head`, `flat_head`, `pan_head`, `hex_head`, `truss_head`, `carriage`, `hex`, `nylon_insert` (lock nut), `flange`, `wing`, `coupling`, `acorn`, `flat` (washer), `split_lock`, `fender`, `heat_set`, `press_in`, `female_female`, `male_female` |
| 2 | Drive (only if not implied by the head) | `hex_drive`, `phillips`, `torx`, `slotted`, `square` |
| 3 | Material / finish | `stainless`, `zinc`, `black_oxide`, `brass`, `nylon`, `galvanized`, `steel` |
| 4 | Other | grade or strength (`n52`, `grade8`), `wood`, `self_tapping`, `partially_threaded`, `adhesive_back` |

- Socket-head screws are assumed to be hex drive, so don't add `hex_drive`.
- Leave a group out if it doesn't apply or isn't known.

## 4. Lowe's code

- The **Lowe's Item #** from the package or the loose-hardware bin label. **Digits only** (no `#`, no spaces).
- It is always the last part, so an item can be found by its code alone.
- If an item is added before its code is known, add the code to the name (and rename its file) the next time a label with the code shows up.

## Full examples

| Item | Name |
|---|---|
| M4 × 12 socket head cap screw, stainless, Lowe's #1234567 | `screw_m4x12_socket_head_stainless_1234567` |
| M3 × 10 button head, black oxide, no code | `screw_m3x10_button_head_black_oxide` |
| 1/4"-20 × 1" hex bolt, zinc | `bolt_0.25in-20x1in_hex_head_zinc` |
| #10-24 × 3/4" Phillips pan head machine screw | `screw_no10-24x0.75in_pan_head_phillips` |
| #8 × 1-1/4" wood screw, Phillips | `screw_no8x1.25in_flat_head_phillips_wood` |
| M4 nylon-insert lock nut, stainless | `nut_m4_nylon_insert_stainless` |
| 1/4"-20 hex nut, zinc, Lowe's #7654321 | `nut_0.25in-20_hex_zinc_7654321` |
| M4 flat washer | `washer_m4_flat` |
| M5 split lock washer, stainless | `washer_m5_split_lock_stainless` |
| 6 × 3 mm disc magnet, N52 | `magnet_d6x3_n52` |
| 20 × 10 × 3 mm block magnet with adhesive | `magnet_20x10x3_adhesive_back` |
| M3 heat-set insert, 5.7 mm long, brass | `insert_m3x5.7_heat_set_brass` |
| 608 bearing | `bearing_8x22x7` |

*The Lowe's codes in these examples are placeholders, not real item numbers.*

## Adding from a photo

When a photo of a package, bin label, or part number is sent with `/bf-add` or `/bf-restock`:

1. Read the type, size, specifiers, and Lowe's Item # from the label, and build the name with this guide.
2. Look it up (by Lowe's code first, then by name). If it exists, restock it. If not, add it and fill in its item file from the label.
3. **Quantity:** use the number given with the command. Otherwise use the count printed on the package (count per pack × packs shown). For loose hardware with no count, ask.
4. If anything on the label can't be read, ask for just that part.
