"""
Bonfire project helper: creates project folders and works out file names,
so they aren't rebuilt by hand each time (saves tokens and mistakes).

Run inside Blender (via the Blender MCP) or any Python 3:

    import os, runpy
    BONFIRE = os.environ.get("BONFIRE_HOME") or os.path.expanduser(r"~\\Desktop\\Project Bonfire")
    bp = runpy.run_path(os.path.join(BONFIRE, "tools", "paths.py"))
    p = bp["create_project"]("letter board letters arial", friend="Alex")
    # p["blend"], p["stl"], p["references"], ...
    bp["next_export_path"](p["root"], "upper_a")          # -> ...\\stl\\upper_a_1.stl
    bp["next_reference_path"](p["root"], "plate preview", "png")  # -> ...\\references\\plate_preview_1.png
    bp["next_backup_name"]("lid", "big", existing_names)  # -> back_lid_0.0.1
    bp["match_title"]("LB letters")                       # compare a drawing title with existing projects
    bp["match_title"]("upr A", "part", [o.name for o in bpy.data.objects])
    bp["index_projects"]()                                # rebuild the project index CSV (after exports, edits)
    bp["find_projects"]("letter")                         # fast search of the project index
    bp["resolve_project"]("shelf bracket")                # folder name from a full or partial name
    bp["cleanup_exports"]()                               # delete all but the newest STL of each part
    bp["cleanup_exports"]("tolerance", dry_run=True)      # preview for one project
    bp["cleanup_references"]()                            # drop old sketches/renders, keep the newest
    bp["cleanup_references"](keep=2, dry_run=True)        # preview, keeping the newest two

Project index (fast lookup, one row per project folder):
    catalog/model library/data/projects.csv
Readable view for people only (generated, never read it for lookups):
    catalog/model library/projects.md

Rules implemented (see 01_blender_basics.md, section 2 and 4):
- names are lowercase with underscores
- project folder: catalog/model library/<friend>_<type>_<name>/
- inside: <type>/ (e.g. stl/), blend/, references/
  (references/drawings_images/ and references/specifications.md only when asked)
- Claude's outputs (previews, renders, reports): references/<project>_<description>_<n>.<ext>, never overwritten
- .blend: blend/<friend>_<name>.blend  (no type)
- exports: <type>/<object name>_<n>.<type>, n starts at 1 and never overwrites
"""
import csv
import datetime
import os
import re
import shutil

CATALOG = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "catalog")   # Project Bonfire/catalog
LIBRARY = os.path.join(CATALOG, "model library")
SPEC_TEMPLATE = os.path.join(LIBRARY, "_TEMPLATE_part.md")
PROJECTS_CSV = os.path.join(LIBRARY, "data", "projects.csv")
PROJECTS_MD = os.path.join(LIBRARY, "projects.md")
PROJECT_COLS = ["folder", "project", "friend", "file_type", "blend", "parts", "latest_exports",
                "has_specs", "has_drawings", "hardware", "created", "updated"]


def clean(name):
    """Lowercase, spaces/dashes -> underscores, drop other symbols."""
    s = re.sub(r"[\s\-]+", "_", str(name).strip().lower())
    s = re.sub(r"[^a-z0-9_.]", "", s)
    return re.sub(r"_+", "_", s).strip("_")


def project_name(name, friend=None):
    """Name used for the .blend: <friend>_<name> (no file type)."""
    return "_".join(x for x in (clean(friend) if friend else "", clean(name)) if x)


def folder_name(name, friend=None, ftype="stl"):
    """Project folder: <friend>_<type>_<name>."""
    return "_".join(x for x in (clean(friend) if friend else "", clean(ftype), clean(name)) if x)


def project_paths(name, friend=None, ftype="stl", library=LIBRARY):
    root = os.path.join(library, folder_name(name, friend, ftype))
    refs = os.path.join(root, "references")
    return {
        "root": root,
        "name": project_name(name, friend),
        ftype: os.path.join(root, clean(ftype)),
        "blend_dir": os.path.join(root, "blend"),
        "blend": os.path.join(root, "blend", project_name(name, friend) + ".blend"),
        "references": refs,
        "drawings_images": os.path.join(refs, "drawings_images"),
        "specifications": os.path.join(refs, "specifications.md"),
    }


