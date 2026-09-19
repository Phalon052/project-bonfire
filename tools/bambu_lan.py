#!/usr/bin/env python3
"""
Project Bonfire — the P1S on the local network: find it, and put files on it.

Bambu Cloud can start a print, but it can't deliver the file. The printer
takes files over FTPS on the home network (port 990, user `bblp`, password =
the printer's access code). This works with the printer in its normal cloud
mode — LAN-only Mode and Developer Mode stay off.

    python tools/bambu_lan.py check          # find it, log in, list its files
    python tools/bambu_lan.py upload <file>  # copy one file onto it

Where the address and access code come from, first match wins:

  * `.env`: BAMBU_PRINTER_IP, BAMBU_ACCESS_CODE — if you set them.
  * the address: the printer announces itself on the network every few
    seconds (SSDP, UDP 1990/2021); this listens for it and matches the serial.
  * the access code: Bambu Cloud hands it to a signed-in account along with
    the device list. It is used for the one connection and never stored or
    printed.

Nothing here starts, stops or deletes anything.
"""
import ftplib
import os
import re
import runpy
import select
import socket
import ssl
import struct
import sys
import time

_HERE = os.path.dirname(os.path.abspath(__file__))
FTP_PORT = 990
FTP_USER = "bblp"
SSDP_GROUP = "239.255.255.250"
SSDP_PORTS = (2021, 1990)
DISCOVER_S = 8.0


class LanError(Exception):
    """Something on the local network said no, in words worth showing."""


def _load_env():
    """Pull .env into this process (existing environment wins), quietly."""
    try:
        runpy.run_path(os.path.join(_HERE, "env.py"))["load"]()
    except Exception:
        pass


# ── finding the printer ──────────────────────────────────────────────

def parse_ssdp(packet):
    """A Bambu printer's announcement, as a dict. The printer puts its IP in
    Location, its serial in USN, and its model and name in *.bambu.com
    headers."""
    try:
        text = packet.decode("utf-8", "replace")
    except AttributeError:
        text = packet
    if "bambu" not in text.lower():
        return None
    head = {}
    for line in text.splitlines()[1:]:
        if ":" in line:
            k, v = line.split(":", 1)
            head[k.strip().lower()] = v.strip()
    ip = head.get("location", "")
    ip = re.sub(r"^[a-z]+://", "", ip).split("/")[0].split(":")[0]
    if not re.match(r"^\d+\.\d+\.\d+\.\d+$", ip):
        return None
    return {"ip": ip, "serial": head.get("usn", ""),
            "model": head.get("devmodel.bambu.com", ""),
            "name": head.get("devname.bambu.com", ""),
            "connect": head.get("devconnect.bambu.com", ""),
            "signal": head.get("devsignal.bambu.com", "")}


def discover(serial="", timeout=DISCOVER_S):
    """Listen for printers announcing themselves. Returns every one heard, or
    stops early once `serial` is heard."""
    socks = []
    for port in SSDP_PORTS:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind(("", port))
            try:
                mreq = struct.pack("4sl", socket.inet_aton(SSDP_GROUP),
                                   socket.INADDR_ANY)
                s.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
            except OSError:
                pass                      # broadcast still arrives on 2021
            s.setblocking(False)
            socks.append(s)
        except OSError:
            continue
    if not socks:
        raise LanError("Couldn't listen for the printer on UDP 1990/2021 — "
                       "another program may be using those ports. Set "
                       "BAMBU_PRINTER_IP in .env instead.")
    found = {}
    end = time.time() + timeout
    try:
        while time.time() < end:
            ready, _, _ = select.select(socks, [], [], max(0.0, end - time.time()))
            for s in ready:
                try:
                    data, _ = s.recvfrom(4096)
                except OSError:
                    continue
                p = parse_ssdp(data)
                if p:
                    found[p["serial"] or p["ip"]] = p
                    if serial and p["serial"] == serial:
                        return [p]
    finally:
        for s in socks:
            s.close()
    return list(found.values())


def resolve(serial="", record=None):
    """
    The printer's address and access code, and where each came from. The
    access code is returned for use, never for display — callers must not
    print it.
    """
    _load_env()
    out = {"serial": serial}
    ip = os.environ.get("BAMBU_PRINTER_IP", "").strip()
    code = os.environ.get("BAMBU_ACCESS_CODE", "").strip()
    out["ip_from"] = ".env" if ip else None
    out["code_from"] = ".env" if code else None

    if not ip:
        heard = discover(serial)
        match = [p for p in heard if not serial or p["serial"] == serial]
        if not match:
            raise LanError(
                "Didn't hear the printer on the network in %gs. Is this PC on "
                "the same network as the printer? If so, set BAMBU_PRINTER_IP "
                "in .env (printer screen: Settings → WLAN)." % DISCOVER_S)
        ip = match[0]["ip"]
        out["ip_from"] = "network announcement"
        out["serial"] = out["serial"] or match[0]["serial"]

    if not code:
        bc = runpy.run_path(os.path.join(_HERE, "bambu_cloud.py"))
        try:
            code = bc["lan_access_code"](out["serial"], record)
        except Exception as exc:
            raise LanError("No access code: set BAMBU_ACCESS_CODE in .env "
                           "(printer screen: Settings → WLAN), or sign in to "
                           "Bambu Cloud so it can be fetched. (%s)" % exc)
        out["code_from"] = "Bambu Cloud"
    out["ip"], out["_code"] = ip, code
    return out


# ── FTPS, the way the printer wants it ───────────────────────────────

