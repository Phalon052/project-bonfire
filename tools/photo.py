#!/usr/bin/env python3
"""
Project Bonfire — measure from photos with ArUco markers.

Four printed ArUco markers sit at known, recorded spots on the cutting mat.
In a photo of the part lying among them, the markers give a true planar
homography: the photo is rectified to a straight-down view where every pixel
is the same size in millimetres, and the scale comes from the markers — never
from the part's own stated size.

    python tools/photo.py sheet [out.pdf] [--a4]      # the marker sheet to print
    python tools/photo.py layout                      # show the recorded layout
    python tools/photo.py layout --width 400 --height 300 [--plane 0]
    python tools/photo.py rectify <photo.jpg> [--ppmm 10]
    python tools/photo.py measure <photo_rectified.json> x1,y1 x2,y2 [...]

The layout (dictionary, IDs, marker size, where each marker's centre sits on
the mat, and the height of the marker plane) is tools/photo_markers.json —
committed, so every session measures the same way.

Needs: python -m pip install opencv-python numpy
"""
import json
import math
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
LAYOUT_PATH = os.path.join(_HERE, "photo_markers.json")

# ID 0 top-left, 1 top-right, 2 bottom-right, 3 bottom-left, seen from the
# bottom edge of the mat. x runs right, y runs down (like the picture), in mm,
# with ID 0's centre at (0, 0).
DEFAULT_LAYOUT = {
    "dictionary": "DICT_4X4_50",
    "marker_mm": 50.0,
    "width_mm": 400.0,       # centre of ID 0 to centre of ID 1 (and 3 to 2)
    "height_mm": 300.0,      # centre of ID 0 to centre of ID 3 (and 1 to 2)
    "plane_mm": 0.0,         # marker surface above the mat (a shim raises it)
    "margin_mm": 40.0,       # rectified picture reaches this far past the centres
    "markers": {"0": [0, 0], "1": ["W", 0], "2": ["W", "H"], "3": [0, "H"]},
    "camera": None,          # optional {"matrix": 3x3, "dist": [...]} from calibration
}
PPMM = 10.0                  # rectified pixels per mm (0.1 mm per pixel)
MAX_PIXELS = 80_000_000
RMS_WARN_MM = 0.5            # corner fit worse than this: something moved or bent
SIZE_WARN = 0.01             # marker size off by more than 1 %: print scale
TILT_WARN_DEG = 1.0          # a marker turned off the mat grid


class PhotoError(Exception):
    """Something about the photo or the markers, in words worth showing."""


def _cv():
    try:
        import cv2
        import numpy
    except ImportError:
        raise PhotoError("Measuring photos needs OpenCV: run "
                         "`python -m pip install opencv-python numpy`.")
    if not hasattr(cv2, "aruco"):
        raise PhotoError("This OpenCV has no ArUco module: run "
                         "`python -m pip install --upgrade opencv-python`.")
    return cv2, numpy


# ------------------------------------------------------------------ layout

def load_layout(path=LAYOUT_PATH):
    lay = dict(DEFAULT_LAYOUT)
    if os.path.isfile(path):
        with open(path, encoding="utf-8") as fh:
            lay.update(json.load(fh))
    return lay


def save_layout(lay, path=LAYOUT_PATH):
    keep = {k: lay[k] for k in DEFAULT_LAYOUT if k in lay}
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(keep, fh, indent=2)
        fh.write("\n")
    return path


def marker_centres(lay):
    """{id: (x, y)} in mm, with "W"/"H" replaced by the recorded spacing."""
    sub = {"W": float(lay["width_mm"]), "H": float(lay["height_mm"])}
    out = {}
    for k, (x, y) in lay["markers"].items():
        out[int(k)] = (sub.get(x, x) if isinstance(x, str) else float(x),
                       sub.get(y, y) if isinstance(y, str) else float(y))
    return out


def marker_corners_mm(centre, size):
    """A marker's corners in ArUco's order (its own top-left, top-right,
    bottom-right, bottom-left) when it lies upright on the mat."""
    cx, cy = centre
    h = size / 2.0
    return [(cx - h, cy - h), (cx + h, cy - h), (cx + h, cy + h), (cx - h, cy + h)]


