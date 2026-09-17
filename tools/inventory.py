"""
Bonfire inventory tool. Data lives in CSV files (fast to search, easy to edit in Excel):

    catalog/hardware inventory/data/inventory.csv       one row per item (counts, name parts, reorder level)
    catalog/hardware inventory/data/commitments.csv     hardware reserved for projects
    catalog/hardware inventory/data/shopping_list.csv   things to buy (auto rows + manual rows)

Every change also regenerates the human-readable view
    catalog/hardware inventory/inventory_count.md
which is for people only. Never read or edit it for lookups; use the CSVs / this tool.

Run inside Blender (via the Blender MCP) or any Python 3:

    import os, runpy
    BONFIRE = os.environ.get("BONFIRE_HOME") or os.path.expanduser(r"~\\Desktop\\Project Bonfire")
    inv = runpy.run_path(os.path.join(BONFIRE, "tools", "inventory.py"))
    inv["add_item"]("screw_m4x12_socket_head_stainless", qty=50, reorder_at=10,
                    details={"Thread size": "M4 x 0.7", "Length": "12", "Head type": "socket"})
    inv["search"]("m4")                    # fast lookup by any part of the name, type, or Lowe's code
    inv["find_item"]("1234567")            # exact lookup by Lowe's code or name
    inv["restock"]("1234567", 25)          # by Lowe's code or name
    inv["commit"]("alex_stl_letter_board_letters_arial")     # hardware from the project's specifications.md
    inv["commit"]("stl_shelf_bracket", {"screw_m4x12_socket_head": 4})
    inv["complete"]("stl_shelf_bracket")   # used: subtract from quantity, mark complete
    inv["cancel"]("stl_shelf_bracket")     # release without using
    inv["rename_item"]("old_name", "new_name")
    inv["refresh"]()                       # after editing a CSV by hand
    inv["status"]()                        # summary text

Item names follow hardware inventory/_NAMING_GUIDE.md:
    <type>_<dimensions>_<specifiers>_<lowes code>   e.g. screw_m4x12_socket_head_stainless_1234567
"""
import csv
import datetime
import os
import re

TOOLS = os.path.dirname(os.path.abspath(__file__))
CATALOG = os.path.join(os.path.dirname(TOOLS), "catalog")          # Project Bonfire/catalog
LIBRARY = os.path.join(CATALOG, "model library")
INVENTORY = os.path.join(CATALOG, "hardware inventory")
DATA = os.path.join(INVENTORY, "data")
INVENTORY_CSV = os.path.join(DATA, "inventory.csv")
COMMITMENTS_CSV = os.path.join(DATA, "commitments.csv")
SHOPPING_CSV = os.path.join(DATA, "shopping_list.csv")
VIEW_MD = os.path.join(INVENTORY, "inventory_count.md")
ITEM_TEMPLATE = os.path.join(INVENTORY, "_TEMPLATE_inventory_item.md")
COUNT_FILE = INVENTORY_CSV   # kept for older callers

TYPES = {"screw": "screws", "bolt": "bolts", "nut": "nuts", "washer": "washers", "magnet": "magnets", "misc": "misc"}

INV_COLS = ["item", "type", "dimensions", "specifiers", "lowes_code", "folder", "item_file",
            "quantity", "committed", "available", "reorder_at", "last_updated", "notes"]
COMMIT_COLS = ["project", "item", "quantity", "committed_on", "status", "completed_on"]
SHOP_COLS = ["item", "quantity_to_buy", "needed_for", "where_to_buy", "source"]   # source: auto / manual


# ---------- basics ----------

def _today():
    return datetime.date.today().isoformat()


def _num(v):
    try:
        return int(str(v).strip())
    except ValueError:
        return None


def _key(s):
    return re.sub(r"\s+", " ", str(s).strip().lower())


def _read_csv(path, cols):
    if not os.path.exists(path):
        return []
    with open(path, newline="", encoding="utf-8-sig") as f:
        rows = []
        for r in csv.DictReader(f):
            row = {c: (r.get(c) or "").strip() for c in cols}
            if any(row.values()):
                rows.append(row)
        return rows


def _write_csv(path, cols, rows):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    try:
        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
            w.writeheader()
            for r in rows:
                w.writerow({c: r.get(c, "") for c in cols})
    except PermissionError:
        raise PermissionError(f"{os.path.basename(path)} is open in another program (e.g. Excel). Close it and try again.")


