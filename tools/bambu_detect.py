#!/usr/bin/env python3
"""
Project Bonfire — Obico's spaghetti detector, run directly on this PC.

No Docker, no server: Obico's published ONNX model (the same weights its own
server uses) run with onnxruntime, with the same pre- and post-processing as
obico-server's ml_api/lib/onnx.py. CPU is plenty for a picture every few
minutes (well under a second each).

    python tools/bambu_detect.py setup            # download the model (once)
    python tools/bambu_detect.py <picture.jpg>    # detections and score

Needs: python -m pip install onnxruntime numpy pillow

The model file goes to tools/obico/model-weights.onnx (git-ignored). Obico's
code is AGPL-3.0 and the weights are theirs; this file only loads them.
"""
import json
import os
import sys
import urllib.request

_HERE = os.path.dirname(os.path.abspath(__file__))
MODEL_DIR = os.path.join(_HERE, "obico")
MODEL_PATH = os.path.join(MODEL_DIR, "model-weights.onnx")
# obico-server, ml_api/model/model-weights.onnx.url (release branch)
MODEL_URL = "https://tsd-pub-static.s3.amazonaws.com/ml-models/model-weights-5a6b1be1fa.onnx"
NAMES = ["failure"]                       # ml_api/model/names
THRESH = 0.08                             # ml_api/server.py THRESH
NMS = 0.45
_SESSION = []


class DetectorError(Exception):
    """Something about the detector, in words worth showing."""


def _need(module):
    try:
        return __import__(module)
    except ImportError:
        raise DetectorError("The detector needs onnxruntime, numpy and pillow: run "
                            "`python -m pip install onnxruntime numpy pillow`.")


def setup(url=MODEL_URL, path=MODEL_PATH, progress=True):
    """Download the model once. Returns its path."""
    if os.path.isfile(path) and os.path.getsize(path) > 1_000_000:
        return path
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".part"
    try:
        with urllib.request.urlopen(url, timeout=60) as resp, open(tmp, "wb") as out:
            total = int(resp.headers.get("Content-Length") or 0)
            done = 0
            while True:
                chunk = resp.read(1 << 20)
                if not chunk:
                    break
                out.write(chunk)
                done += len(chunk)
                if progress and total and sys.stdout:
                    print("\r  %d / %d MB" % (done >> 20, total >> 20), end="", flush=True)
        if progress and sys.stdout:
            print()
    except Exception as exc:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise DetectorError("Couldn't download the detector model from %s (%s)." % (url, exc))
    os.replace(tmp, path)
    return path


def _session(path=MODEL_PATH):
    if _SESSION and _SESSION[0][0] == path:
        return _SESSION[0][1]
    ort = _need("onnxruntime")
    if not os.path.isfile(path):
        setup(path=path, progress=False)
    try:
        sess = ort.InferenceSession(path, providers=["CPUExecutionProvider"])
    except Exception as exc:
        raise DetectorError("The detector model wouldn't load (%s). Delete %s and "
                            "run `python tools/bambu_detect.py setup` again." % (exc, path))
    _SESSION[:] = [(path, sess)]
    return sess


def _nms(boxes, confs, thresh):
    np = _need("numpy")
    x1, y1, x2, y2 = boxes[:, 0], boxes[:, 1], boxes[:, 2], boxes[:, 3]
    areas = (x2 - x1) * (y2 - y1)
    order = confs.argsort()[::-1]
    keep = []
    while order.size > 0:
        i, rest = order[0], order[1:]
        keep.append(i)
        w = np.maximum(0.0, np.minimum(x2[i], x2[rest]) - np.maximum(x1[i], x1[rest]))
        h = np.maximum(0.0, np.minimum(y2[i], y2[rest]) - np.maximum(y1[i], y1[rest]))
        inter = w * h
        over = inter / (areas[i] + areas[rest] - inter + 1e-12)
        order = order[np.where(over <= thresh)[0] + 1]
    return np.array(keep, dtype=int)


def post_process(outputs, width, height, thresh=THRESH, nms=NMS, names=NAMES):
    """obico-server's post_processing: boxes [1, N, 1, 4] as x1 y1 x2 y2 (0-1),
    confidences [1, N, classes]. Returns [(name, confidence, (cx, cy, w, h))]."""
    np = _need("numpy")
    boxes = np.asarray(outputs[0])[:, :, 0]
    confs = np.asarray(outputs[1])
    max_conf = confs.max(axis=2)[0]
    max_id = confs.argmax(axis=2)[0]
    sel = max_conf > thresh
    boxes, max_conf, max_id = boxes[0][sel], max_conf[sel], max_id[sel]
    out = []
    for cls in range(confs.shape[2]):
        m = max_id == cls
        b, c = boxes[m], max_conf[m]
        if not len(c):
            continue
        for k in _nms(b, c, nms):
            x1, y1, x2, y2 = (float(v) for v in b[k])
            name = names[cls] if cls < len(names) else str(cls)
            out.append((name, float(c[k]),
                        (0.5 * width * (x1 + x2), 0.5 * height * (y1 + y2),
                         width * (x2 - x1), height * (y2 - y1))))
    return out


def detect(picture, thresh=THRESH, model_path=MODEL_PATH):
    """Detections for one picture, as obico-server returns them:
    [[name, confidence, [cx, cy, w, h]], ...] in the picture's pixels."""
    np = _need("numpy")
    _need("PIL")
    from PIL import Image
    sess = _session(model_path)
    inp = sess.get_inputs()[0]
    h = inp.shape[2] if isinstance(inp.shape[2], int) else 416
    w = inp.shape[3] if isinstance(inp.shape[3], int) else 416
    try:
        img = Image.open(picture).convert("RGB")
    except Exception as exc:
        raise DetectorError("Couldn't open %s (%s)." % (picture, exc))
    width, height = img.size
    arr = np.asarray(img.resize((w, h), Image.BILINEAR), dtype=np.float32) / 255.0
    arr = np.expand_dims(np.transpose(arr, (2, 0, 1)), 0)
    outputs = sess.run(None, {inp.name: arr})
    return [[n, round(c, 4), [round(v, 1) for v in box]]
            for n, c, box in post_process(outputs, width, height, thresh)]


def score(detections):
    """A picture's failure score, as Obico's server counts it: the sum of the
    detections' confidence."""
    return round(sum(float(d[1]) for d in detections), 3)


def _cli(argv):
    try:
        if len(argv) > 1 and argv[1] == "setup":
            print("Downloading the detector model (once)...")
            print("Saved %s." % setup())
            return 0
        if len(argv) > 1 and os.path.isfile(argv[1]):
            det = detect(argv[1])
            print("score %.2f, %d detection(s): %s" % (score(det), len(det), json.dumps(det)))
            return 0
    except DetectorError as exc:
        print("Couldn't: %s" % exc)
        return 1
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(_cli(sys.argv))
