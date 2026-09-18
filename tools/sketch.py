"""
Bonfire part sketches: three dimensioned views drawn from a part spec, in SVG,
with the standard library only.

Why it exists: `02_drawing_rules.md` -> A01 says every clarifying question comes
with a picture. Annotating a photo means editing an image and looking at it
again; rendering in Blender means a model must already exist. This draws the
structure *as understood* straight from the numbers, before any geometry, so a
wrong reading is visible immediately and costs almost nothing to redraw.

    import os, runpy
    sk = runpy.run_path(os.path.join(BONFIRE, "tools", "sketch.py"))

    spec = sk["load_spec"](r"...\\references\\part_spec.json")
    print(sk["audit"](spec))                       # text check: numbers, not pixels
    sk["write_svg"](spec, r"...\\references\\shelf_bracket_sketch_1.svg")

Views follow `02_drawing_rules.md` -> A00. The top view is the plan, looking
down the +Z axis at the face toward the camera in the reference. Thickness is
always Z. The front view sits below the top view and shares its X. The side view
sits to the right of the front view and shares its Z.

Coordinates in the spec are millimetres, X to the right and Y up in the top
view, with the origin at the datum named by `"datum"` ("center", the default, or
"corner" for the lower-left corner of the outline as drawn).

Nothing here needs to be looked at to be trusted: the drawing is a deterministic
function of the spec, and `audit()` reports in text what the drawing shows in
lines. Read the spec and the audit; look at the picture only when a human is
deciding whether the structure is right.
"""
import ast
import json
import os
import re

# ── Spec ─────────────────────────────────────────────────────

SPEC_VERSION = 1

# Question box colours, in the order they are handed out. Named, because A01
# asks questions by colour ("the orange box - is this ...").
QUESTION_COLORS = [
    ("orange", "#e8710a"),
    ("blue", "#1a73e8"),
    ("green", "#137333"),
    ("purple", "#8430ce"),
    ("red", "#c5221f"),
]

FEATURE_TYPES = ("hole", "slot", "pocket", "cutout", "boss")

# Which face a blind feature is cut from. Through features are the same either way.
FACES = ("top", "bottom")



def load_spec(path):
    """Read a part_spec.json and fill in the defaults the rest of this file assumes."""
    with open(path, encoding="utf-8") as fh:
        spec = json.load(fh)
    return normalise(spec)


def normalise(spec):
    """Apply defaults and derive the outline's extents. Returns a new dict."""
    spec = json.loads(json.dumps(spec))            # copy, so the caller's dict is untouched
    if spec.get("_normalised"):
        # Idempotent on purpose: audit() normalises and then calls check(), which
        # normalises again. Converting a "topleft" datum twice would flip every
        # feature back off the part - and report it as the user's mistake.
        return spec
    spec["_normalised"] = True
    spec.setdefault("spec_version", SPEC_VERSION)
    spec.setdefault("units", "mm")
    spec.setdefault("datum", "center")
    spec.setdefault("features", [])
    spec.setdefault("questions", [])
    spec.setdefault("details", [])
    spec.setdefault("constants", {})
    spec.setdefault("companions", {})
    spec.setdefault("mates", [])
    resolve(spec)                                  # "=" expressions -> numbers, before any geometry
    # "topleft" is how this project reads a part: u across from the left edge, L
    # down from the top end. Convert once, here, so nothing downstream has to
    # know - and so the numbers in the spec can be copied straight out of the
    # Expanded criteria table without being re-derived by hand.
    if spec["datum"] == "topleft":
        for f in spec["features"]:
            f["y"] = -float(f["y"])
        for q in list(spec.get("questions", [])) + list(spec.get("details", [])):
            if q.get("region"):
                rx0, ry0, rx1, ry1 = [float(v) for v in q["region"]]
                q["region"] = [rx0, -ry1, rx1, -ry0]

    outline = spec["outline"]
    outline.setdefault("type", "rect")
    if outline["type"] == "rect":
        w, l = float(outline["width"]), float(outline["length"])
        if spec["datum"] == "corner":
            outline["_points"] = [(0, 0), (w, 0), (w, l), (0, l)]
        elif spec["datum"] == "topleft":
            outline["_points"] = [(0, -l), (w, -l), (w, 0), (0, 0)]
        else:
            outline["_points"] = [(-w / 2, -l / 2), (w / 2, -l / 2), (w / 2, l / 2), (-w / 2, l / 2)]
    elif outline["type"] == "polygon":
        outline["_points"] = [(float(x), float(y)) for x, y in outline["points"]]
    else:
        raise ValueError("outline type must be 'rect' or 'polygon', got {!r}".format(outline["type"]))
    return spec


def extents(spec):
    """(min_x, min_y, max_x, max_y) of the outline."""
    pts = spec["outline"]["_points"]
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    return min(xs), min(ys), max(xs), max(ys)


def feature_box(feature):
    """
    (min_x, min_y, max_x, max_y) of a feature in the top view.

    Every feature carries x/y as its centre, so a wrong datum shows up as a
    feature off the part rather than as a silently shifted drawing.
    """
    x, y = float(feature["x"]), float(feature["y"])
    kind = feature["type"]
    if kind in ("hole", "boss"):
        r = float(feature["diameter"]) / 2.0
        return x - r, y - r, x + r, y + r
    w = float(feature["width"]) / 2.0
    l = float(feature["length"]) / 2.0
    return x - w, y - l, x + w, y + l


def feature_depth(feature, thickness):
    """
    Depth in Z as a number. 'through' is the full thickness; so is 'unknown',
    which draws the feature at full depth and says so on the label rather than
    inventing a value - an open number stays visibly open (02 A01).
    """
    d = feature.get("depth", "through")
    if isinstance(d, str) and d.lower() in ("through", "unknown"):
        return float(thickness)
    return float(d)


def depth_unknown(feature):
    d = feature.get("depth", "through")
    return isinstance(d, str) and d.lower() == "unknown"


def is_through(feature, thickness):
    d = feature.get("depth", "through")
    if isinstance(d, str) and d.lower() in ("through", "unknown"):
        return True
    return abs(float(d) - float(thickness)) < 1e-9


# ── Audit ────────────────────────────────────────────────────

