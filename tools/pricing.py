"""
Project Bonfire — plate price calculator.

    Price = ((filament g x 0.013) + (2 x print hours)) + 15%

Per plate, from what the slicer reports for that plate. The .3mf's price is
the sum of its plates.

Use:
    import os, runpy
    pr = runpy.run_path(os.path.join(ROOT, "tools", "pricing.py"))
    pr["plate_price"](120.5, 3.25)          # grams, hours -> 9.28
    print(pr["price_3mf"](r"...\\3mf\\lid_2.gcode.3mf")["report"])

Command line:
    python pricing.py 120.5 3.25             # grams hours
    python pricing.py path\\to\\file.gcode.3mf
"""

import os
import runpy
import sys
from decimal import Decimal, ROUND_HALF_UP

PER_GRAM = 0.013     # $ per gram of filament
PER_HOUR = 2.0       # $ per hour of printing
MARKUP = 0.15        # added on top


def _cents(value):
    """Round to the cent, half up (plain round() turns 3.795 into 3.79)."""
    return float(Decimal(repr(round(value, 9))).quantize(Decimal("0.01"),
                                                         ROUND_HALF_UP))


def plate_price(grams, hours):
    """Price of one plate, rounded to the cent."""
    grams = float(grams or 0.0)
    hours = float(hours or 0.0)
    return _cents((grams * PER_GRAM + hours * PER_HOUR) * (1 + MARKUP))


def price_breakdown(grams, hours):
    grams = float(grams or 0.0)
    hours = float(hours or 0.0)
    filament = grams * PER_GRAM
    time = hours * PER_HOUR
    markup = (filament + time) * MARKUP
    return {"grams": round(grams, 2), "hours": round(hours, 2),
            "filament_cost": _cents(filament), "time_cost": _cents(time),
            "markup": _cents(markup),
            "price": plate_price(grams, hours)}


def price_plates(plates):
    """plates: the `plates` list from bambu_slice.read_slice_info (needs
    filament_g and print_seconds). Returns per-plate prices and the total."""
    rows = []
    for p in plates:
        hours = (p.get("print_seconds") or 0) / 3600.0
        row = price_breakdown(p.get("filament_g") or 0.0, hours)
        row["plate"] = p.get("plate")
        row["known"] = bool(p.get("print_seconds")) and p.get("filament_g") is not None
        rows.append(row)
    return {"plates": rows,
            "total": _cents(sum(r["price"] for r in rows)),
            "all_known": all(r["known"] for r in rows)}


def format_price(priced, name=""):
    lines = ["Price%s" % ((" — %s" % name) if name else "")]
    for r in priced["plates"]:
        lines.append("  Plate %s: $%.2f  (%.1f g x $%.3f = $%.2f, "
                     "%.2f h x $%.2f = $%.2f, +%d%% = $%.2f)%s"
                     % (r["plate"], r["price"], r["grams"], PER_GRAM,
                        r["filament_cost"], r["hours"], PER_HOUR, r["time_cost"],
                        round(MARKUP * 100), r["markup"],
                        "" if r["known"] else "  ! time or weight missing"))
    if len(priced["plates"]) > 1:
        lines.append("  Total for the file: $%.2f" % priced["total"])
    return "\n".join(lines)


def price_3mf(path):
    """Price every plate of a sliced .gcode.3mf. An unsliced .3mf has no
    weight or time yet, so it must be sliced first."""
    here = os.path.dirname(os.path.abspath(__file__))
    bs = runpy.run_path(os.path.join(here, "bambu_slice.py"))
    info = bs["read_slice_info"](path)
    if not info.get("sliced"):
        return {"ok": False,
                "error": "Not sliced yet — slice it first; the price needs the "
                         "slicer's weight and time. (%s)" % info.get("note", "")}
    priced = price_plates(info["plates"])
    priced["ok"] = True
    priced["file"] = path
    priced["report"] = format_price(priced, os.path.basename(path))
    return priced


if __name__ == "__main__":
    args = sys.argv[1:]
    if len(args) == 2:
        b = price_breakdown(args[0], args[1])
        print("$%.2f  (filament $%.2f + time $%.2f + markup $%.2f)"
              % (b["price"], b["filament_cost"], b["time_cost"], b["markup"]))
    elif len(args) == 1:
        r = price_3mf(args[0])
        print(r.get("report") or r.get("error"))
    else:
        print(__doc__)
