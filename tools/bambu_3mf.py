"""
Writes real Bambu Studio project .3mf files — the kind Studio opens with its
presets, filament assignment and per-object settings intact, not the
"not from Bambu Lab, load geometry data only" kind.

Pure standard library. Run inside Blender, a plain Python 3, or anywhere:

    import os, runpy
    b3 = runpy.run_path(os.path.join(BONFIRE, "tools", "bambu_3mf.py"))
    b3["write_project"](out_path, items, project_settings)

What makes Studio treat the file as a project (read off BambuStudio's own
bbs_3mf.cpp / Plater.cpp):

  * `_rels/.rels` must exist and point at /3D/3dmodel.model — without it the
    importer returns false before reading anything else.
  * `3D/3dmodel.model` must carry <metadata name="Application">BambuStudio-…
    That single string is what sets the "this is a Bambu file" flag.
  * `Metadata/project_settings.config` must be present and non-empty, must name
    a real BBL `printer_model`, and must have a non-empty `filament_colour`
    (an empty one throws rather than warns).

Two conventions differ between the files, which is easy to get wrong:
  * 3D/3dmodel.model transforms: 12 floats, column-major.
  * model_settings.config `matrix`: 16 floats, row-major.
"""
import datetime
import os
import struct
import json
import math
import zlib
import zipfile

# Keep this at or below the installed Studio's version: a HIGHER major number
# sends the importer down the "project from a newer Studio" path and it loads
# geometry only. 1.9.x is the current P1S-era line, so this is safe; when a
# preset template is present its own Application string is used instead.
APPLICATION = "BambuStudio-01.09.00.00"
BBS_3MF_VERSION = "1"

BED_SIZE_MM = 256.0          # P1S / X1 family, from fdm_bbl_3dp_001_common
BED_HEIGHT_MM = 256.0

CONTENT_TYPES = (
    '<?xml version="1.0" encoding="UTF-8"?>\n'
    '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">\n'
    ' <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>\n'
    ' <Default Extension="model" ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/>\n'
    ' <Default Extension="png" ContentType="image/png"/>\n'
    ' <Default Extension="gcode" ContentType="text/x.gcode"/>\n'
    '</Types>'
)

RELS = (
    '<?xml version="1.0" encoding="UTF-8"?>\n'
    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">\n'
    ' <Relationship Target="/3D/3dmodel.model" Id="rel-1" '
    'Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/>\n'
    ' <Relationship Target="/Metadata/plate_1.png" Id="rel-2" '
    'Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/thumbnail"/>\n'
    ' <Relationship Target="/Metadata/plate_1.png" Id="rel-4" '
    'Type="http://schemas.bambulab.com/package/2021/cover-thumbnail-middle"/>\n'
    '<Relationship Target="/Metadata/plate_1_small.png" Id="rel-5" '
    'Type="http://schemas.bambulab.com/package/2021/cover-thumbnail-small"/>\n'
    '</Relationships>'
)