def audit(spec):
    """
    Everything the drawing shows, as text and numbers.

    This is the check that matters: the drawing is derived from the spec, so
    reading the spec back tells you what was drawn, without spending an image on
    it. Warnings are the things that are almost always a misread rather than a
    real design: a feature off the part, a pocket deeper than the part, two
    features overlapping, a number with no stated source.
    """
    spec = normalise(spec)
    thickness = float(spec["thickness"])
    min_x, min_y, max_x, max_y = extents(spec)
    out = []
    out.append("{:s}  [{:s}]".format(spec.get("part", "(unnamed part)"), spec["units"]))
    out.append("  outline    {:s}".format(_outline_text(spec)))
    out.append("  thickness  {:g} (Z)".format(thickness))
    if spec["datum"] == "topleft":
        out.append("  datum      topleft: u from the left edge, L down from the top end"
                   "  -> u 0..{:g}, L 0..{:g}".format(max_x, -min_y))
    else:
        out.append("  datum      {:s}  -> x {:g}..{:g}, y {:g}..{:g}".format(
            spec["datum"], min_x, max_x, min_y, max_y))

    if spec["features"]:
        out.append("")
        flip = spec["datum"] == "topleft"
        out.append("  {:<16} {:<8} {:>9} {:>9} {:>18} {:>10} {:>7}".format(
            "feature", "type", "u" if flip else "x", "L" if flip else "y",
            "size", "depth", "from"))
        for f in spec["features"]:
            y = -float(f["y"]) if flip else float(f["y"])
            out.append("  {:<16} {:<8} {:>9.3f} {:>9.3f} {:>18} {:>10} {:>7}".format(
                f.get("id", "?"), f["type"], float(f["x"]), y,
                _size_text(f), _depth_text(f, thickness),
                "-" if is_through(f, thickness) else f.get("from", "top")))
            for key, expr in sorted((f.get("_expr") or {}).items()):
                out.append("  {:<16} {:>9} {:s}".format("", key, expr))

    if spec.get("mates"):
        out.append("")
        out.append("  mates")
        out.append(mate_report(spec))

    warnings = check(spec)
    out.append("")
    if warnings:
        out.append("  {:d} thing(s) to look at:".format(len(warnings)))
        out.extend("    ! " + w for w in warnings)
    else:
        out.append("  no inconsistencies found")

    if spec["questions"]:
        out.append("")
        out.append("  questions on the drawing:")
        for i, q in enumerate(spec["questions"]):
            colour = QUESTION_COLORS[i % len(QUESTION_COLORS)][0]
            out.append("    Q{:d} ({:s} box, around {:s}): {:s}".format(
                i + 1, colour, q.get("about", "region"), q.get("text", "")))
    return "\n".join(out)


def check(spec):
    """The warnings list from audit(), on its own so callers can branch on it."""
    spec = normalise(spec)
    thickness = float(spec["thickness"])
    min_x, min_y, max_x, max_y = extents(spec)
    warnings = []

    for f in spec["features"]:
        fid = f.get("id", "?")
        if f["type"] not in FEATURE_TYPES:
            warnings.append("{:s}: unknown type {!r} (expected one of {:s})".format(
                fid, f["type"], ", ".join(FEATURE_TYPES)))
        fx0, fy0, fx1, fy1 = feature_box(f)
        if fx0 < min_x or fx1 > max_x or fy0 < min_y or fy1 > max_y:
            warnings.append("{:s}: sits outside the outline - check the datum it was measured from".format(fid))
        depth = feature_depth(f, thickness)
        if f["type"] != "boss" and depth > thickness + 1e-9:
            warnings.append("{:s}: {:g} deep in a part {:g} thick".format(fid, depth, thickness))
        if f.get("from", "top") not in FACES:
            warnings.append("{:s}: 'from' is {!r}, expected one of {:s}".format(
                fid, f.get("from"), ", ".join(FACES)))
        if depth_unknown(f):
            warnings.append("{:s}: depth is open - drawn full depth, not a value to model from".format(fid))
        if not f.get("source"):
            warnings.append("{:s}: no source (stated / derived / measured / assumed)".format(fid))

    for i, a in enumerate(spec["features"]):
        for b in spec["features"][i + 1:]:
            box_a, box_b = feature_box(a), feature_box(b)
            if _overlap(box_a, box_b) and not (_contains(box_a, box_b) or _contains(box_b, box_a)):
                warnings.append("{:s} and {:s} overlap in the top view".format(
                    a.get("id", "?"), b.get("id", "?")))

    known = {f.get("id") for f in spec["features"]}
    for q in spec["questions"]:
        about = q.get("about")
        if about and about not in known and not q.get("region"):
            warnings.append("question about {!r}, which is not a feature id".format(about))
    return warnings


def _contains(outer, inner):
    """True when `inner` sits wholly inside `outer` - nesting, not a collision."""
    return (outer[0] <= inner[0] + 1e-9 and outer[1] <= inner[1] + 1e-9
            and outer[2] >= inner[2] - 1e-9 and outer[3] >= inner[3] - 1e-9)


def _overlap(a, b):
    return not (a[2] <= b[0] or b[2] <= a[0] or a[3] <= b[1] or b[3] <= a[1])


def _outline_text(spec):
    o = spec["outline"]
    if o["type"] == "rect":
        txt = "rect {:g} wide x {:g} long".format(float(o["width"]), float(o["length"]))
        if o.get("corner_radius"):
            txt += ", r{:g} corners".format(float(o["corner_radius"]))
        return txt
    return "polygon, {:d} points".format(len(o["_points"]))


def _size_text(f):
    if f["type"] in ("hole", "boss"):
        return "d{:g}".format(float(f["diameter"]))
    return "{:g} x {:g}".format(float(f["width"]), float(f["length"]))


def _depth_text(f, thickness):
    if depth_unknown(f):
        return "OPEN"
    return "through" if is_through(f, thickness) else "{:g}".format(feature_depth(f, thickness))


# ── SVG ──────────────────────────────────────────────────────

# ── Linked values ────────────────────────────────────────────
#
# Any numeric field may be an expression instead: "=blade_gap.x", or
# "=board_channel.width - 2*slide". They exist so a correction lands in ONE
# place: when a caliper settles the blade slot, everything measured from it
# follows, instead of three hand edits of which one is eventually missed.

_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_.]*")
_ALLOWED_NODES = (ast.Expression, ast.BinOp, ast.UnaryOp, ast.Name, ast.Load,
                  ast.Add, ast.Sub, ast.Mult, ast.Div, ast.USub, ast.UAdd, ast.Constant)
_NUMERIC_FIELDS = ("x", "y", "width", "length", "diameter", "depth", "thickness",
                   "corner_radius", "projection", "span")


def is_expr(value):
    return isinstance(value, str) and value.startswith("=")


def context(spec):
    """Every number in the spec, by dotted name, for expressions to refer to."""
    ctx = {}
    for key, value in (spec.get("constants") or {}).items():
        ctx[key] = float(value)
    if not is_expr(spec.get("thickness")):
        ctx["thickness"] = float(spec["thickness"])
    for key, value in (spec.get("outline") or {}).items():
        if key in _NUMERIC_FIELDS and not is_expr(value):
            ctx["outline." + key] = float(value)
    for f in spec.get("features", []):
        for key, value in f.items():
            if key in _NUMERIC_FIELDS and not is_expr(value) and not isinstance(value, str):
                ctx["{:s}.{:s}".format(f.get("id", "?"), key)] = float(value)
    for name, comp in (spec.get("companions") or {}).items():
        if not is_expr(comp.get("thickness")):
            ctx["companions.{:s}.thickness".format(name)] = float(comp.get("thickness", 0))
        for key, value in (comp.get("outline") or {}).items():
            if key in _NUMERIC_FIELDS and not is_expr(value):
                ctx["companions.{:s}.outline.{:s}".format(name, key)] = float(value)
    return ctx


def evaluate(expr, ctx):
    """Arithmetic only, over names that exist. No calls, no attributes, no builtins."""
    body = expr[1:] if expr.startswith("=") else expr
    env, missing = {}, []

    def swap(match):
        name = match.group(0)
        if name not in ctx:
            missing.append(name)
            return name
        key = "_v{:d}".format(len(env))
        env[key] = float(ctx[name])
        return key

    swapped = _NAME.sub(swap, body)
    if missing:
        raise KeyError(", ".join(sorted(set(missing))))
    tree = ast.parse(swapped, mode="eval")
    for node in ast.walk(tree):
        if not isinstance(node, _ALLOWED_NODES):
            raise ValueError("{!r} is not allowed in an expression".format(type(node).__name__))
    return float(eval(compile(tree, "<spec>", "eval"), {"__builtins__": {}}, env))   # noqa: S307