# ------------------------------------------------------------ marker sheet

_PAGES = {"letter": (215.9, 279.4), "a4": (210.0, 297.0)}


def _marker_bits(dictionary, marker_id):
    """The marker as rows of 0/1 (1 = black), border included."""
    cv2, np = _cv()
    d = cv2.aruco.getPredefinedDictionary(getattr(cv2.aruco, dictionary))
    n = d.markerSize + 2
    img = cv2.aruco.generateImageMarker(d, marker_id, n, borderBits=1)
    return [[1 if v < 128 else 0 for v in row] for row in img]


def _pdf(page_w_mm, page_h_mm, ops):
    """A one-page vector PDF. `ops` is the content stream in mm (converted
    to points here by a scale in the page's matrix), Helvetica as /F1."""
    pt = 72.0 / 25.4
    content = ("%.6f 0 0 %.6f 0 0 cm\n" % (pt, pt) + ops).encode("latin-1")
    objs = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        ("<< /Type /Page /Parent 2 0 R /MediaBox [0 0 %.2f %.2f] "
         "/Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>"
         % (page_w_mm * pt, page_h_mm * pt)).encode(),
        b"<< /Length %d >>\nstream\n" % len(content) + content + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for i, body in enumerate(objs, 1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % i + body + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1)
    for off in offsets:
        out += b"%010d 00000 n \n" % off
    out += (b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n"
            % (len(objs) + 1, xref))
    return bytes(out)


def _text(x, y, size, s):
    s = s.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    # text is drawn in mm space, so the font size is in mm too
    return "BT /F1 %.3f Tf %.3f %.3f Td (%s) Tj ET\n" % (size, x, y, s)


def marker_sheet(out_path, lay=None, page="letter"):
    """
    One page with the four markers, ready to print at 100 % ("Actual size",
    not "Fit to page"). Each tile has a dashed cut line and centre lines
    through its white border, to set the marker's centre on a grid crossing
    of the mat; a 100 mm bar checks the printer didn't scale the page.
    """
    lay = lay or load_layout()
    size = float(lay["marker_mm"])
    quiet = max(8.0, size * 0.2)                  # white border round each marker
    tile = size + 2 * quiet
    pw, ph = _PAGES[page]
    names = {0: "top-left", 1: "top-right", 2: "bottom-right", 3: "bottom-left"}
    ids = sorted(marker_centres(lay))
    gap = 6.0
    x0 = (pw - (2 * tile + gap)) / 2.0
    top = ph - 30.0                               # PDF y runs up from the bottom
    ops = ["0 g\n"]
    ops.append(_text(x0, ph - 15, 4.2, "Project Bonfire - photo markers"))
    ops.append(_text(x0, ph - 21, 2.8, "%s, IDs %s, %g mm markers. Print at 100%% "
                     "(Actual size) - not Fit to page." % (lay["dictionary"],
                     ", ".join(str(i) for i in ids), size)))
    for n, mid in enumerate(ids[:4]):
        col, row = n % 2, n // 2
        # tiles in mat order: 0 top-left, 1 top-right, then 3 bottom-left, 2 bottom-right
        if mid in (2, 3):
            col = 1 if mid == 2 else 0
        tx = x0 + col * (tile + gap)
        ty = top - (row + 1) * tile - row * gap
        ops.append("q 0.5 g 0.2 w [2 1.5] 0 d %.3f %.3f %.3f %.3f re S Q\n" % (tx, ty, tile, tile))
        mx, my = tx + quiet, ty + quiet
        bits = _marker_bits(lay["dictionary"], mid)
        cell = size / len(bits)
        for r, line in enumerate(bits):
            for c, v in enumerate(line):
                if v:
                    ops.append("%.4f %.4f %.4f %.4f re f\n"
                               % (mx + c * cell, my + size - (r + 1) * cell, cell, cell))
        cx, cy = mx + size / 2, my + size / 2
        ops.append("q 0.15 w\n")
        for a, b in (((tx, cy), (mx - 1, cy)), ((mx + size + 1, cy), (tx + tile, cy)),
                     ((cx, ty), (cx, my - 1)), ((cx, my + size + 1), (cx, ty + tile))):
            ops.append("%.3f %.3f m %.3f %.3f l S\n" % (a[0], a[1], b[0], b[1]))
        ops.append("Q\n")
        ops.append(_text(tx + 1.5, ty + 1.5, 2.6, "ID %d  %s" % (mid, names.get(mid, ""))))
        ops.append(_text(tx + 1.5, ty + tile - 3.6, 2.2, "^ top of mat"))
    # 100 mm check bar
    by = top - 2 * tile - gap - 16
    ops.append("q 0.3 w %.3f %.3f m %.3f %.3f l S\n" % (x0, by, x0 + 100, by))
    for i in range(11):
        ops.append("%.3f %.3f m %.3f %.3f l S\n" % (x0 + 10 * i, by, x0 + 10 * i,
                                                    by + (4 if i % 5 == 0 else 2)))
    ops.append("Q\n")
    ops.append(_text(x0, by - 5, 2.8, "Measure this bar: it must be 100 mm end to end, and each "
                     "marker's black square %g mm." % size))
    ops.append(_text(x0, by - 10, 2.8, "Cut on the dashed lines. Lay each tile flat with its centre "
                     "lines on grid lines of the mat, in the corners named above."))
    ops.append(_text(x0, by - 14, 2.8, "Then record the centre-to-centre spacing: "
                     "python tools/photo.py layout --width <mm> --height <mm>"))
    data = _pdf(pw, ph, "".join(ops))
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    with open(out_path, "wb") as fh:
        fh.write(data)
    return {"ok": True, "file": os.path.abspath(out_path), "page": page,
            "marker_mm": size, "ids": ids[:4], "dictionary": lay["dictionary"]}