def _esc(text):
    return (str(text).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def _num(v):
    s = "%.6f" % float(v)
    s = s.rstrip("0").rstrip(".")
    return s if s not in ("", "-0") else "0"


def _translation(dx, dy, dz):
    """12-float column-major transform string for 3dmodel.model."""
    return " ".join([_num(1), _num(0), _num(0),
                     _num(0), _num(1), _num(0),
                     _num(0), _num(0), _num(1),
                     _num(dx), _num(dy), _num(dz)])


IDENTITY_MATRIX_16 = "1 0 0 0 0 1 0 0 0 0 1 0 0 0 0 1"

# Bambu Studio lays plates out in a grid in one shared space, each plate a
# bed's width plus a fifth apart (PartPlate.hpp LOGICAL_PART_PLATE_GAP = 1/5,
# PartPlateList::compute_origin): plate i sits at column i % cols, row
# i // cols, rows running towards -y, with cols = ceil(sqrt(plate count)).
PLATE_GAP_FRACTION = 1.0 / 5.0


def plate_columns(count):
    value = math.sqrt(count)
    rounded = round(value)
    return int(rounded + 1 if value > rounded else rounded) or 1


def plate_origin(index, count, bed=BED_SIZE_MM):
    """Where plate `index` (0-based) starts in the shared space."""
    cols = plate_columns(count)
    stride = bed * (1.0 + PLATE_GAP_FRACTION)
    return ((index % cols) * stride, -(index // cols) * stride)


def _instances(item):
    """(x, y, z, plate) for each instance; plate defaults to 0."""
    for inst in item["instances"]:
        if len(inst) == 4:
            yield tuple(inst)
        else:
            yield (inst[0], inst[1], inst[2], 0)


def plate_count(items):
    return 1 + max((p for it in items for *_, p in _instances(it)), default=0)


# ── the model file ───────────────────────────────────────────────────

def _model_file(items, title, application=APPLICATION):
    """items: list of dicts with keys mesh, name, instances (list of (x,y,z))."""
    today = datetime.date.today().isoformat()
    out = ['<?xml version="1.0" encoding="UTF-8"?>',
           '<model unit="millimeter" xml:lang="en-US"'
           ' xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02"'
           ' xmlns:BambuStudio="http://schemas.bambulab.com/package/2021">',
           ' <metadata name="Application">%s</metadata>' % application,
           ' <metadata name="BambuStudio:3mfVersion">%s</metadata>' % BBS_3MF_VERSION,
           ' <metadata name="CreationDate">%s</metadata>' % today,
           ' <metadata name="ModificationDate">%s</metadata>' % today,
           ' <metadata name="Title">%s</metadata>' % _esc(title),
           ' <metadata name="Designer"></metadata>',
           ' <metadata name="Description"></metadata>',
           ' <metadata name="Copyright"></metadata>',
           ' <metadata name="License"></metadata>',
           ' <resources>']

    build = []
    next_id = 1
    for item in items:
        mesh = item["mesh"]
        mesh_id = next_id
        out.append('  <object id="%d" type="model">' % mesh_id)
        out.append('   <mesh>')
        out.append('    <vertices>')
        for x, y, z in mesh["verts"]:
            out.append('     <vertex x="%s" y="%s" z="%s"/>'
                       % (_num(x), _num(y), _num(z)))
        out.append('    </vertices>')
        out.append('    <triangles>')
        for a, b, c in mesh["tris"]:
            out.append('     <triangle v1="%d" v2="%d" v3="%d"/>' % (a, b, c))
        out.append('    </triangles>')
        out.append('   </mesh>')
        out.append('  </object>')

        container_id = mesh_id + 1
        out.append('  <object id="%d" type="model">' % container_id)
        out.append('   <components>')
        out.append('    <component objectid="%d" transform="%s"/>'
                   % (mesh_id, _translation(0, 0, 0)))
        out.append('   </components>')
        out.append('  </object>')

        item["_mesh_id"] = mesh_id
        item["_object_id"] = container_id
        for pos in _instances(item):
            build.append((container_id, pos))
        next_id = container_id + 1

    count = plate_count(items)
    out.append(' </resources>')
    out.append(' <build>')
    for oid, (x, y, z, plate) in build:
        ox, oy = plate_origin(plate, count)
        out.append('  <item objectid="%d" transform="%s" printable="1"/>'
                   % (oid, _translation(x + ox, y + oy, z)))
    out.append(' </build>')
    out.append('</model>')
    return "\n".join(out)


# ── per-object settings and the plate ────────────────────────────────

def _model_settings(items, plate):
    out = ['<?xml version="1.0" encoding="UTF-8"?>', '<config>']
    for item in items:
        out.append('  <object id="%d">' % item["_object_id"])
        out.append('    <metadata key="name" value="%s"/>' % _esc(item["name"]))
        for key, value in sorted(item.get("settings", {}).items()):
            out.append('    <metadata key="%s" value="%s"/>'
                       % (_esc(key), _esc(value)))
        out.append('    <metadata face_count="%d"/>' % len(item["mesh"]["tris"]))
        out.append('    <part id="%d" subtype="normal_part">' % item["_mesh_id"])
        out.append('      <metadata key="name" value="%s"/>' % _esc(item["name"]))
        out.append('      <metadata key="matrix" value="%s"/>' % IDENTITY_MATRIX_16)
        src = item.get("source_file", item["name"])
        out.append('      <metadata key="source_file" value="%s"/>' % _esc(src))
        out.append('      <metadata key="source_object_id" value="0"/>')
        out.append('      <metadata key="source_volume_id" value="0"/>')
        out.append('      <metadata key="source_offset_x" value="0"/>')
        out.append('      <metadata key="source_offset_y" value="0"/>')
        out.append('      <metadata key="source_offset_z" value="0"/>')
        out.append('      <mesh_stat face_count="%d" edges_fixed="0" '
                   'degenerate_facets="0" facets_removed="0" '
                   'facets_reversed="0" backwards_edges="0"/>'
                   % len(item["mesh"]["tris"]))
        out.append('    </part>')
        out.append('  </object>')

    # One <plate> per plate, listing the instances on it. instance_id is the
    # instance's position among its object's build items, in file order.
    count = plate_count(items)
    on_plate = [[] for _ in range(count)]
    identify = 100
    for item in items:
        for n, (_, _, _, p) in enumerate(_instances(item)):
            on_plate[p].append((item["_object_id"], n, identify))
            identify += 1
    for p in range(count):
        out.append('  <plate>')
        out.append('    <metadata key="plater_id" value="%d"/>' % (p + 1))
        name = plate.get("names", {}).get(p + 1, plate.get("name", "") if p == 0 else "")
        out.append('    <metadata key="plater_name" value="%s"/>' % _esc(name))
        out.append('    <metadata key="locked" value="false"/>')
        # Bed type and print sequence live in project_settings.config; Studio
        # does not repeat them on the plate of an unsliced project.
        for oid, n, ident in on_plate[p]:
            out.append('    <model_instance>')
            out.append('      <metadata key="object_id" value="%d"/>' % oid)
            out.append('      <metadata key="instance_id" value="%d"/>' % n)
            out.append('      <metadata key="identify_id" value="%d"/>' % ident)
            out.append('    </model_instance>')
        out.append('  </plate>')
    out.append('  <assemble>')
    out.append('  </assemble>')
    out.append('</config>')
    return "\n".join(out)


# ── a placeholder plate thumbnail, so the relationships resolve ──────

def _png(width, height, rgb=(30, 32, 36)):
    """A tiny solid-colour PNG, built with zlib only."""
    raw = b"".join(b"\x00" + bytes(rgb) * width for _ in range(height))

    def chunk(tag, data):
        body = tag + data
        return (struct.pack(">I", len(data)) + body
                + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF))

    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header)
            + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))