def resolve(spec, max_passes=12):
    """
    Replace every "=" expression with its value, keeping the expression in
    `_expr` so the audit can still show the derivation. Anything left after the
    last pass is a cycle or a typo, and is reported rather than guessed at.
    """
    holders = [("outline", spec.get("outline") or {}), ("spec", spec)]
    holders += [(f.get("id", "?"), f) for f in spec.get("features", [])]
    for name, comp in (spec.get("companions") or {}).items():
        holders += [("companions." + name, comp), ("companions." + name, comp.get("outline") or {})]

    for _ in range(max_passes):
        ctx = context(spec)
        progressed, pending = False, []
        for owner, holder in holders:
            for key in list(holder.keys()):
                if key not in _NUMERIC_FIELDS or not is_expr(holder[key]):
                    continue
                try:
                    value = evaluate(holder[key], ctx)
                except KeyError:
                    pending.append("{:s}.{:s} = {:s}".format(owner, key, holder[key]))
                    continue
                holder.setdefault("_expr", {})[key] = holder[key]
                holder[key] = value
                progressed = True
        if not pending:
            return spec
        if not progressed:
            raise ValueError("expressions that never resolve (cycle or unknown name): "
                             + "; ".join(pending))
    raise ValueError("expressions did not settle after {:d} passes".format(max_passes))


def flatten(spec):
    """Numbers by dotted name, for diffing two versions of a spec."""
    return context(normalise(spec))


def diff(before, after, tolerance=1e-9):
    """What moved between two specs, as text. Empty string when nothing did."""
    a, b = flatten(before), flatten(after)
    rows = []
    for key in sorted(set(a) | set(b)):
        if key not in a:
            rows.append("  + {:s} = {:g}".format(key, b[key]))
        elif key not in b:
            rows.append("  - {:s} (was {:g})".format(key, a[key]))
        elif abs(a[key] - b[key]) > tolerance:
            rows.append("  ~ {:s}  {:g} -> {:g}  ({:+g})".format(key, a[key], b[key], b[key] - a[key]))
    return "\n".join(rows)


def answer(spec, question_id, value, source="measured"):
    """
    Record a measurement against the question that was waiting for it.

    The question names the field it settles (`"sets": "blade_gap.x"`), so one
    caliper reading lands in the spec, re-resolves everything derived from it,
    and returns the diff - rather than being typed into several places by hand.
    """
    before = json.loads(json.dumps(spec))
    spec = json.loads(json.dumps(spec))
    spec.pop("_normalised", None)

    target = None
    for q in spec.get("questions", []):
        if q.get("id") == question_id:
            target = q
            break
    if target is None:
        raise KeyError("no question with id {!r}".format(question_id))
    field = target.get("sets")
    if not field:
        raise KeyError("question {!r} does not say which field it sets".format(question_id))

    owner, _, key = field.rpartition(".")
    holder = None
    if owner in ("", "spec"):
        holder = spec
    elif owner == "outline":
        holder = spec["outline"]
    else:
        for f in spec["features"]:
            if f.get("id") == owner:
                holder = f
                break
    if holder is None:
        raise KeyError("{!r} is not a field this spec has".format(field))

    holder[key] = float(value)
    holder.pop("_expr", None)
    holder["source"] = "{:s} ({:s})".format(source, question_id)
    target["answered"] = float(value)

    resolved = normalise(spec)
    return resolved, diff(before, resolved)


# ── Coverage and mates ───────────────────────────────────────

def coverage(spec, criteria, tolerance=0.01):
    """
    Which rows of the Expanded criteria table made it into the spec.

    The project's rule is that every number in the request gets a row; this is
    that rule, checked. `criteria` is a list of dicts with at least `value`, and
    optionally `id`, `feature` and `quote`.
    """
    spec = normalise(spec)
    ctx = context(spec)
    out, missing = [], 0
    for row in criteria:
        want = float(row["value"])
        feature = row.get("feature")
        hits = [name for name, got in ctx.items()
                if abs(got - want) <= tolerance and (feature is None or name.startswith(feature + "."))]
        label = str(row.get("id", row.get("quote", want)))[:34]
        if hits:
            hits.sort(key=lambda n: (len(n), n))       # the plainest name is the likeliest match
            out.append("  ok      {:<34} {:g} -> {:s}".format(label, want, ", ".join(hits[:3])))
        else:
            missing += 1
            out.append("  MISSING {:<34} {:g}{:s}".format(
                label, want, "  (expected on {:s})".format(feature) if feature else ""))
    head = "coverage: {:d} of {:d} criteria rows are in the spec".format(len(criteria) - missing, len(criteria))
    return "\n".join([head] + out)


def mate_report(spec):
    """
    Computed clearance for each mate, against the fit it is supposed to be.

    A fit is arithmetic, so it should be checked as arithmetic and not by eye:
    hole minus shaft, halved, compared with the per-side clearance the rule asks
    for (`03_materials_tolerances.md` -> section 3).
    """
    spec = normalise(spec)
    ctx = context(spec)
    rows = []
    for m in spec.get("mates", []):
        hole, shaft = ctx.get(m["hole"]), ctx.get(m["shaft"])
        if hole is None or shaft is None:
            rows.append("  {:<18} cannot check: {:s} or {:s} is not a number in this spec".format(
                m.get("id", "?"), m["hole"], m["shaft"]))
            continue
        per_side = (hole - shaft) / 2.0
        want = m.get("per_side")
        line = "  {:<18} {:s} {:g} - {:s} {:g} = {:+g} per side".format(
            m.get("id", "?"), m["hole"], hole, m["shaft"], shaft, per_side)
        if want is not None:
            delta = per_side - float(want)
            line += "  (wants {:g}{:s})".format(
                float(want), "" if abs(delta) < 1e-6 else ", off by {:+g}".format(delta))
        rows.append(line)
    return "\n".join(rows)


# ── Markdown out ─────────────────────────────────────────────

def to_markdown(spec):
    """
    The Key dimensions table, generated from the spec.

    Written so the spec can be the source and the document the output, instead
    of the numbers living in a 35 KB markdown table that has to be read in full
    every time somebody needs the geometry.
    """
    spec = normalise(spec)
    thickness = float(spec["thickness"])
    rows = ["| Feature | Value | Depth | Source | Notes |", "|---|---|---|---|---|"]
    rows.append("| Outline | {:s} | - | {:s} | datum: {:s} |".format(
        _outline_text(spec), spec.get("outline", {}).get("source", "-"), spec["datum"]))
    rows.append("| Thickness | {:g} (Z) | - | {:s} | |".format(thickness, spec.get("thickness_source", "-")))
    for f in spec["features"]:
        expr = (f.get("_expr") or {})
        note = f.get("note", "")
        if expr:
            note = (note + "  " if note else "") + "derived: " + "; ".join(
                "{:s} {:s}".format(k, v) for k, v in sorted(expr.items()))
        rows.append("| `{:s}` | {:s} | {:s} | {:s} | {:s} |".format(
            f.get("id", "?"), _size_text(f), _depth_text(f, thickness),
            str(f.get("source", "-")), note.replace("|", "/")))
    for m in spec.get("mates", []):
        rows.append("| mate `{:s}` | {:s} vs {:s} | - | {:s} | {:s} |".format(
            m.get("id", "?"), m["hole"], m["shaft"], m.get("fit", "-"),
            "per side {:g}".format(float(m["per_side"])) if m.get("per_side") is not None else ""))
    return "\n".join(rows)