# ------------------------------------------------------------- rectifying

def detect_markers(image, lay):
    """{id: 4x2 corners in picture pixels} for the layout's markers."""
    cv2, np = _cv()
    d = cv2.aruco.getPredefinedDictionary(getattr(cv2.aruco, lay["dictionary"]))
    params = cv2.aruco.DetectorParameters()
    params.cornerRefinementMethod = cv2.aruco.CORNER_REFINE_SUBPIX
    grey = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if image.ndim == 3 else image
    corners, ids, _ = cv2.aruco.ArucoDetector(d, params).detectMarkers(grey)
    wanted = marker_centres(lay)
    found = {}
    for c, i in zip(corners, [] if ids is None else ids.flatten()):
        if int(i) in wanted and int(i) not in found:
            found[int(i)] = c.reshape(4, 2).astype(float)
    return found


def _fit(found, lay):
    """The homography picture → mm, taking each marker's quarter turn from the
    data (a tile laid sideways still fits), from all the markers' corners."""
    cv2, np = _cv()
    centres = marker_centres(lay)
    size = float(lay["marker_mm"])
    ids = sorted(found)
    img_c = np.array([found[i].mean(axis=0) for i in ids], np.float64)
    world_c = np.array([centres[i] for i in ids], np.float64)
    if len(ids) >= 4:
        rough = cv2.getPerspectiveTransform(img_c[:4].astype(np.float32),
                                            world_c[:4].astype(np.float32)) \
            if len(ids) == 4 else cv2.findHomography(img_c, world_c)[0]
    else:
        a = cv2.getAffineTransform(img_c.astype(np.float32), world_c.astype(np.float32))
        rough = np.vstack([a, [0, 0, 1]])
    turns, img_pts, world_pts = {}, [], []
    for i in ids:
        seen = cv2.perspectiveTransform(found[i].reshape(-1, 1, 2), rough).reshape(4, 2)
        ideal = np.array(marker_corners_mm(centres[i], size))
        best = min(range(4), key=lambda k: np.linalg.norm(np.roll(ideal, -k, axis=0) - seen))
        turns[i] = best
        img_pts.append(found[i])
        world_pts.append(np.roll(ideal, -best, axis=0))
    img_pts = np.vstack(img_pts)
    world_pts = np.vstack(world_pts)
    H, _ = cv2.findHomography(img_pts, world_pts, 0)
    mapped = cv2.perspectiveTransform(img_pts.reshape(-1, 1, 2), H).reshape(-1, 2)
    err = np.linalg.norm(mapped - world_pts, axis=1)
    return H, turns, mapped, world_pts, err