def _read():
    return (_read_csv(INVENTORY_CSV, INV_COLS),
            _read_csv(COMMITMENTS_CSV, COMMIT_COLS),
            _read_csv(SHOPPING_CSV, SHOP_COLS))


def _write(counts, commits, shop):
    counts.sort(key=lambda r: (r["type"], r["item"]))
    _write_csv(INVENTORY_CSV, INV_COLS, counts)
    _write_csv(COMMITMENTS_CSV, COMMIT_COLS, commits)
    _write_csv(SHOPPING_CSV, SHOP_COLS, shop)
    _write_view(counts, commits, shop)


def setup():
    """Create the CSV files (headers only) if they don't exist, and the readable view."""
    counts, commits, shop = _read()
    _recalc(counts, commits, shop)
    _write(counts, commits, shop)
    return f"Data files ready in {DATA}"


# ---------- names ----------

def parse_name(name):
    """Split a guide-style name into type, dimensions, specifiers, lowes code. Returns (dict, problems)."""
    parts = str(name).strip().split("_")
    info = {"type": parts[0] if parts else "", "dimensions": parts[1] if len(parts) > 1 else "",
            "specifiers": [], "lowes": ""}
    rest = parts[2:]
    if rest and rest[-1].isdigit():
        info["lowes"] = rest.pop()
    info["specifiers"] = rest
    problems = []
    if name != name.lower() or " " in name:
        problems.append("use lowercase with underscores, no spaces")
    if not info["type"] or info["type"].isdigit():
        problems.append("missing type")
    if not info["dimensions"] or not re.search(r"\d", info["dimensions"]):
        problems.append("missing dimensions")
    return info, problems


def _name_fields(name):
    info, _ = parse_name(name)
    return {"dimensions": info["dimensions"], "specifiers": "_".join(info["specifiers"]), "lowes_code": info["lowes"]}


def _file_name(name):
    return name.strip() + ".md"


def _type_folder(item_type):
    t = _key(item_type)
    if t not in TYPES and t.endswith("s") and t[:-1] in TYPES:
        t = t[:-1]
    if t not in TYPES:
        raise ValueError(f"type must be one of: {', '.join(TYPES)}")
    return t, TYPES[t]


# ---------- lookups ----------

def find_item(query, counts=None):
    """Exact lookup by Lowe's code (digits) or name. Also matches the same item saved without a code."""
    counts = counts if counts is not None else _read()[0]
    q = str(query).strip()
    if q.isdigit():
        return next((r for r in counts if r["lowes_code"] == q), None)
    row = next((r for r in counts if _key(r["item"]) == _key(q)), None)
    if row:
        return row
    base = parse_name(q)[0]
    if base["lowes"]:
        row = next((r for r in counts if r["lowes_code"] == base["lowes"]), None)
        if row:
            return row
    spec = "_".join(base["specifiers"])
    return next((r for r in counts if parse_name(r["item"])[0]["type"] == base["type"]
                 and r["dimensions"] == base["dimensions"] and r["specifiers"] == spec), None)


def search(query="", item_type=None, low_only=False):
    """
    Fast search. query matches any part of the name, dimensions, specifiers, notes, or Lowe's code
    (several words = all must match). item_type filters by folder type. Returns a short text list.
    """
    counts, commits, shop = _read()
    _recalc(counts, commits, shop)
    words = [w for w in re.split(r"[\s_]+", _key(query)) if w]
    want = _type_folder(item_type)[1] if item_type else None
    out = []
    for r in counts:
        if want and r["folder"] != want:
            continue
        hay = " ".join([r["item"], r["dimensions"], r["specifiers"], r["lowes_code"], r["notes"]]).lower()
        if not all(w in hay for w in words):
            continue
        a, lvl = _num(r["available"]), _num(r["reorder_at"])
        low = a is not None and lvl is not None and a <= lvl
        if low_only and not low:
            continue
        out.append(f"{r['item']}: {r['available'] or r['quantity']} available"
                   + (f" ({r['committed']} committed)" if r["committed"] else "")
                   + (" LOW" if low else ""))
    return "\n".join(out) if out else "no matches"


# ---------- calculations ----------