PX_PER_MM = 2.2          # drawing scale; the SVG itself carries the real numbers
DETAIL_W = 210           # px, width of a detail panel
DETAIL_ASPECT = 0.62     # panel height as a fraction of its width
MARGIN = 34              # px around each view, for dimension lines
GAP = 46                 # px between views
LINE = "#202124"
THIN = "#9aa0a6"
HIDDEN = "#5f6368"
FONT = "font-family='DejaVu Sans, Verdana, sans-serif'"


def write_svg(spec, path, scale=PX_PER_MM):
    """Render the three views to `path`. Returns the path."""
    svg = svg_text(spec, scale=scale)
    directory = os.path.dirname(os.path.abspath(path))
    if directory and not os.path.isdir(directory):
        os.makedirs(directory)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(svg)
    return path


def svg_text(spec, scale=PX_PER_MM):
    """The whole drawing as an SVG string."""
    spec = normalise(spec)
    thickness = float(spec["thickness"])
    min_x, min_y, max_x, max_y = extents(spec)
    part_w = (max_x - min_x) * scale
    part_l = (max_y - min_y) * scale
    part_t = thickness * scale

    # Layout: top view upper-left; front view below it, sharing X; side view
    # right of the front view, sharing Z.
    # A question box may sit outside the part (a feature that is not drawn yet,
    # like a tab on the end), so the canvas has to make room for it.
    over_top = max([0.0] + [(_q_box(spec, q)[3] - max_y) * scale for q in spec["questions"] if _q_box(spec, q)])

    top_x, top_y = MARGIN, MARGIN + 24 + max(0.0, over_top + 10)
    front_x, front_y = top_x, top_y + part_l + GAP + 18
    side_x, side_y = front_x + part_w + GAP + 30, front_y

    # Feature labels live in a column to the right of the top view, one per row,
    # so they can never overlap each other or the drawing.
    label_x = top_x + part_w + 22
    longest = max([len(_label_text(f, thickness)) for f in spec["features"]] or [0])
    subtitle_px = MARGIN + 52 * 5.0                  # the title block's second line

    # The side elevation is the part's LENGTH across, not its thickness - a long
    # thin part runs off the page if this is measured from the wrong axis.
    side_span = part_l
    width = int(max(side_x + side_span, label_x + longest * 5.4, subtitle_px) + MARGIN)

    # Detail panels go BELOW the elevations, not beside them: the right-hand
    # band at that height already belongs to the side view, and whichever is
    # drawn second silently paints over the other.
    details = spec.get("details", [])
    detail_x = MARGIN
    detail_y = front_y + part_t + 40
    detail_row = DETAIL_W * DETAIL_ASPECT + 46          # panel + title + two caption lines
    bottom = detail_y + len(details) * detail_row if details else front_y + part_t

    legend_lines = _legend_lines(spec, width)
    height = int(bottom + MARGIN + 18 + 14 * len(legend_lines))

    body = []
    body.append("<rect width='100%' height='100%' fill='white'/>")
    body.append(_title_block(spec))

    body.append(_view_top(spec, top_x, top_y, scale, label_x))
    body.append(_view_side_elevation(spec, front_x, front_y, scale, axis="x"))   # front: X across, Z down
    body.append(_view_side_elevation(spec, side_x, side_y, scale, axis="y"))     # side:  Y across, Z down
    for i, d in enumerate(details):
        body.append(_detail_panel(spec, d, i, detail_x, detail_y + i * detail_row, thickness, scale))
    body.append(_legend(spec, width, height))

    return ("<svg xmlns='http://www.w3.org/2000/svg' width='{:d}' height='{:d}' "
            "viewBox='0 0 {:d} {:d}'>\n{:s}\n</svg>\n").format(
                width, height, width, height, "\n".join(body))


def _title_block(spec):
    name = spec.get("part", "part")
    units = spec["units"]
    sub = "dimensions in {:s}  -  top view = the face toward the camera (02 A00)".format(units)
    return ("<text x='{:d}' y='19' {:s} font-size='13' font-weight='bold' fill='{:s}'>{:s}</text>"
            "<text x='{:d}' y='32' {:s} font-size='9' fill='{:s}'>{:s}</text>").format(
                MARGIN, FONT, LINE, _esc(name), MARGIN, FONT, THIN, _esc(sub))


def _px(spec, scale, x, y, ox, oy):
    """Top view: spec mm -> svg px. Y is flipped so +Y is up, as A00 reads it."""
    min_x, min_y, max_x, max_y = extents(spec)
    return ox + (x - min_x) * scale, oy + (max_y - y) * scale