def _checks(found, mapped, lay):
    """Per-marker size and turn off the grid, measured in the rectified plane."""
    size = float(lay["marker_mm"])
    out = {}
    for n, i in enumerate(sorted(found)):
        q = mapped[4 * n:4 * n + 4]
        sides = [math.dist(q[k], q[(k + 1) % 4]) for k in range(4)]
        dx, dy = q[1][0] - q[0][0], q[1][1] - q[0][1]
        ang = math.degrees(math.atan2(dy, dx))
        tilt = (ang + 45) % 90 - 45
        out[i] = {"size_mm": round(sum(sides) / 4, 2), "tilt_deg": round(tilt, 2)}
    return out


def to_mm(H, points):
    """Picture pixels → mm on the marker plane (ID 0's centre is 0, 0)."""
    cv2, np = _cv()
    pts = np.array(points, np.float64).reshape(-1, 1, 2)
    return [tuple(round(float(v), 2) for v in p)
            for p in cv2.perspectiveTransform(pts, np.array(H, np.float64)).reshape(-1, 2)]


def _grid(img, ppmm, origin, step=10, major=50):
    """Millimetre grid over the rectified picture: fine lines every `step`,
    strong lines and labels every `major`, 0 at ID 0's centre."""
    cv2, np = _cv()
    over = img.copy()
    h, w = img.shape[:2]
    ox, oy = origin
    for axis, extent, start in ((0, w, ox), (1, h, oy)):
        v = math.ceil(start / step) * step
        while (v - start) * ppmm < extent:
            p = int(round((v - start) * ppmm))
            strong = v % major == 0
            colour = (255, 0, 255) if strong else (255, 200, 0)
            thick = max(1, int(ppmm / 10)) * (2 if strong else 1)
            if axis == 0:
                cv2.line(over, (p, 0), (p, h - 1), colour, thick)
            else:
                cv2.line(over, (0, p), (w - 1, p), colour, thick)
            v += step
    out = cv2.addWeighted(over, 0.45, img, 0.55, 0)
    fs = max(0.6, ppmm / 6.0)
    lw = max(1, int(fs * 1.5))
    for axis, extent, start in ((0, w, ox), (1, h, oy)):
        v = math.ceil(start / major) * major
        while (v - start) * ppmm < extent:
            p = int(round((v - start) * ppmm))
            pos = (p + 6, int(30 * fs)) if axis == 0 else (6, p - 8)
            cv2.putText(out, "%g" % v, pos, cv2.FONT_HERSHEY_SIMPLEX, fs, (0, 0, 0), lw * 4)
            cv2.putText(out, "%g" % v, pos, cv2.FONT_HERSHEY_SIMPLEX, fs, (255, 255, 255), lw)
            v += major
    return out