def _recalc(counts, commits, shop):
    committed, projects = {}, {}
    for c in commits:
        if c["status"].lower() == "committed":
            k = _key(c["item"])
            committed[k] = committed.get(k, 0) + (_num(c["quantity"]) or 0)
            projects.setdefault(k, set()).add(c["project"])
    auto, known = [], set()
    for r in counts:
        k = _key(r["item"])
        known.add(k)
        r.update(_name_fields(r["item"]))
        cm = committed.get(k, 0)
        r["committed"] = str(cm) if cm else ""
        q = _num(r["quantity"])
        if q is None:
            r["available"] = r["quantity"]
            continue
        avail = q - cm
        r["available"] = str(avail)
        low = _num(r["reorder_at"])
        if avail < 0:
            auto.append({"item": r["item"], "quantity_to_buy": str(-avail),
                         "needed_for": ", ".join(sorted(projects.get(k, []))), "source": "auto"})
        elif low is not None and avail <= low:
            auto.append({"item": r["item"], "quantity_to_buy": "", "needed_for": "at or below reorder level",
                         "source": "auto"})
    for k, n in committed.items():
        if k not in known:
            auto.append({"item": k, "quantity_to_buy": str(n),
                         "needed_for": "not in inventory; " + ", ".join(sorted(projects[k])), "source": "auto"})
    old_where = {_key(s["item"]): s["where_to_buy"] for s in shop}
    for a in auto:
        a["where_to_buy"] = old_where.get(_key(a["item"]), "")
    manual = [s for s in shop if s["source"] != "auto"]
    for s in manual:
        s["source"] = "manual"
    shop[:] = manual + auto
    return auto


# ---------- readable view (for people only) ----------

def _md_table(cols, rows):
    out = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    for r in rows:
        out.append("| " + " | ".join(str(v).replace("|", "/") for v in r) + " |")
    if not rows:
        out.append("| " + " | ".join("" for _ in cols) + " |")
    return out