def _view_top(spec, ox, oy, scale, label_x):
    min_x, min_y, max_x, max_y = extents(spec)
    o = spec["outline"]
    parts = ["<g>"]
    parts.append(_view_label(ox, oy - 8, "TOP"))

    # outline
    if o["type"] == "rect":
        rx = float(o.get("corner_radius") or 0) * scale
        parts.append("<rect x='{:.2f}' y='{:.2f}' width='{:.2f}' height='{:.2f}' rx='{:.2f}' "
                     "fill='#f8f9fa' stroke='{:s}' stroke-width='1.6'/>".format(
                         ox, oy, (max_x - min_x) * scale, (max_y - min_y) * scale, rx, LINE))
    else:
        pts = " ".join("{:.2f},{:.2f}".format(*_px(spec, scale, x, y, ox, oy)) for x, y in o["_points"])
        parts.append("<polygon points='{:s}' fill='#f8f9fa' stroke='{:s}' stroke-width='1.6'/>".format(pts, LINE))

    # centre lines
    cx, cy = _px(spec, scale, (min_x + max_x) / 2.0, (min_y + max_y) / 2.0, ox, oy)
    parts.append("<line x1='{:.2f}' y1='{:.2f}' x2='{:.2f}' y2='{:.2f}' stroke='{:s}' stroke-width='0.7' "
                 "stroke-dasharray='9 3 2 3'/>".format(ox - 8, cy, ox + (max_x - min_x) * scale + 8, cy, THIN))
    parts.append("<line x1='{:.2f}' y1='{:.2f}' x2='{:.2f}' y2='{:.2f}' stroke='{:s}' stroke-width='0.7' "
                 "stroke-dasharray='9 3 2 3'/>".format(cx, oy - 8, cx, oy + (max_y - min_y) * scale + 8, THIN))

    # features
    thickness = float(spec["thickness"])
    for f in spec["features"]:
        through = is_through(f, thickness)
        stroke = LINE if through else HIDDEN
        dash = "" if through else " stroke-dasharray='5 3'"
        fill = "white" if through else "none"
        if f["type"] in ("hole", "boss"):
            fx, fy = _px(spec, scale, float(f["x"]), float(f["y"]), ox, oy)
            r = float(f["diameter"]) / 2.0 * scale
            parts.append("<circle cx='{:.2f}' cy='{:.2f}' r='{:.2f}' fill='{:s}' stroke='{:s}' "
                         "stroke-width='1.2'{:s}/>".format(fx, fy, r, fill, stroke, dash))
            parts.append("<line x1='{:.2f}' y1='{:.2f}' x2='{:.2f}' y2='{:.2f}' stroke='{:s}' "
                         "stroke-width='0.6' stroke-dasharray='6 2 1 2'/>".format(fx - r - 4, fy, fx + r + 4, fy, THIN))
            parts.append("<line x1='{:.2f}' y1='{:.2f}' x2='{:.2f}' y2='{:.2f}' stroke='{:s}' "
                         "stroke-width='0.6' stroke-dasharray='6 2 1 2'/>".format(fx, fy - r - 4, fx, fy + r + 4, THIN))
        else:
            bx0, by0, bx1, by1 = feature_box(f)
            px0, py0 = _px(spec, scale, bx0, by1, ox, oy)
            px1, py1 = _px(spec, scale, bx1, by0, ox, oy)
            radius = (min(float(f["width"]), float(f["length"])) / 2.0 * scale) if f["type"] == "slot" else 0
            parts.append("<rect x='{:.2f}' y='{:.2f}' width='{:.2f}' height='{:.2f}' rx='{:.2f}' fill='{:s}' "
                         "stroke='{:s}' stroke-width='1.2'{:s}/>".format(
                             px0, py0, px1 - px0, py1 - py0, radius, fill, stroke, dash))
    for row, f in enumerate(spec["features"]):
        parts.append(_feature_label(spec, f, ox, oy, scale, thickness, label_x, row))

    # overall dimensions
    parts.append(_dim_h(ox, oy + (max_y - min_y) * scale + 16, (max_x - min_x) * scale,
                        "{:g}".format(max_x - min_x)))
    parts.append(_dim_v(ox - 16, oy, (max_y - min_y) * scale, "{:g}".format(max_y - min_y)))

    parts.extend(_question_boxes(spec, ox, oy, scale))
    parts.append("</g>")
    return "".join(parts)


def _detail_panel(spec, detail, index, ox, oy, thickness, sheet_scale):
    """
    A zoomed window on one feature, with the measurement that settles it.

    A 3 mm disagreement on a 348 mm part is invisible at sheet scale - three
    readings land in the same pixel. The detail panel exists so that a question
    about a small feature is actually legible, and so the dimension shown is the
    one someone would put a caliper on: from the nearest part edge to the near
    edge of the feature.
    """
    tag = detail.get("title") or chr(ord("A") + index)
    box = _q_box(spec, detail)                       # same about/region handling as a question
    if not box:
        return ""
    fx0, fy0, fx1, fy1 = box
    cx, cy = (fx0 + fx1) / 2.0, (fy0 + fy1) / 2.0

    min_x, min_y, max_x, max_y = extents(spec)

    # Which edge the caliper would sit on. The datum edge by default, because
    # that is the number the spec is written in - "nearest" would have measured
    # this part's blade slot from the right edge and answered a question nobody
    # asked.
    from_edge = detail.get("from_edge") or ("left" if spec["datum"] in ("topleft", "corner") else "nearest")
    if from_edge == "left":
        edge = min_x
    elif from_edge == "right":
        edge = max_x
    else:
        edge = min_x if abs(fx0 - min_x) <= abs(max_x - fx1) else max_x
    near = fx0 if edge <= fx0 else fx1

    # The window has to contain both the edge and the feature, or the dimension
    # it is there to show runs off the panel.
    pad = max(2.0, abs(near - edge) * 0.08)
    wx0 = min(edge, fx0) - pad
    wx1 = max(edge, fx1) + pad
    if detail.get("span"):
        span = float(detail["span"])
        wx0, wx1 = cx - span / 2.0, cx + span / 2.0
        wx0, wx1 = min(wx0, edge - pad), max(wx1, edge + pad)
    win_w = wx1 - wx0
    win_h = win_w * DETAIL_ASPECT
    mag = DETAIL_W / win_w
    wy0, wy1 = cy - win_h / 2.0, cy + win_h / 2.0
    panel_h = DETAIL_W * DETAIL_ASPECT
    clip = "detail{:d}".format(index)

    def px(x, y):
        return ox + (x - wx0) * mag, oy + (wy1 - y) * mag

    parts = ["<g>"]
    parts.append("<clipPath id='{:s}'><rect x='{:.2f}' y='{:.2f}' width='{:.2f}' height='{:.2f}'/></clipPath>".format(
        clip, ox, oy, DETAIL_W, panel_h))
    parts.append("<g clip-path='url(#{:s})'>".format(clip))
    parts.append("<rect x='{:.2f}' y='{:.2f}' width='{:.2f}' height='{:.2f}' fill='#f8f9fa'/>".format(
        ox, oy, DETAIL_W, panel_h))

    # the part's own edges, where they fall inside the window
    for edge_x in (min_x, max_x):
        if wx0 <= edge_x <= wx1:
            ex, _ = px(edge_x, 0)
            parts.append("<line x1='{:.2f}' y1='{:.2f}' x2='{:.2f}' y2='{:.2f}' stroke='{:s}' "
                         "stroke-width='1.6'/>".format(ex, oy, ex, oy + panel_h, LINE))
    for edge_y in (min_y, max_y):
        if wy0 <= edge_y <= wy1:
            _, ey = px(0, edge_y)
            parts.append("<line x1='{:.2f}' y1='{:.2f}' x2='{:.2f}' y2='{:.2f}' stroke='{:s}' "
                         "stroke-width='1.6'/>".format(ox, ey, ox + DETAIL_W, ey, LINE))

    for f in spec["features"]:
        bx0, by0, bx1, by1 = feature_box(f)
        if bx1 < wx0 or bx0 > wx1 or by1 < wy0 or by0 > wy1:
            continue
        through = is_through(f, thickness)
        stroke = LINE if through else HIDDEN
        dash = "" if through else " stroke-dasharray='5 3'"
        if f["type"] in ("hole", "boss"):
            fx, fy = px(float(f["x"]), float(f["y"]))
            parts.append("<circle cx='{:.2f}' cy='{:.2f}' r='{:.2f}' fill='white' stroke='{:s}' "
                         "stroke-width='1.2'{:s}/>".format(fx, fy, float(f["diameter"]) / 2.0 * mag, stroke, dash))
        else:
            ax, ay = px(bx0, by1)
            bx, by = px(bx1, by0)
            radius = (min(float(f["width"]), float(f["length"])) / 2.0 * mag) if f["type"] == "slot" else 0
            parts.append("<rect x='{:.2f}' y='{:.2f}' width='{:.2f}' height='{:.2f}' rx='{:.2f}' fill='white' "
                         "stroke='{:s}' stroke-width='1.2'{:s}/>".format(
                             ax, ay, bx - ax, by - ay, radius, stroke, dash))
    parts.append("</g>")

    # frame and title
    parts.append("<rect x='{:.2f}' y='{:.2f}' width='{:.2f}' height='{:.2f}' fill='none' stroke='{:s}' "
                 "stroke-width='0.9'/>".format(ox, oy, DETAIL_W, panel_h, THIN))
    parts.append("<text x='{:.2f}' y='{:.2f}' {:s} font-size='10' font-weight='bold' fill='{:s}'>"
                 "DETAIL {:s}  ({:.1f}x the sheet)</text>".format(
                     ox, oy - 5, FONT, THIN, tag, mag / float(sheet_scale)))

    # the caliper dimension: the datum edge -> near edge of the feature
    if wx0 <= edge <= wx1:
        ex, _ = px(edge, 0)
        nx, _ = px(near, 0)
        y = oy + panel_h - 12
        parts.append(_dim_h(min(ex, nx), y, abs(nx - ex), "{:g}".format(abs(near - edge))))
    span_x, _ = px(fx0, 0)
    parts.append(_dim_h(span_x, oy + panel_h - 26, (fx1 - fx0) * mag, "{:g}".format(fx1 - fx0)))
    if detail.get("text"):
        line, row = "", 0
        for word in str(detail["text"]).split():
            if line and len(line) + 1 + len(word) > 46:
                parts.append("<text x='{:.2f}' y='{:.2f}' {:s} font-size='9' fill='{:s}'>{:s}</text>".format(
                    ox, oy + panel_h + 12 + row * 11, FONT, LINE, _esc(line)))
                line, row = word, row + 1
            else:
                line = (line + " " + word).strip()
        if line:
            parts.append("<text x='{:.2f}' y='{:.2f}' {:s} font-size='9' fill='{:s}'>{:s}</text>".format(
                ox, oy + panel_h + 12 + row * 11, FONT, LINE, _esc(line)))
    parts.append("</g>")
    return "".join(parts)