def rectify(photo, out_dir=None, ppmm=PPMM, lay=None, grid=True, part_height_mm=None):
    """
    Rectify `photo` to a straight-down view of the marker plane.

    Writes beside the photo (or in out_dir):
      <name>_rectified.png        ppmm pixels per mm, x right / y down,
                                  top-left pixel at (origin_mm)
      <name>_rectified_grid.png   the same with a mm grid (every 10, labels every 50)
      <name>_rectified.json       homography, scale, and how well the markers fit
    """
    cv2, np = _cv()
    lay = lay or load_layout()
    img = cv2.imread(photo)
    if img is None:
        raise PhotoError("Couldn't open %s as a picture." % photo)
    cam = lay.get("camera")
    if cam:
        img = cv2.undistort(img, np.array(cam["matrix"], np.float64),
                            np.array(cam["dist"], np.float64))
    found = detect_markers(img, lay)
    wanted = sorted(marker_centres(lay))
    if len(found) < 3:
        raise PhotoError(
            "Found %d of the %d markers (%s). All four need to be in the picture, flat, "
            "unshaded and not cut off by the frame; a sharper or closer shot helps."
            % (len(found), len(wanted), ", ".join("ID %d" % i for i in sorted(found)) or "none"))
    H, turns, mapped, world, err = _fit(found, lay)
    checks = _checks(found, mapped, lay)
    centres = marker_centres(lay)
    m = float(lay.get("margin_mm", 40))
    xs = [c[0] for c in centres.values()]
    ys = [c[1] for c in centres.values()]
    origin = (min(xs) - m, min(ys) - m)
    w_mm, h_mm = max(xs) + m - origin[0], max(ys) + m - origin[1]
    if w_mm * h_mm * ppmm * ppmm > MAX_PIXELS:
        ppmm = math.sqrt(MAX_PIXELS / (w_mm * h_mm))
    S = np.array([[ppmm, 0, -origin[0] * ppmm], [0, ppmm, -origin[1] * ppmm], [0, 0, 1]])
    size = (int(round(w_mm * ppmm)), int(round(h_mm * ppmm)))
    flat = cv2.warpPerspective(img, S @ H, size, flags=cv2.INTER_CUBIC,
                               borderMode=cv2.BORDER_CONSTANT, borderValue=(40, 40, 40))
    base = os.path.splitext(os.path.basename(photo))[0] + "_rectified"
    folder = out_dir or os.path.dirname(os.path.abspath(photo))
    os.makedirs(folder, exist_ok=True)
    out_png = os.path.join(folder, base + ".png")
    cv2.imwrite(out_png, flat)
    grid_png = None
    if grid:
        grid_png = os.path.join(folder, base + "_grid.png")
        cv2.imwrite(grid_png, _grid(flat, ppmm, origin))
    warnings = []
    missing = [i for i in wanted if i not in found]
    if missing:
        warnings.append("ID %s not found: fitted from %d markers, so the far corner is "
                        "extrapolated — trust it less." % (", ".join(map(str, missing)), len(found)))
    rms = float(np.sqrt((err ** 2).mean()))
    if rms > RMS_WARN_MM:
        warnings.append("The markers don't agree with the recorded layout (corner error "
                        "%.2f mm RMS). Check the spacing in photo_markers.json, that no tile "
                        "moved, and that they lie flat." % rms)
    size_mm = float(lay["marker_mm"])
    for i, c in checks.items():
        if abs(c["size_mm"] / size_mm - 1) > SIZE_WARN:
            warnings.append("ID %d reads %.2f mm across, not %g: the sheet may not have "
                            "printed at 100%%, or the spacing is off." % (i, c["size_mm"], size_mm))
        if abs(c["tilt_deg"]) > TILT_WARN_DEG:
            warnings.append("ID %d is turned %.1f° off the mat grid; square it up (its corners "
                            "are placed assuming it's on the grid)." % (i, c["tilt_deg"]))
    plane = float(lay.get("plane_mm", 0))
    if part_height_mm is not None and abs(float(part_height_mm) - plane) > 1.0:
        warnings.append("The part's top face (%g mm) isn't on the marker plane (%g mm): "
                        "edges on it read too big, more so near the picture's edges. Raise "
                        "the markers on a shim of the part's height, or caliper the key "
                        "dimensions." % (float(part_height_mm), plane))
    report = {
        "ok": True, "photo": os.path.abspath(photo), "rectified": out_png,
        "grid": grid_png, "px_per_mm": round(ppmm, 4), "mm_per_px": round(1 / ppmm, 4),
        "origin_mm": [round(v, 3) for v in origin],
        "size_px": list(size), "plane_mm": plane,
        "markers_found": sorted(found), "quarter_turns": turns,
        "fit_rms_mm": round(rms, 3), "fit_max_mm": round(float(err.max()), 3),
        "marker_checks": checks, "warnings": warnings,
        "homography": [[float(v) for v in row] for row in H],
        "how_to_read": "Rectified pixel (u, v) is at x = origin_mm[0] + u / px_per_mm, "
                       "y = origin_mm[1] + v / px_per_mm, in mm with ID 0's centre at 0, 0. "
                       "True sizes hold on the marker plane only (plane_mm above the mat).",
    }
    with open(os.path.join(folder, base + ".json"), "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2)
    return report


def measure(report, points, space="photo"):
    """
    Points → mm, and the distance along them. `report` is rectify()'s result
    (or its .json path). `space`: "photo" for pixels of the original picture,
    "rectified" for pixels of the rectified one.
    """
    if isinstance(report, str):
        with open(report, encoding="utf-8") as fh:
            report = json.load(fh)
    if space == "rectified":
        ppmm, (ox, oy) = report["px_per_mm"], report["origin_mm"]
        mm = [(round(ox + u / ppmm, 2), round(oy + v / ppmm, 2)) for u, v in points]
    else:
        mm = to_mm(report["homography"], points)
    legs = [round(math.dist(a, b), 2) for a, b in zip(mm, mm[1:])]
    return {"points_mm": mm, "legs_mm": legs, "total_mm": round(sum(legs), 2),
            "plane_mm": report.get("plane_mm", 0)}


def preview(path, max_side=1600):
    """A JPEG of the picture no bigger than max_side, for showing in chat."""
    cv2, np = _cv()
    img = cv2.imread(path)
    if img is None:
        return None
    f = min(1.0, max_side / float(max(img.shape[:2])))
    if f < 1:
        img = cv2.resize(img, None, fx=f, fy=f, interpolation=cv2.INTER_AREA)
    ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 88])
    return buf.tobytes() if ok else None


