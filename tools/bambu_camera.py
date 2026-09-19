#!/usr/bin/env python3
"""
Project Bonfire — one picture from the P1S camera, over the home network.

The P1-series camera isn't on the cloud. The printer serves it on the home
network: TLS on port 6000, log in with user `bblp` and the printer's access
code, and it sends JPEG frames (about one a second), each behind a 16-byte
header whose first 4 bytes are the JPEG's length. This reads one whole frame
and hangs up. It only watches — nothing is sent to the printer but the login.

    python tools/bambu_camera.py snapshot [out.jpg]

The address and access code come from bambu_lan.resolve() (.env, the
printer's network announcement, and Bambu Cloud) — the code is never printed.
"""
import datetime
import os
import runpy
import socket
import ssl
import struct
import sys
import time

_HERE = os.path.dirname(os.path.abspath(__file__))
CAMERA_PORT = 6000
USER = "bblp"
JPEG_START = b"\xff\xd8"
JPEG_END = b"\xff\xd9"
MAX_FRAME = 8 * 1024 * 1024
TIMEOUT_S = 12.0
SNAPSHOT_DIR = os.path.join(_HERE, "camera_snapshots")      # git-ignored
KEEP_SNAPSHOTS = 20


class CameraError(Exception):
    """The camera said no, in words worth showing."""


def auth_packet(access_code, user=USER):
    """The 80-byte login: 4 little-endian words (0x40 payload size, 0x3000
    type, 0, 0), then the user and the access code, each padded to 32."""
    user_b = user.encode("ascii")[:32]
    code_b = str(access_code).encode("ascii")[:32]
    return (struct.pack("<IIII", 0x40, 0x3000, 0, 0)
            + user_b + b"\x00" * (32 - len(user_b))
            + code_b + b"\x00" * (32 - len(code_b)))


def read_frame(recv, deadline):
    """
    Read one whole JPEG from the stream. `recv(n)` returns up to n bytes
    (b"" when the printer hangs up). Each frame is a 16-byte header — the
    first 4 bytes little-endian are the JPEG's size — then the JPEG.
    """
    buf = b""

    def need(n):
        nonlocal buf
        while len(buf) < n:
            if time.time() > deadline:
                raise CameraError("No picture from the camera in %gs." % TIMEOUT_S)
            chunk = recv(max(4096, n - len(buf)))
            if not chunk:
                raise CameraError(
                    "The printer closed the camera connection without sending a "
                    "picture. Check that LAN liveview is allowed on the printer "
                    "(on the screen: Settings → Network/WLAN → LAN Only Liveview).")
            buf += chunk
        out, buf = buf[:n], buf[n:]
        return out

    while True:
        header = need(16)
        size = struct.unpack("<I", header[:4])[0]
        if size <= 0 or size > MAX_FRAME:
            raise CameraError("The camera sent a frame header that doesn't make "
                              "sense (%d bytes)." % size)
        jpeg = need(size)
        if jpeg[:2] == JPEG_START and jpeg[-2:] == JPEG_END:
            return jpeg
        # A damaged frame: skip it and take the next one.


def _connect(ip, code, timeout):
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE          # the printer's certificate is self-signed
    try:
        raw = socket.create_connection((ip, CAMERA_PORT), timeout=timeout)
    except OSError as exc:
        raise CameraError("Couldn't reach the camera at %s:%d (%s). Is this PC on "
                          "the printer's network?" % (ip, CAMERA_PORT, exc))
    try:
        sock = ctx.wrap_socket(raw, server_hostname=ip)
    except (ssl.SSLError, OSError) as exc:
        raw.close()
        raise CameraError("The camera wouldn't start a secure connection (%s)." % exc)
    sock.sendall(auth_packet(code))
    return sock


def _tidy(folder, keep=KEEP_SNAPSHOTS):
    """Only the newest `keep` automatic snapshots stay."""
    try:
        shots = sorted((f for f in os.listdir(folder) if f.startswith("snapshot_")
                        and f.endswith(".jpg")), reverse=True)
        for old in shots[keep:]:
            os.remove(os.path.join(folder, old))
    except OSError:
        pass


def snapshot(out_path=None, serial="", lan=None, timeout=TIMEOUT_S, _connect_fn=None):
    """
    One JPEG from the camera, saved to `out_path` (default:
    tools/camera_snapshots/snapshot_<time>.jpg, newest 20 kept). Returns
    {"ok", "file", "bytes", "ip", "taken"} — never the access code.
    """
    if lan is None:
        try:
            lan = runpy.run_path(os.path.join(_HERE, "bambu_lan.py"))["resolve"](serial)
        except Exception as exc:          # LanError / CloudError, in plain words
            raise CameraError(str(exc))
    sock = (_connect_fn or _connect)(lan["ip"], lan["_code"], timeout)
    try:
        sock.settimeout(timeout)
        try:
            jpeg = read_frame(sock.recv, time.time() + timeout)
        except socket.timeout:
            raise CameraError("No picture from the camera in %gs. If the printer "
                              "is on, check LAN liveview is allowed on its screen "
                              "(Settings → Network/WLAN → LAN Only Liveview)." % timeout)
        except ssl.SSLError as exc:
            raise CameraError("The camera connection broke (%s). A wrong access "
                              "code ends it this way too." % exc)
    finally:
        try:
            sock.close()
        except Exception:
            pass
    taken = datetime.datetime.now()
    auto = out_path is None
    if auto:
        os.makedirs(SNAPSHOT_DIR, exist_ok=True)
        out_path = os.path.join(SNAPSHOT_DIR, taken.strftime("snapshot_%Y%m%d_%H%M%S.jpg"))
    else:
        os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    with open(out_path, "wb") as fh:
        fh.write(jpeg)
    if auto:
        _tidy(SNAPSHOT_DIR)
    return {"ok": True, "file": os.path.abspath(out_path), "bytes": len(jpeg),
            "ip": lan["ip"], "taken": taken.isoformat(timespec="seconds")}


def _cli(argv):
    if len(argv) > 1 and argv[1] == "snapshot":
        try:
            r = snapshot(argv[2] if len(argv) > 2 else None)
        except Exception as exc:
            print("Couldn't: %s" % exc)
            return 1
        print("Saved %s (%d bytes) from the camera at %s." % (r["file"], r["bytes"], r["ip"]))
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(_cli(sys.argv))