def _view_side_elevation(spec, ox, oy, scale, axis):
    """Front (axis='x') or side (axis='y') elevation: the chosen axis across, Z down."""
    min_x, min_y, max_x, max_y = extents(spec)
    thickness = float(spec["thickness"])
    span = (max_x - min_x) if axis == "x" else (max_y - min_y)
    across = span * scale
    down = thickness * scale
    lo = min_x if axis == "x" else min_y

    parts = ["<g>"]
    parts.append(_view_label(ox, oy - 8, "FRONT" if axis == "x" else "SIDE"))
    parts.append("<rect x='{:.2f}' y='{:.2f}' width='{:.2f}' height='{:.2f}' fill='#f8f9fa' "
                 "stroke='{:s}' stroke-width='1.6'/>".format(ox, oy, across, down, LINE))

    for f in spec["features"]:
        bx0, by0, bx1, by1 = feature_box(f)
        a0, a1 = (bx0, bx1) if axis == "x" else (by0, by1)
        x0 = ox + (a0 - lo) * scale
        x1 = ox + (a1 - lo) * scale
        depth = feature_depth(f, thickness)
        through = is_through(f, thickness)
        if f["type"] == "boss":
            parts.append("<rect x='{:.2f}' y='{:.2f}' width='{:.2f}' height='{:.2f}' fill='#f1f3f4' "
                         "stroke='{:s}' stroke-width='1.2'/>".format(x0, oy - depth * scale, x1 - x0, depth * scale, LINE))
            continue
        # cut from whichever face it is machined from
        top_of_cut = oy if f.get("from", "top") == "top" else oy + (thickness - depth) * scale
        parts.append("<rect x='{:.2f}' y='{:.2f}' width='{:.2f}' height='{:.2f}' fill='white' stroke='{:s}' "
                     "stroke-width='1.1'{:s}/>".format(
                         x0, top_of_cut, x1 - x0, depth * scale, LINE if through else HIDDEN,
                         "" if through else " stroke-dasharray='5 3'"))

    parts.append(_dim_v(ox + across + 14, oy, down, "{:g}".format(thickness)))
    parts.append("</g>")
    return "".join(parts)


def _label_text(f, thickness):
    """id, size and depth, in one short line."""
    if depth_unknown(f):
        return "{:s}  {:s}  depth open".format(f.get("id", "?"), _size_text(f))
    if is_through(f, thickness):
        return "{:s}  {:s}".format(f.get("id", "?"), _size_text(f))
    return "{:s}  {:s}  {:g} deep from {:s}".format(
        f.get("id", "?"), _size_text(f), feature_depth(f, thickness), f.get("from", "top"))


def _feature_label(spec, f, ox, oy, scale, thickness, label_x, row):
    """
    A leader from the feature to its own row in the label column.

    One row per feature, so labels cannot overlap each other however crowded the
    part is - a drawing that has to be squinted at is not a drawing that settles
    a question.
    """
    fx, fy = _px(spec, scale, float(f["x"]), float(f["y"]), ox, oy)
    ly = oy + 10 + row * 13
    return ("<line x1='{:.2f}' y1='{:.2f}' x2='{:.2f}' y2='{:.2f}' stroke='{:s}' stroke-width='0.6' "
            "stroke-dasharray='3 2'/>"
            "<circle cx='{:.2f}' cy='{:.2f}' r='1.6' fill='{:s}'/>"
            "<text x='{:.2f}' y='{:.2f}' {:s} font-size='9' fill='{:s}'>{:s}</text>").format(
                fx, fy, label_x - 4, ly - 3, THIN, fx, fy, THIN,
                label_x, ly, FONT, LINE, _esc(_label_text(f, thickness)))


def _question_boxes(spec, ox, oy, scale):
    """One coloured, numbered box per question (02 A01: one box per question, named by colour)."""
    out = []
    for i, q in enumerate(spec["questions"]):
        colour = QUESTION_COLORS[i % len(QUESTION_COLORS)][1]
        box = _q_box(spec, q)
        if not box:
            continue
        rx0, ry0, rx1, ry1 = box
        pad = 2.0
        px0, py0 = _px(spec, scale, rx0 - pad, ry1 + pad, ox, oy)
        px1, py1 = _px(spec, scale, rx1 + pad, ry0 - pad, ox, oy)
        out.append("<rect x='{:.2f}' y='{:.2f}' width='{:.2f}' height='{:.2f}' fill='none' stroke='{:s}' "
                   "stroke-width='1.8'/>".format(px0, py0, px1 - px0, py1 - py0, colour))
        out.append("<text x='{:.2f}' y='{:.2f}' {:s} font-size='11' font-weight='bold' fill='{:s}'>Q{:d}</text>".format(
            px0, py0 - 3, FONT, colour, i + 1))
    return out


def _q_box(spec, q):
    """The region a question points at, in spec coordinates, or None."""
    if q.get("region"):
        rx0, ry0, rx1, ry1 = [float(v) for v in q["region"]]
        return rx0, ry0, rx1, ry1
    for f in spec["features"]:
        if f.get("id") == q.get("about"):
            return feature_box(f)
    return None


def _legend_lines(spec, width):
    """
    The legend, wrapped to the canvas. A question that runs off the edge is a
    question that does not get answered, so the text wraps rather than clips.
    """
    chars = max(20, int((width - 2 * MARGIN) / 5.0))
    lines = []
    for i, q in enumerate(spec["questions"]):
        name, colour = QUESTION_COLORS[i % len(QUESTION_COLORS)]
        text = "Q{:d} ({:s}): {:s}".format(i + 1, name, q.get("text", ""))
        row, words = "", text.split()
        wrapped = []
        for word in words:
            if row and len(row) + 1 + len(word) > chars:
                wrapped.append(row)
                row = "    " + word                  # continuation lines are indented
            else:
                row = (row + " " + word).strip() if row else word
        if row:
            wrapped.append(row)
        lines.extend((colour, w) for w in wrapped)
    return lines