def create_project(name, friend=None, ftype="stl", drawings=False, specs=False,
                   library=LIBRARY):
    """Create the folder structure (safe to call again; never overwrites)."""
    p = project_paths(name, friend, ftype, library)
    for key in (ftype, "blend_dir", "references"):
        os.makedirs(p[key], exist_ok=True)
    if drawings:
        os.makedirs(p["drawings_images"], exist_ok=True)
    if specs and not os.path.exists(p["specifications"]):
        if os.path.exists(SPEC_TEMPLATE):
            shutil.copyfile(SPEC_TEMPLATE, p["specifications"])
        else:
            with open(p["specifications"], "w", encoding="utf-8") as f:
                f.write("# " + p["name"] + " specifications\n")
    p["existed"] = True
    index_projects()
    return p


# ---------- project index (CSV) ----------

def _spec_hardware_names(spec_path):
    """Item names from the 'Hardware' table in specifications.md."""
    names, in_sec, header = [], False, False
    for ln in open(spec_path, encoding="utf-8").read().split("\n"):
        if ln.startswith("## "):
            in_sec, header = ln[3:].lower().startswith("hardware"), False
            continue
        if in_sec and ln.strip().startswith("|"):
            cells = [c.strip() for c in ln.strip().strip("|").split("|")]
            if not header:
                header = True
                continue
            if set("".join(cells)) <= set("-: ") or not cells[0] or cells[0].lower() == "none":
                continue
            names.append(cells[0])
    return names


def _scan_project(folder):
    root = os.path.join(LIBRARY, folder)
    friend, core = _core_project(folder)
    ftype = next((p for p in clean(folder).split("_") if p in FILE_TYPES), "")
    blend_dir = os.path.join(root, "blend")
    blends = sorted(f for f in os.listdir(blend_dir) if f.endswith(".blend")) if os.path.isdir(blend_dir) else []
    parts, latest = {}, 0
    for t in FILE_TYPES:
        d = os.path.join(root, t)
        if not os.path.isdir(d):
            continue
        for f in os.listdir(d):
            m = re.match(r"^(.*)_(\d+)\.%s$" % t, f, re.I)
            if m:
                parts[m.group(1)] = max(parts.get(m.group(1), 0), int(m.group(2)))
                latest = max(latest, os.path.getmtime(os.path.join(d, f)))
    spec = os.path.join(root, "references", "specifications.md")
    draw = os.path.join(root, "references", "drawings_images")
    mtimes = [os.path.getmtime(os.path.join(r, f)) for r, _, fs in os.walk(root) for f in fs] or [os.path.getmtime(root)]
    fmt = lambda t: datetime.datetime.fromtimestamp(t).strftime("%Y-%m-%d")
    return {
        "folder": folder,
        "project": "_".join(x for x in (friend, core) if x),
        "friend": friend,
        "file_type": ftype,
        "blend": f"blend/{blends[0]}" if blends else "",
        "parts": str(len(parts)),
        "latest_exports": ";".join(f"{k}_{v}" for k, v in sorted(parts.items())) if len(parts) <= 12
                          else f"{len(parts)} parts, highest version {max(parts.values())}",
        "has_specs": "yes" if os.path.exists(spec) else "",
        "has_drawings": "yes" if os.path.isdir(draw) and os.listdir(draw) else "",
        "hardware": ";".join(_spec_hardware_names(spec)) if os.path.exists(spec) else "",
        "created": fmt(min(mtimes)),
        "updated": fmt(max(mtimes)),
    }


def index_projects():
    """Rebuild data/projects.csv from the project folders, and regenerate projects.md. Returns the rows."""
    folders = sorted(d for d in (os.listdir(LIBRARY) if os.path.isdir(LIBRARY) else [])
                     if os.path.isdir(os.path.join(LIBRARY, d)) and d != "data")
    old = {r["folder"]: r for r in read_projects()}
    rows = []
    for f in folders:
        r = _scan_project(f)
        if f in old and old[f].get("created"):
            r["created"] = old[f]["created"]
        rows.append(r)
    os.makedirs(os.path.dirname(PROJECTS_CSV), exist_ok=True)
    try:
        with open(PROJECTS_CSV, "w", newline="", encoding="utf-8-sig") as fh:
            w = csv.DictWriter(fh, fieldnames=PROJECT_COLS)
            w.writeheader()
            w.writerows(rows)
    except PermissionError:
        raise PermissionError("projects.csv is open in another program (e.g. Excel). Close it and try again.")
    _write_projects_md(rows)
    return rows