# ── writing ──────────────────────────────────────────────────────────

def write_project(path, items, project_settings, plate=None, title=None,
                  application=None):
    """
    items: [{"mesh": mesh, "name": str, "instances": [(x, y, z), ...] or
             [(x, y, z, plate), ...] with plate 0-based (x, y are that
             plate's own coordinates; the offset is added here),
             "settings": {"extruder": "1", "enable_support": "1", ...},
             "source_file": str}]
           Coordinates are absolute plate coordinates: plate 1 runs 0..256 in
           both x and y, so a centred part sits at (128, 128).
    project_settings: dict of strings (see bambu_presets.py).
    """
    if not items:
        raise ValueError("nothing to place on the plate")
    title = title or os.path.splitext(os.path.basename(path))[0]
    plate = plate or {}

    settings = dict(project_settings)
    if not settings.get("filament_colour"):
        raise ValueError("project_settings needs a non-empty filament_colour — "
                         "Bambu Studio throws without it")
    if not settings.get("printer_model"):
        raise ValueError("project_settings needs printer_model, e.g. "
                         "'Bambu Lab P1S'")

    model_xml = _model_file(items, title, application or APPLICATION)
    config_xml = _model_settings(items, plate)
    settings_json = json.dumps(settings, indent=4)

    folder = os.path.dirname(os.path.abspath(path))
    if folder:
        os.makedirs(folder, exist_ok=True)
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("3D/3dmodel.model", model_xml)
        z.writestr("Metadata/project_settings.config", settings_json)
        z.writestr("Metadata/model_settings.config", config_xml)
        for p in range(1, plate_count(items) + 1):
            z.writestr("Metadata/plate_%d.png" % p, _png(512, 512))
            z.writestr("Metadata/plate_%d_small.png" % p, _png(128, 128))
        z.writestr("[Content_Types].xml", CONTENT_TYPES)
        z.writestr("_rels/.rels", RELS)
    return path


def read_project_settings(path):
    """Pull Metadata/project_settings.config out of an existing Bambu 3MF.
    This is how a template saved from Bambu Studio becomes our preset base."""
    with zipfile.ZipFile(path) as z:
        if "Metadata/project_settings.config" not in z.namelist():
            raise ValueError("%s has no project_settings.config — it isn't a "
                             "Bambu project file" % os.path.basename(path))
        return json.loads(z.read("Metadata/project_settings.config"))


def read_application(path):
    """The Application string a Bambu 3MF was written with, e.g.
    'BambuStudio-01.09.07.52'. Reusing the template's keeps our files from
    claiming a newer Studio than the one installed."""
    with zipfile.ZipFile(path) as z:
        name = next((n for n in z.namelist() if n.endswith("3dmodel.model")), None)
        if not name:
            return ""
        head = z.read(name)[:4000].decode("utf-8", "replace")
        marker = '<metadata name="Application">'
        if marker not in head:
            return ""
        return head.split(marker, 1)[1].split("<", 1)[0]


def describe(path):
    """What's inside a 3MF, and whether Studio will treat it as a project."""
    with zipfile.ZipFile(path) as z:
        names = z.namelist()
        model = next((n for n in names if n.endswith("3dmodel.model")), None)
        app = ""
        if model:
            head = z.read(model)[:4000].decode("utf-8", "replace")
            marker = '<metadata name="Application">'
            if marker in head:
                app = head.split(marker, 1)[1].split("<", 1)[0]
        has_settings = "Metadata/project_settings.config" in names
        printer = ""
        if has_settings:
            try:
                printer = json.loads(
                    z.read("Metadata/project_settings.config")).get(
                        "printer_model", "")
            except Exception:
                printer = "(unreadable)"
    return {
        "entries": sorted(names),
        "application": app,
        "is_bambu_project": app.startswith("BambuStudio-") and has_settings
                            and bool(printer),
        "has_project_settings": has_settings,
        "has_model_settings": "Metadata/model_settings.config" in names,
        "has_rels": "_rels/.rels" in names,
        "printer_model": printer,
        "sliced": any(n.endswith(".gcode") for n in names),
    }