class _ImplicitFTPS(ftplib.FTP_TLS):
    """The printer speaks implicit TLS on 990 (TLS from the first byte), which
    Python's FTP_TLS doesn't do by itself, and wants the data connection to
    reuse the control connection's TLS session."""

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self._sock = None

    @property
    def sock(self):
        return self._sock

    @sock.setter
    def sock(self, value):
        if value is not None and not isinstance(value, ssl.SSLSocket):
            value = self.context.wrap_socket(value)
        self._sock = value

    def ntransfercmd(self, cmd, rest=None):
        conn, size = ftplib.FTP.ntransfercmd(self, cmd, rest)
        if self._prot_p:
            conn = self.context.wrap_socket(conn, server_hostname=self.host,
                                            session=self.sock.session)
        return conn, size

    # The printer never answers the TLS close (unwrap) at the end of a data
    # transfer, so the stock methods sit out their whole timeout afterwards.
    # These are ftplib's own, minus the unwrap.
    def storbinary(self, cmd, fp, blocksize=8192, callback=None, rest=None):
        self.voidcmd("TYPE I")
        with self.transfercmd(cmd, rest) as conn:
            while True:
                buf = fp.read(blocksize)
                if not buf:
                    break
                conn.sendall(buf)
                if callback:
                    callback(buf)
        return self.voidresp()

    def retrlines(self, cmd, callback=None):
        callback = callback or ftplib.print_line
        self.sendcmd("TYPE A")
        with self.transfercmd(cmd) as conn, conn.makefile("r", encoding=self.encoding) as fp:
            while True:
                line = fp.readline(self.maxline + 1)
                if not line:
                    break
                callback(line.rstrip("\r\n"))
        return self.voidresp()


def _connect(ip, code, timeout=20):
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE     # the printer's certificate is self-signed
    ftp = _ImplicitFTPS(context=ctx, timeout=timeout)
    try:
        ftp.connect(ip, FTP_PORT)
        ftp.login(FTP_USER, code)
        ftp.prot_p()
    except ftplib.error_perm as exc:
        raise LanError("The printer refused the login (%s). The access code may "
                       "have changed — it changes when LAN-only Mode is toggled."
                       % str(exc).split("\n")[0])
    except (OSError, ftplib.Error) as exc:
        raise LanError("Couldn't reach the printer at %s:%d (%s)."
                       % (ip, FTP_PORT, exc))
    return ftp


def safe_name(name):
    """A file name the printer's SD card and its print command both accept:
    plain ASCII, no path, no spaces."""
    base = re.split(r"[\\/]", name)[-1]     # Windows or POSIX path, either way
    base = re.sub(r"[^A-Za-z0-9._-]+", "_", base).strip("._") or "print"
    if not base.lower().endswith(".3mf"):
        base += ".3mf"
    return base


def upload(local_path, lan=None, remote_name=None, serial=""):
    """Copy a sliced .gcode.3mf onto the printer's SD card. Returns the name it
    has there — the name the print command needs."""
    if not os.path.isfile(local_path):
        raise LanError("No file at %s" % local_path)
    lan = lan or resolve(serial)
    name = safe_name(remote_name or os.path.basename(local_path))
    size = os.path.getsize(local_path)
    ftp = _connect(lan["ip"], lan["_code"])
    try:
        with open(local_path, "rb") as fh:
            ftp.storbinary("STOR " + name, fh, blocksize=64 * 1024)
        try:
            there = ftp.size(name)
        except ftplib.Error:
            there = None
    finally:
        try:
            ftp.quit()
        except Exception:
            ftp.close()
    if there is not None and there != size:
        raise LanError("Upload ended short: %d of %d bytes arrived." % (there, size))
    return {"name": name, "bytes": size, "ip": lan["ip"],
            "ip_from": lan["ip_from"], "code_from": lan["code_from"]}


def list_files(lan=None, serial=""):
    """What's on the printer's SD card (top level)."""
    lan = lan or resolve(serial)
    ftp = _connect(lan["ip"], lan["_code"])
    try:
        names = ftp.nlst()
    finally:
        try:
            ftp.quit()
        except Exception:
            ftp.close()
    return sorted(n for n in names if n not in (".", ".."))


def check(serial=""):
    """Find the printer, log in, and list its files — proves the whole path
    works before a print depends on it."""
    lan = resolve(serial)
    files = list_files(lan)
    prints = [f for f in files if f.lower().endswith(".3mf")]
    return {"ok": True, "ip": lan["ip"], "ip_from": lan["ip_from"],
            "access_code_from": lan["code_from"], "files": len(files),
            "print_files": prints[:20]}


def _cli(argv):
    cmd = argv[1] if len(argv) > 1 else "check"
    try:
        if cmd == "check":
            r = check()
            print("Printer at %s (address from %s, access code from %s)."
                  % (r["ip"], r["ip_from"], r["access_code_from"]))
            print("%d files on the SD card; print files:" % r["files"])
            for f in r["print_files"]:
                print("  " + f)
        elif cmd == "upload" and len(argv) > 2:
            r = upload(argv[2])
            print("Uploaded %s (%d bytes) to %s." % (r["name"], r["bytes"], r["ip"]))
        elif cmd == "discover":
            for p in discover():
                print("%s  %s  %s  %s" % (p["ip"], p["model"], p["serial"], p["name"]))
        else:
            print(__doc__)
            return 2
    except LanError as exc:
        print("Couldn't: %s" % exc)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(_cli(sys.argv))