def read_projects():
    if not os.path.exists(PROJECTS_CSV):
        return []
    with open(PROJECTS_CSV, newline="", encoding="utf-8-sig") as fh:
        return [{c: (r.get(c) or "") for c in PROJECT_COLS} for r in csv.DictReader(fh)]


def find_projects(query=""):
    """Fast search of the project index: every word must appear in the folder, friend, parts, or hardware."""
    rows = read_projects() or index_projects()
    words = [w for w in re.split(r"[\s_]+", clean(query)) if w]
    hits = [r for r in rows if all(w in " ".join(r.values()).lower() for w in words)]
    return "\n".join(f"{r['folder']}: {r['parts']} parts, updated {r['updated']}"
                     + (", specs" if r["has_specs"] else "") for r in hits) or "no matches"


def _write_projects_md(rows):
    lines = ["# Model Library Projects", "",
             f"*Generated from `data/projects.csv` on {datetime.datetime.now():%Y-%m-%d %H:%M}. "
             "Read-only view for people: edits here are overwritten.*", "",
             "| Project folder | Friend | Parts | Specs | Drawings | Hardware | Updated |",
             "|---|---|---|---|---|---|---|"]
    for r in rows:
        lines.append(f"| {r['folder']} | {r['friend']} | {r['parts']} | {r['has_specs']} | {r['has_drawings']} "
                     f"| {r['hardware'].replace(';', ', ')} | {r['updated']} |")
    if not rows:
        lines.append("| | | | | | | |")
    with open(PROJECTS_MD, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")


def resolve_project(query):
    """
    Match a full or partial project name to its folder in model library.
    Returns (folder, candidates): folder is None unless exactly one folder matches.
    """
    folders = sorted(d for d in (os.listdir(LIBRARY) if os.path.isdir(LIBRARY) else [])
                     if os.path.isdir(os.path.join(LIBRARY, d)) and d != "data")
    q = clean(query)
    if q in folders:
        return q, [q]
    words = [w for w in q.split("_") if w]
    hits = [f for f in folders if all(w in f.split("_") or w in f for w in words)]
    return (hits[0] if len(hits) == 1 else None), hits


def cleanup_exports(project=None, ext="stl", dry_run=False):
    """
    Delete every <object>_<n>.<ext> except the highest n for each object.
    project: folder name or part of it; None = every project in model library.
    dry_run=True only lists what would be deleted. Rebuilds the project index afterwards.
    Returns a short report.
    """
    if project:
        folder, hits = resolve_project(project)
        if folder is None:
            return (f"Cleanup: '{project}' matches {len(hits)} projects: " + ", ".join(hits)
                    if hits else f"Cleanup: no project matches '{project}'")
        folders = [folder]
    else:
        folders = sorted(d for d in (os.listdir(LIBRARY) if os.path.isdir(LIBRARY) else [])
                         if os.path.isdir(os.path.join(LIBRARY, d)) and d != "data")
    ext = clean(ext)
    out, total = [], 0
    for f in folders:
        d = os.path.join(LIBRARY, f, ext)
        if not os.path.isdir(d):
            continue
        versions = {}
        for name in os.listdir(d):
            m = re.match(r"^(.*)_(\d+)\.%s$" % re.escape(ext), name, re.I)
            if m:
                versions.setdefault(m.group(1), []).append((int(m.group(2)), name))
        old = sorted(name for vs in versions.values() for n, name in sorted(vs)[:-1])
        if not old:
            continue
        for name in old:
            if not dry_run:
                os.remove(os.path.join(d, name))
        total += len(old)
        keep = sorted(max(vs)[1] for vs in versions.values())
        out.append(f"  {f}: {'would delete' if dry_run else 'deleted'} {len(old)} "
                   f"({', '.join(old)}); kept {', '.join(keep)}")
    if total and not dry_run:
        index_projects()
    head = f"Cleanup{' (preview)' if dry_run else ''}: {total} old .{ext} file{'s' if total != 1 else ''}"
    return "\n".join([head] + (out or ["  nothing to delete"]))


def cleanup_references(project=None, keep=1, dry_run=False, exts=("png", "svg", "jpg", "jpeg")):
    """
    Delete old generated files in references/, keeping the newest `keep` of each
    series (`<description>_<n>.<ext>`, as `next_reference_path` names them).

    These are Claude's outputs - sketches, renders, marked-up question images.
    They are reproducible from `part_spec.json` and `specifications.md`, which is
    why they can be thrown away; they are also the biggest thing in the project
    by disk (a marked-up photo runs to several MB, a generated sketch to ~10 KB).

    Never touches: `references/drawings_images/` (the user's own photos and
    drawings, which are evidence and cannot be regenerated), `specifications.md`,
    `part_spec.json`, or any file that does not end in `_<n>.<ext>`.

    project: folder name or part of it; None = every project in model library.
    dry_run=True only lists what would go. Returns a short report.
    """
    if project:
        folder, hits = resolve_project(project)
        if folder is None:
            return (f"Reference cleanup: '{project}' matches {len(hits)} projects: " + ", ".join(hits)
                    if hits else f"Reference cleanup: no project matches '{project}'")
        folders = [folder]
    else:
        folders = sorted(d for d in (os.listdir(LIBRARY) if os.path.isdir(LIBRARY) else [])
                         if os.path.isdir(os.path.join(LIBRARY, d)) and d != "data")
    keep = max(1, int(keep))
    pattern = r"^(.*)_(\d+)\.(%s)$" % "|".join(re.escape(e.lower().lstrip(".")) for e in exts)
    out, total, freed = [], 0, 0
    for f in folders:
        d = os.path.join(LIBRARY, f, "references")
        if not os.path.isdir(d):
            continue
        series = {}
        for name in os.listdir(d):
            if not os.path.isfile(os.path.join(d, name)):
                continue                                  # drawings_images/ and any other folder
            m = re.match(pattern, name, re.I)
            if m:
                series.setdefault((m.group(1), m.group(3).lower()), []).append((int(m.group(2)), name))
        old = sorted(name for vs in series.values() for n, name in sorted(vs)[:-keep])
        if not old:
            continue
        for name in old:
            path = os.path.join(d, name)
            freed += os.path.getsize(path)
            if not dry_run:
                os.remove(path)
        total += len(old)
        kept = sorted(name for vs in series.values() for n, name in sorted(vs)[-keep:])
        out.append(f"  {f}: {'would delete' if dry_run else 'deleted'} {len(old)} "
                   f"({', '.join(old)}); kept {', '.join(kept)}")
    head = (f"Reference cleanup{' (preview)' if dry_run else ''}: {total} file"
            f"{'s' if total != 1 else ''}, {freed / 1048576.0:.1f} MB"
            f"{'' if dry_run else ' freed'}; keeping the newest {keep} of each")
    return "\n".join([head] + (out or ["  nothing to delete"]))


def next_export_path(root, object_name, ext="stl"):
    """Next unused <type>/<object>_<n>.<ext>. Strips a prod_ prefix."""
    obj = clean(object_name)
    if obj.startswith("prod_"):
        obj = obj[len("prod_"):]
    folder = os.path.join(root, clean(ext))
    os.makedirs(folder, exist_ok=True)
    n = 1
    while os.path.exists(os.path.join(folder, "%s_%d.%s" % (obj, n, ext))):
        n += 1
    return os.path.join(folder, "%s_%d.%s" % (obj, n, ext))


def next_reference_path(root, description, ext="png"):
    """Next unused references/<description>_<n>.<ext> for Claude's outputs
    (previews, renders, screenshots, reports). Never overwrites."""
    name = clean(description)
    ext = ext.lower().lstrip(".")
    folder = os.path.join(root, "references")
    os.makedirs(folder, exist_ok=True)
    n = 1
    while os.path.exists(os.path.join(folder, "%s_%d.%s" % (name, n, ext))):
        n += 1
    return os.path.join(folder, "%s_%d.%s" % (name, n, ext))


def next_backup_name(object_name, change, existing_names=()):
    """
    back_<object>_<x.y.z>. change: 'big' bumps z, 'hard' (hard-to-undo) bumps y.
    Starts from the highest existing version for this object; if the result is
    already taken, bump x (per 01_blender_basics.md, section 4).
    """
    obj = clean(object_name)
    for pre in ("prod_", "back_"):
        if obj.startswith(pre):
            obj = obj[len(pre):]
    pat = re.compile(r"^back_%s_(\d+)\.(\d+)\.(\d+)$" % re.escape(obj))
    taken = {tuple(map(int, m.groups())) for m in (pat.match(n) for n in existing_names) if m}
    x, y, z = max(taken) if taken else (0, 0, 0)
    if change == "big":
        z += 1
    elif change == "hard":
        y += 1
    else:
        raise ValueError("change must be 'big' or 'hard'")
    while (x, y, z) in taken:
        x += 1
    return "back_%s_%d.%d.%d" % (obj, x, y, z)


# ---------- matching drawing titles to existing projects / parts ----------

FILE_TYPES = ("stl", "3mf")


def _core_project(folder):
    """<friend>_<type>_<name> or <type>_<name> -> (friend, name)."""
    parts = clean(folder).split("_")
    for i, p in enumerate(parts):
        if p in FILE_TYPES:
            return "_".join(parts[:i]), "_".join(parts[i + 1:])
    return "", "_".join(parts)


def _initials(name):
    return "".join(w[0] for w in name.split("_") if w)


def _score(title, name):
    """0..1 similarity between a cleaned title and a cleaned name, counting abbreviations."""
    import difflib
    if not title or not name:
        return 0.0
    if title == name:
        return 1.0
    t_words, n_words = title.split("_"), name.split("_")
    best = difflib.SequenceMatcher(None, title, name).ratio()
    # abbreviation: "lbl" -> letter_board_letters, "lb_letters" -> letter_board_letters
    if title.replace("_", "") == _initials(name):
        best = max(best, 0.9)
    i = 0
    ok = True
    for w in t_words:
        # each title word must be a word of the name, a prefix of one, or the initials of a run of words
        matched = False
        for j in range(i, len(n_words)):
            run = "".join(x[0] for x in n_words[i:j + 1])
            if n_words[j].startswith(w) and j == i or run == w:
                i = j + 1; matched = True; break
        if not matched:
            ok = False; break
    if ok and t_words:
        best = max(best, 0.88 if i == len(n_words) else 0.75)
    # all title words appear in the name (subset)
    if set(t_words) <= set(n_words):
        best = max(best, 0.8)
    # the name is part of the title ("base plate" vs "base")
    elif set(n_words) <= set(t_words):
        best = max(best, 0.7)
    return round(best, 3)


def match_title(title, kind="project", names=None, friend=None):
    """
    Compare a drawing title with existing projects (kind="project") or parts (kind="part").
    names: for parts, the object names in the open .blend (prod_ prefix is ignored);
           for projects, defaults to the folders in model library.
    Returns {"exact": name or None, "likely": [(name, score)], "possible": [(name, score)], "decision": ...}
    decision: "use_existing", "ask", or "new".
    """
    t = clean(title)
    if kind == "project":
        folders = names if names is not None else [r["folder"] for r in (read_projects() or index_projects())]
        cands = []
        for f in folders:
            fr, core = _core_project(f)
            if friend and fr and clean(friend) != fr:
                continue
            tt = t[len(fr) + 1:] if fr and t.startswith(fr + "_") else t
            cands.append((f, _score(tt, core)))
    else:
        cands = []
        for n in (names or []):
            core = clean(n)
            core = core[5:] if core.startswith("prod_") else core
            cands.append((n, _score(t, core)))
    cands.sort(key=lambda x: -x[1])
    exact = next((n for n, sc in cands if sc == 1.0), None)
    likely = [(n, sc) for n, sc in cands if 0.85 <= sc < 1.0]
    possible = [(n, sc) for n, sc in cands if 0.6 <= sc < 0.85]
    if exact:
        decision = "use_existing"
    elif len(likely) == 1 and not possible:
        decision = "use_existing"
    elif likely or possible:
        decision = "ask"
    else:
        decision = "new"
    return {"exact": exact, "likely": likely, "possible": possible, "decision": decision}


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("usage: paths.py <name> [friend] [type]")
    else:
        a = sys.argv[1:] + [None, "stl"][len(sys.argv) - 2:]
        print(create_project(a[0], a[1], a[2] or "stl"))