def _legend(spec, width, height):
    lines = _legend_lines(spec, width)
    if not lines:
        return ""
    out = []
    y = height - 12 - 14 * (len(lines) - 1)
    for i, (colour, text) in enumerate(lines):
        out.append("<text x='{:d}' y='{:.0f}' {:s} font-size='10' fill='{:s}'>{:s}</text>".format(
            MARGIN, y + 14 * i, FONT, colour, _esc(text)))
    return "".join(out)


def _view_label(x, y, text):
    return "<text x='{:.2f}' y='{:.2f}' {:s} font-size='10' font-weight='bold' fill='{:s}'>{:s}</text>".format(
        x, y, FONT, THIN, text)


def _dim_h(x, y, length, text):
    """Horizontal dimension line with arrow ticks and the value above it."""
    return ("<line x1='{x0:.2f}' y1='{y:.2f}' x2='{x1:.2f}' y2='{y:.2f}' stroke='{c}' stroke-width='0.8'/>"
            "<line x1='{x0:.2f}' y1='{ya:.2f}' x2='{x0:.2f}' y2='{yb:.2f}' stroke='{c}' stroke-width='0.8'/>"
            "<line x1='{x1:.2f}' y1='{ya:.2f}' x2='{x1:.2f}' y2='{yb:.2f}' stroke='{c}' stroke-width='0.8'/>"
            "<text x='{xm:.2f}' y='{yt:.2f}' {f} font-size='10' fill='{c}' text-anchor='middle'>{t}</text>").format(
                x0=x, x1=x + length, y=y, ya=y - 3, yb=y + 3, xm=x + length / 2.0, yt=y - 5,
                c=LINE, f=FONT, t=_esc(text))


def _dim_v(x, y, length, text):
    """Vertical dimension line; the value is written alongside, upright."""
    return ("<line x1='{x:.2f}' y1='{y0:.2f}' x2='{x:.2f}' y2='{y1:.2f}' stroke='{c}' stroke-width='0.8'/>"
            "<line x1='{xa:.2f}' y1='{y0:.2f}' x2='{xb:.2f}' y2='{y0:.2f}' stroke='{c}' stroke-width='0.8'/>"
            "<line x1='{xa:.2f}' y1='{y1:.2f}' x2='{xb:.2f}' y2='{y1:.2f}' stroke='{c}' stroke-width='0.8'/>"
            "<text x='{xt:.2f}' y='{ym:.2f}' {f} font-size='10' fill='{c}' text-anchor='middle' "
            "transform='rotate(-90 {xt:.2f} {ym:.2f})'>{t}</text>").format(
                x=x, y0=y, y1=y + length, xa=x - 3, xb=x + 3, ym=y + length / 2.0, xt=x - 5,
                c=LINE, f=FONT, t=_esc(text))


def _esc(text):
    return (str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace("'", "&apos;").replace('"', "&quot;"))


# ── Self-test ────────────────────────────────────────────────

def _demo_spec():
    """A small part that exercises every feature type, used by self_test()."""
    return {
        "part": "demo_plate",
        "units": "mm",
        "datum": "center",
        "thickness": 6.0,
        "outline": {"type": "rect", "width": 80.0, "length": 40.0, "corner_radius": 3.0},
        "features": [
            {"id": "bore", "type": "hole", "x": -25.0, "y": 0.0, "diameter": 8.0,
             "depth": "through", "source": "stated"},
            {"id": "slot", "type": "slot", "x": 10.0, "y": 0.0, "width": 6.0, "length": 30.0,
             "depth": "through", "source": "stated"},
            {"id": "pocket", "type": "pocket", "x": 30.0, "y": 12.0, "width": 12.0, "length": 8.0,
             "depth": 2.5, "source": "derived"},
        ],
        "questions": [
            {"about": "slot", "text": "is the slot centred on the long axis, or offset to one side?"},
        ],
    }


def example_spec():
    """
    A small part that uses every feature of the schema, as documentation that
    runs. Nothing here is a real part - it exists so the spec format can be read
    off a working example instead of a paragraph.
    """
    return {
        "spec_version": SPEC_VERSION,
        "part": "example_bracket",
        "units": "mm",
        "datum": "center",

        # Named numbers, so a rule appears once and is referred to, not retyped.
        "constants": {"slide": 0.20, "wall": 4.0},

        "outline": {"type": "rect", "width": 120.0, "length": 60.0,
                    "corner_radius": 4.0, "source": "stated"},
        "thickness": 8.0,
        "thickness_source": "stated",

        # A part this one mates with, so the fit can be checked as arithmetic.
        "companions": {
            "slide_key": {"outline": {"type": "rect", "width": 12.0, "length": 50.0},
                          "thickness": 4.0}
        },

        "features": [
            {"id": "pilot_hole", "type": "hole", "x": -44.0, "y": 0.0, "diameter": 5.2,
             "depth": "through", "source": "stated", "note": "clearance for an M5"},

            {"id": "cable_slot", "type": "slot", "x": 0.0, "y": 0.0,
             "width": 8.0, "length": 34.0, "depth": "through", "source": "stated"},

            # Linked: sits one wall thickness clear of the slot, so moving the
            # slot moves it too.
            {"id": "keeper_hole", "type": "hole",
             "x": "=cable_slot.x + cable_slot.width/2 + wall",
             "y": 22.0, "diameter": 3.3, "depth": "unknown",
             "source": "derived; depth open until the screw is measured"},

            {"id": "magnet_pocket", "type": "pocket", "x": -44.0, "y": -20.0,
             "width": 20.0, "length": 12.0, "depth": 3.0, "from": "bottom",
             "source": "measured"},

            # Linked to the companion: the channel is the key plus clearance.
            {"id": "key_channel", "type": "pocket", "x": 40.0, "y": 0.0,
             "width": "=companions.slide_key.outline.width + 2*slide",
             "length": "=companions.slide_key.outline.length",
             "depth": "=companions.slide_key.thickness", "from": "bottom",
             "source": "derived from the key plus the slide clearance"},

            {"id": "locator_boss", "type": "boss", "x": -12.0, "y": 24.0,
             "diameter": 6.0, "depth": 2.0, "source": "stated"},
        ],

        "questions": [
            {"id": "Q-A", "about": "cable_slot", "sets": "cable_slot.x",
             "text": "the slot is drawn on the centreline; is it centred, or offset toward the "
                     "pilot hole? A caliper from the left edge to its near edge settles it."},
            {"id": "Q-B", "about": "keeper_hole", "sets": "keeper_hole.depth",
             "text": "how deep does the keeper screw need to go? drawn full depth until then."},
        ],

        "details": [
            {"about": "cable_slot", "title": "A", "from_edge": "left",
             "text": "left edge of the plate to the near edge of the slot - the reading Q-A needs."},
        ],

        "mates": [
            {"id": "key_in_channel", "hole": "key_channel.width",
             "shaft": "companions.slide_key.outline.width", "fit": "slide", "per_side": 0.20},
        ],
    }