# -------------------------------------------------------------------- CLI

def _flag(argv, name, default=None, cast=float):
    if name in argv:
        i = argv.index(name)
        v = argv[i + 1]
        del argv[i:i + 2]
        return cast(v)
    return default


def _cli(argv):
    argv = list(argv)
    try:
        cmd = argv[1] if len(argv) > 1 else ""
        if cmd == "sheet":
            page = "a4" if "--a4" in argv else "letter"
            argv = [a for a in argv if a != "--a4"]
            out = argv[2] if len(argv) > 2 else os.path.join(_HERE, "photo_markers.pdf")
            r = marker_sheet(out, page=page)
            print("Saved %s (%s, %g mm markers). Print at 100%% and check the 100 mm bar."
                  % (r["file"], page, r["marker_mm"]))
            return 0
        if cmd == "layout":
            lay = load_layout()
            changed = False
            for flag, key in (("--width", "width_mm"), ("--height", "height_mm"),
                              ("--plane", "plane_mm"), ("--size", "marker_mm"),
                              ("--margin", "margin_mm")):
                v = _flag(argv, flag)
                if v is not None:
                    lay[key] = v
                    changed = True
            if changed:
                save_layout(lay)
                print("Saved %s." % LAYOUT_PATH)
            print(json.dumps({k: lay[k] for k in DEFAULT_LAYOUT}, indent=2))
            print("Marker centres (mm):", marker_centres(lay))
            return 0
        if cmd == "rectify" and len(argv) > 2:
            ppmm = _flag(argv, "--ppmm", PPMM)
            part = _flag(argv, "--part-height")
            r = rectify(argv[2], ppmm=ppmm, part_height_mm=part)
            print("Saved %s (%.1f px/mm). Marker fit %.2f mm RMS, %.2f mm worst."
                  % (r["rectified"], r["px_per_mm"], r["fit_rms_mm"], r["fit_max_mm"]))
            for w in r["warnings"]:
                print("  ! " + w)
            return 0
        if cmd == "measure" and len(argv) > 3:
            space = "rectified" if "--rectified" in argv else "photo"
            pts = [tuple(float(v) for v in a.split(",")) for a in argv[3:] if "," in a]
            print(json.dumps(measure(argv[2], pts, space)))
            return 0
    except PhotoError as exc:
        print("Couldn't: %s" % exc)
        return 1
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(_cli(sys.argv))