def _write_view(counts, commits, shop):
    lines = [
        "# Hardware Inventory",
        "",
        f"*Generated from `data/*.csv` on {datetime.datetime.now():%Y-%m-%d %H:%M}. Read-only view for people: "
        "edits here are overwritten. To change things, use the `/bf-` commands (`/bf-add`, `/bf-restock`, "
        "`/bf-commit`, `/bf-done`, `/bf-cancel`), or edit the CSV files in `data/` and ask for a refresh.*",
        "",
        "## Counts",
        "",
    ]
    lines += _md_table(["Item", "Type", "Qty", "Committed", "Available", "Reorder at", "Updated", "Notes"],
                       [[r["item"], r["type"], r["quantity"], r["committed"], r["available"], r["reorder_at"],
                         r["last_updated"], r["notes"]] for r in counts])
    open_c = [c for c in commits if c["status"] == "committed"]
    done_c = [c for c in commits if c["status"] != "committed"]
    lines += ["", "## Reserved for projects", ""]
    lines += _md_table(["Project", "Item", "Qty", "Since"],
                       [[c["project"], c["item"], c["quantity"], c["committed_on"]] for c in open_c])
    lines += ["", "## Shopping list", ""]
    lines += _md_table(["Item", "Qty to buy", "Why", "Where to buy"],
                       [[s["item"], s["quantity_to_buy"], s["needed_for"], s["where_to_buy"]] for s in shop])
    lines += ["", "## History (last 50)", ""]
    lines += _md_table(["Project", "Item", "Qty", "Committed", "Result", "Closed"],
                       [[c["project"], c["item"], c["quantity"], c["committed_on"], c["status"], c["completed_on"]]
                        for c in done_c[-50:]])
    with open(VIEW_MD, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


# ---------- project hardware (from specifications.md) ----------

def _spec_hardware(project):
    path = os.path.join(LIBRARY, project, "references", "specifications.md")
    if not os.path.exists(path):
        raise FileNotFoundError(f"No specifications.md for project '{project}'")
    items, in_sec, header = {}, False, None
    for ln in open(path, encoding="utf-8").read().split("\n"):
        if ln.startswith("## "):
            in_sec, header = ln[3:].lower().startswith("hardware"), None
            continue
        if not in_sec or not ln.strip().startswith("|"):
            continue
        cells = [c.strip() for c in ln.strip().strip("|").split("|")]
        if header is None:
            header = [c.lower() for c in cells]
            continue
        if set("".join(cells)) <= set("-: "):
            continue
        row = dict(zip(header, cells))
        qty = _num(next((v for k, v in row.items() if k.startswith("quantity")), ""))
        if cells[0] and cells[0].lower() != "none" and qty:
            items[cells[0]] = items.get(cells[0], 0) + qty
    return items


def _report(action, subject, changes, auto):
    out = [f"{action}: {subject}"] + [f"  {c}" for c in changes]
    if auto:
        out.append("  Shopping list:")
        out += [f"    {a['item']}: {a['quantity_to_buy'] or '-'} ({a['needed_for']})" for a in auto]
    return "\n".join(out)


# ---------- commands ----------

def commit(project, items=None):
    """Reserve hardware for a project. items: {item name: qty}; default = project's specifications.md."""
    items = items if items is not None else _spec_hardware(project)
    counts, commits, shop = _read()
    active = {_key(c["item"]) for c in commits if c["project"] == project and c["status"] == "committed"}
    changes = []
    for name, qty in items.items():
        row = find_item(name, counts)
        match = row["item"] if row else name
        if _key(match) in active:
            changes.append(f"{match}: already committed, skipped")
            continue
        commits.append({"project": project, "item": match, "quantity": str(qty), "committed_on": _today(),
                        "status": "committed", "completed_on": ""})
        changes.append(f"{match}: {qty} committed")
    if not items:
        changes.append("no hardware listed")
    auto = _recalc(counts, commits, shop)
    _write(counts, commits, shop)
    return _report("Committed", project, changes, auto)


def _close(project, status):
    counts, commits, shop = _read()
    changes = []
    for c in commits:
        if c["project"] == project and c["status"] == "committed":
            if status == "complete":
                row = next((r for r in counts if _key(r["item"]) == _key(c["item"])), None)
                q = _num(row["quantity"]) if row else None
                if q is not None:
                    row["quantity"] = str(q - (_num(c["quantity"]) or 0))
                    row["last_updated"] = _today()
                    changes.append(f"{c['item']}: -{c['quantity']} (now {row['quantity']})")
                else:
                    changes.append(f"{c['item']}: {c['quantity']} used (not counted or not in inventory; unchanged)")
            else:
                changes.append(f"{c['item']}: {c['quantity']} released")
            c["status"], c["completed_on"] = status, _today()
    if not changes:
        changes.append("nothing committed for this project")
    auto = _recalc(counts, commits, shop)
    _write(counts, commits, shop)
    return _report("Completed" if status == "complete" else "Cancelled", project, changes, auto)


def complete(project):
    return _close(project, "complete")


def cancel(project):
    return _close(project, "cancelled")


def _make_item_file(path, name, item_type, fields, details):
    text = open(ITEM_TEMPLATE, encoding="utf-8").read() if os.path.exists(ITEM_TEMPLATE) else "# <item>\n"
    lines = text.split("\n")
    for i, ln in enumerate(lines):
        if ln.startswith("# "):
            lines[i] = f"# {name}"
        elif ln.startswith("- **Type:**"):
            lines[i] = f"- **Type:** {item_type}"
        else:
            for label, value in fields.items():
                if value and ln.startswith(f"- **{label}:**"):
                    lines[i] = f"- **{label}:** {value}"
            if ln.startswith("|") and details:
                cells = [c.strip() for c in ln.strip().strip("|").split("|")]
                for label, value in details.items():
                    if len(cells) >= 2 and _key(cells[0]).startswith(_key(label)) and not cells[1]:
                        lines[i] = f"| {cells[0]} | {value} |"
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def add_item(name, item_type=None, qty=0, reorder_at=None, notes="", details=None,
             storage="", where_to_buy="", material=""):
    """
    Add a new item: a row in inventory.csv plus an item file (from the template) in its type folder.
    item_type defaults to the name's first part (types without their own folder go to misc).
    qty: number, or "plenty" / "few". If the item already exists (name or Lowe's code), restocks instead.
    """
    parsed, problems = parse_name(name)
    if problems:
        return f"Add: '{name}' not added. Name doesn't follow _NAMING_GUIDE.md: " + "; ".join(problems)
    if item_type is None:
        item_type = parsed["type"] if parsed["type"] in TYPES else "misc"
    _, folder = _type_folder(item_type)
    counts, commits, shop = _read()
    if find_item(name, counts) is not None:
        if _num(qty) is None:
            return f"Add: {find_item(name, counts)['item']} already exists; quantity not changed ('{qty}' isn't a number)"
        return restock(name, int(qty))
    rel = f"{folder}/{_file_name(name)}"
    path = os.path.join(INVENTORY, folder, _file_name(name))
    changes = [f"added with quantity {qty}" + (f", reorder at {reorder_at}" if reorder_at is not None else "")]
    if os.path.exists(path):
        changes.append(f"item file already exists, kept: {rel}")
    else:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        _make_item_file(path, name, parsed["type"], {"Storage location": storage, "Where to buy / link": where_to_buy,
                                                     "Material / finish": material}, details or {})
        changes.append(f"item file created: {rel}")
    counts.append({"item": name, "type": parsed["type"], "folder": folder, "item_file": rel, "quantity": str(qty),
                   "reorder_at": "" if reorder_at is None else str(reorder_at), "last_updated": _today(),
                   "notes": notes})
    auto = _recalc(counts, commits, shop)
    _write(counts, commits, shop)
    return _report("Added", name, changes, auto)


def restock(item, qty):
    """Add qty to an existing item. item: name or Lowe's code. A full name with a new Lowe's code adds the code."""
    counts, commits, shop = _read()
    row = find_item(item, counts)
    if row is None:
        return f"Restock: '{item}' isn't in the inventory yet; add it with add_item()"
    q = _num(row["quantity"])
    if q is None:
        return f"Restock: {row['item']} has a non-numeric quantity ('{row['quantity']}'); not changed"
    row["quantity"], row["last_updated"] = str(q + qty), _today()
    name, had_code = row["item"], row["lowes_code"]
    auto = _recalc(counts, commits, shop)
    _write(counts, commits, shop)
    report = _report("Restocked", name, [f"+{qty} (now {row['quantity']})"], auto)
    s = str(item).strip()
    if not s.isdigit() and parse_name(s)[0]["lowes"] and not had_code:
        report += "\n" + rename_item(name, s)
    return report


def rename_item(old, new):
    """Rename an item everywhere: inventory row, item file, commitments, shopping list, project hardware lists."""
    _, problems = parse_name(new)
    if problems:
        return f"Rename: '{new}' doesn't follow _NAMING_GUIDE.md: " + "; ".join(problems)
    counts, commits, shop = _read()
    row = next((r for r in counts if _key(r["item"]) == _key(old)), None)
    if row is None:
        return f"Rename: '{old}' not found"
    changes = []
    if row["item_file"]:
        src = os.path.join(INVENTORY, *row["item_file"].split("/"))
        new_rel = row["item_file"].rsplit("/", 1)[0] + "/" + _file_name(new)
        dst = os.path.join(INVENTORY, *new_rel.split("/"))
        if os.path.exists(src) and not os.path.exists(dst):
            os.rename(src, dst)
            txt = open(dst, encoding="utf-8").read().replace(f"# {old}", f"# {new}", 1)
            open(dst, "w", encoding="utf-8").write(txt)
            row["item_file"] = new_rel
            changes.append(f"file renamed: {new_rel}")
    for lst in (commits, shop):
        for r in lst:
            if _key(r["item"]) == _key(old):
                r["item"] = new
    row["item"], row["last_updated"] = new, _today()
    if os.path.isdir(LIBRARY):
        for proj in os.listdir(LIBRARY):
            spec = os.path.join(LIBRARY, proj, "references", "specifications.md")
            if os.path.exists(spec):
                txt = open(spec, encoding="utf-8").read()
                upd = re.sub(r"^\|\s*" + re.escape(old) + r"\s*\|", f"| {new} |", txt, flags=re.M)
                if upd != txt:
                    open(spec, "w", encoding="utf-8").write(upd)
                    changes.append(f"updated hardware list in {proj}")
    auto = _recalc(counts, commits, shop)
    _write(counts, commits, shop)
    return _report("Renamed", f"{old} -> {new}", changes, auto)


def refresh():
    """Recalculate committed / available / name columns and the shopping list after hand edits to the CSVs."""
    counts, commits, shop = _read()
    auto = _recalc(counts, commits, shop)
    _write(counts, commits, shop)
    return _report("Refreshed", "inventory", [f"{len(counts)} items"], auto)


def status():
    counts, commits, shop = _read()
    _recalc(counts, commits, shop)
    open_c = [c for c in commits if c["status"] == "committed"]
    out = ["Committed:"] + ([f"  {c['project']}: {c['item']} x{c['quantity']}" for c in open_c] or ["  none"])
    out += ["Shopping list:"] + ([f"  {s['item']}: {s['quantity_to_buy'] or '-'} ({s['needed_for']})"
                                  for s in shop] or ["  empty"])
    return "\n".join(out)