def example_criteria():
    """Stand-in for the Expanded criteria rows, for coverage()."""
    return [
        {"id": "1 plate width", "value": 120.0, "feature": "outline"},
        {"id": "2 thickness", "value": 8.0},
        {"id": "3 slot width", "value": 8.0, "feature": "cable_slot"},
        {"id": "4 magnet depth", "value": 3.0, "feature": "magnet_pocket"},
        {"id": "5 rib height", "value": 6.5},          # nothing in the spec carries this yet
    ]


def self_test():
    """Check the geometry, not the look. Returns a list of failures (empty = good)."""
    fails = []
    spec = normalise(_demo_spec())

    x0, y0, x1, y1 = extents(spec)
    if (x0, y0, x1, y1) != (-40.0, -20.0, 40.0, 20.0):
        fails.append("extents wrong: {!r}".format((x0, y0, x1, y1)))

    if feature_box(spec["features"][0]) != (-29.0, -4.0, -21.0, 4.0):
        fails.append("hole box wrong: {!r}".format(feature_box(spec["features"][0])))

    if not is_through(spec["features"][1], spec["thickness"]):
        fails.append("through slot not reported as through")
    if is_through(spec["features"][2], spec["thickness"]):
        fails.append("2.5 deep pocket reported as through")

    if check(spec):
        fails.append("clean spec produced warnings: {!r}".format(check(spec)))

    # a feature off the part, a pocket deeper than the part, and a missing source
    bad = normalise(_demo_spec())
    bad["features"].append({"id": "off", "type": "hole", "x": 60.0, "y": 0.0, "diameter": 4.0,
                            "depth": "through", "source": "stated"})
    bad["features"].append({"id": "deep", "type": "pocket", "x": -10.0, "y": -14.0,
                            "width": 5.0, "length": 5.0, "depth": 9.0})
    found = " ".join(check(bad))
    for expect in ("outside the outline", "9 deep in a part 6 thick", "no source"):
        if expect not in found:
            fails.append("check() missed {!r}; got {!r}".format(expect, found))

    # a top-left datum must survive being normalised twice (audit -> check)
    tl = {"part": "tl", "datum": "topleft", "thickness": 5.0,
          "outline": {"type": "rect", "width": 40.0, "length": 90.0},
          "features": [{"id": "h", "type": "hole", "x": 10.0, "y": 20.0, "diameter": 4.0,
                        "depth": "through", "source": "stated"}]}
    if check(normalise(normalise(tl))):
        fails.append("topleft spec breaks when normalised twice: {!r}".format(check(normalise(tl))))
    rows = [line for line in audit(tl).splitlines() if " hole " in line]
    if not rows or "10.000" not in rows[0] or "20.000" not in rows[0]:
        fails.append("audit does not print topleft coordinates back as u / L: {!r}".format(rows))

    bad_face = json.loads(json.dumps(tl))
    bad_face["features"][0].update({"depth": 2.0, "from": "side"})
    if "expected one of" not in " ".join(check(bad_face)):
        fails.append("check() accepts a 'from' face that does not exist")

    with_detail = json.loads(json.dumps(tl))
    with_detail["details"] = [{"about": "h", "title": "A", "text": "check"}]
    detail_svg = svg_text(with_detail)
    if "DETAIL A" not in detail_svg or "clipPath" not in detail_svg:
        fails.append("detail panel did not render")

    # linked values, and the cascade that is the whole point of them
    ex = normalise(example_spec())
    keeper = [f for f in ex["features"] if f["id"] == "keeper_hole"][0]
    if abs(float(keeper["x"]) - 8.0) > 1e-9:            # 0 + 8/2 + 4
        fails.append("expression did not resolve: keeper_hole.x = {!r}".format(keeper["x"]))
    if keeper.get("_expr", {}).get("x", "")[:1] != "=":
        fails.append("the derivation was not kept for the audit to show")
    channel = [f for f in ex["features"] if f["id"] == "key_channel"][0]
    if abs(float(channel["width"]) - 12.4) > 1e-9:      # key 12 + 2 x 0.20
        fails.append("companion expression wrong: key_channel.width = {!r}".format(channel["width"]))

    moved, changed = answer(example_spec(), "Q-A", -3.10)
    del moved
    if "cable_slot.x" not in changed or "keeper_hole.x" not in changed:
        fails.append("answer() did not cascade to the derived feature: {!r}".format(changed))

    try:
        resolve(normalise({"part": "cyc", "thickness": 3.0,
                           "outline": {"type": "rect", "width": 10.0, "length": 10.0},
                           "features": [{"id": "a", "type": "hole", "x": "=b.x", "y": 0, "diameter": 1,
                                         "depth": "through", "source": "s"},
                                        {"id": "b", "type": "hole", "x": "=a.x", "y": 0, "diameter": 1,
                                         "depth": "through", "source": "s"}]}))
        fails.append("a circular expression was accepted")
    except ValueError:
        pass

    try:
        evaluate("=__import__('os').getcwd()", {})
        fails.append("evaluate() ran something that is not arithmetic")
    except (ValueError, KeyError, SyntaxError):
        pass

    cov = coverage(example_spec(), example_criteria())
    if "MISSING" not in cov or "4 of 5" not in cov:
        fails.append("coverage() did not flag the criteria row with nothing to match it")

    if "+0.2 per side" not in mate_report(example_spec()):
        fails.append("mate_report() did not compute the clearance")

    md = to_markdown(example_spec())
    if "| `key_channel` |" not in md or "derived:" not in md:
        fails.append("to_markdown() lost a feature or its derivation")

    svg = svg_text(spec)
    if not svg.startswith("<svg") or not svg.rstrip().endswith("</svg>"):
        fails.append("svg is not well formed at the edges")
    for expect in ("TOP", "FRONT", "SIDE", "Q1", "demo_plate"):
        if expect not in svg:
            fails.append("svg is missing {!r}".format(expect))
    # the drawing must be inside its own canvas
    import re
    header = re.search(r"width='(\d+)' height='(\d+)'", svg)
    w, h = int(header.group(1)), int(header.group(2))
    for mx, my in re.findall(r"<rect x='(-?[\d.]+)' y='(-?[\d.]+)'", svg):
        if float(mx) < 0 or float(my) < 0 or float(mx) > w or float(my) > h:
            fails.append("something is drawn outside the canvas at {:s},{:s}".format(mx, my))
            break
    return fails


if __name__ == "__main__":
    import sys

    problems = self_test()
    print("\n".join(problems) if problems else "self_test: ok")

    if "--example" in sys.argv:
        spec = example_spec()
        print("\n== audit ==")
        print(audit(spec))
        print("\n== coverage against the criteria table ==")
        print(coverage(spec, example_criteria()))
        print("\n== key dimensions, generated ==")
        print(to_markdown(spec))
        print("\n== answering Q-A with a caliper reading of -3.10 ==")
        answered, changed = answer(spec, "Q-A", -3.10)
        print(changed or "  (nothing moved)")
        out = sys.argv[sys.argv.index("--example") + 1] if len(sys.argv) > sys.argv.index("--example") + 1 else None
        if out:
            write_svg(spec, out)
            print("\nwrote {:s}".format(out))
