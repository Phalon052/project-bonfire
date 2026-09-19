#!/usr/bin/env python3
"""
Project Bonfire — Bambu Layer C: the P1S over Bambu Cloud.

Signs in to the Bambu account, finds the printer, reads its live state — job,
progress, temperatures, errors (HMS), what is loaded in the AMS — and sends it
commands (send_command). The rules about which commands need a yes live in
bambu_print.py, not here.

Sign in once, in a terminal on this PC:

    python tools/bambu_cloud.py login you@example.com

The password is typed there, hidden, and sent straight to Bambu. It is never
stored and never passes through Claude. What is kept is the access token, in
`tools/bambu_cloud.local.json` (git-ignored). It lasts about three months and
Bambu no longer allows refreshing it, so when it runs out the same command is
run again.

    python tools/bambu_cloud.py status     # what the printer is doing
    python tools/bambu_cloud.py devices    # printers on the account
    python tools/bambu_cloud.py logout     # forget the token

From other tools:

    bc = runpy.run_path(os.path.join(ROOT, "tools", "bambu_cloud.py"))
    print(bc["format_status"](bc["printer_status"]()))

Needs `paho-mqtt` for live status, and `curl_cffi` (or `cloudscraper`) to get
past Cloudflare on the sign-in pages — plain HTTP is often refused there:

    python -m pip install paho-mqtt curl_cffi

What cloud can't do on a P1S: send a sliced file to the printer (there is no
upload endpoint — that goes through Bambu Studio or Handy) or show the camera
(LAN only). See 04_bambu_basics.md section 7.

The endpoints are Bambu's own, unofficial and undocumented; they are taken from
the ha-bambulab integration (MIT) and OpenBambuAPI, checked September 2026.
They change — the sign-in CSRF address moved that month — so failures here
say what they got back rather than retrying.
"""
import base64
import datetime
import getpass
import json
import os
import ssl
import sys
import threading
import time
import urllib.error
import urllib.request

_HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(_HERE)
TOKEN_FILE = os.path.join(_HERE, "bambu_cloud.local.json")

API = {"global": "https://api.bambulab.com", "china": "https://api.bambulab.cn"}
WEB = {"global": "https://bambulab.com", "china": "https://bambulab.cn"}
# Global accounts all use the US broker, wherever they are. China's broker is
# still a .com host.
MQTT_HOST = {"global": "us.mqtt.bambulab.com", "china": "cn.mqtt.bambulab.com"}
MQTT_PORT = 8883

# Bambu's own client headers. Without them the API tends to refuse the call.
HEADERS = {
    "User-Agent": "bambu_network_agent/01.09.05.01",
    "X-BBL-Client-Name": "OrcaSlicer",
    "X-BBL-Client-Type": "slicer",
    "X-BBL-Client-Version": "01.09.05.51",
    "X-BBL-Language": "en-US",
    "X-BBL-OS-Type": "windows",
    "X-BBL-OS-Version": "10.0",
    "X-BBL-Agent-Version": "01.09.05.01",
    "X-BBL-Executable-info": "{}",
    "X-BBL-Agent-OS-Type": "windows",
    "accept": "application/json",
    "Content-Type": "application/json",
}

P1S_MODEL_CODES = ("C12",)          # dev_model_name for a P1S (P1P is C11)
STATUS_WAIT_S = 10.0                # how long to wait for the printer's report


class CloudError(Exception):
    """Something the cloud said no to, in words worth showing."""


# ── HTTP, with whatever gets past Cloudflare ─────────────────────────

class _Response:
    def __init__(self, status, text, cookies):
        self.status, self.text, self.cookies = status, text, cookies

    def json(self):
        try:
            return json.loads(self.text) if self.text else {}
        except ValueError:
            return {}


def _http_backend():
    """curl_cffi (impersonating Chrome) is what reliably gets through;
    cloudscraper next; plain urllib last."""
    try:
        from curl_cffi import requests as cr          # noqa: F401
        return "curl_cffi"
    except Exception:
        pass
    try:
        import cloudscraper                           # noqa: F401
        return "cloudscraper"
    except Exception:
        pass
    return "urllib"


def http(method, url, headers=None, body=None, cookies=None, timeout=30):
    """One request. Returns a _Response; never raises on an HTTP status."""
    headers = dict(headers or {})
    data = json.dumps(body) if body is not None else None
    backend = _http_backend()
    if backend == "curl_cffi":
        from curl_cffi import requests as cr
        r = cr.request(method, url, headers=headers, data=data, cookies=cookies,
                       timeout=timeout, impersonate="chrome")
        return _Response(r.status_code, r.text, dict(r.cookies))
    if backend == "cloudscraper":
        import cloudscraper
        s = cloudscraper.create_scraper()
        r = s.request(method, url, headers=headers, data=data, cookies=cookies,
                      timeout=timeout)
        return _Response(r.status_code, r.text, r.cookies.get_dict())
    req = urllib.request.Request(url, data=data.encode() if data else None,
                                 headers=headers, method=method)
    if cookies:
        req.add_header("Cookie", "; ".join("%s=%s" % kv for kv in cookies.items()))
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            jar = _cookies_from(r.headers.get_all("Set-Cookie") or [])
            return _Response(r.status, r.read().decode("utf-8", "replace"), jar)
    except urllib.error.HTTPError as e:
        jar = _cookies_from(e.headers.get_all("Set-Cookie") or [])
        return _Response(e.code, e.read().decode("utf-8", "replace"), jar)


def _cookies_from(set_cookie_headers):
    jar = {}
    for h in set_cookie_headers:
        first = h.split(";", 1)[0]
        if "=" in first:
            k, v = first.split("=", 1)
            jar[k.strip()] = v.strip()
    return jar


def _refused(resp, what):
    """Turn a refusal into something actionable."""
    text = (resp.text or "")[:300]
    if resp.status in (403, 429) and "cloudflare" in text.lower():
        hint = ("Cloudflare blocked the request. Install curl_cffi "
                "(python -m pip install curl_cffi) and try again; if it was a "
                "429, wait a few minutes first.")
        if resp.status == 429:
            hint = "Bambu is rate-limiting this PC. Wait a few minutes. " + hint
        return CloudError("%s refused (%d). %s" % (what, resp.status, hint))
    if resp.status == 401:
        return CloudError("%s: the sign-in has expired or been revoked. Run "
                          "`python tools/bambu_cloud.py login` again." % what)
    return CloudError("%s failed (HTTP %d): %s" % (what, resp.status, text))


# ── the token file ───────────────────────────────────────────────────

def load_token(path=TOKEN_FILE):
    if not os.path.isfile(path):
        return None
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return None


def save_token(record, path=TOKEN_FILE):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(record, fh, indent=2)
    os.replace(tmp, path)
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    return path


def forget_token(path=TOKEN_FILE):
    if os.path.isfile(path):
        os.remove(path)
        return True
    return False


def jwt_claims(token):
    """The claims inside the token, if it is a JWT (Bambu's usually are)."""
    try:
        part = token.split(".")[1]
        return json.loads(base64.urlsafe_b64decode(part + "=" * (-len(part) % 4)))
    except Exception:
        return {}


def account_state(record=None, now=None):
    """Signed in? Until when? Without touching the network."""
    record = record if record is not None else load_token()
    if not record or not record.get("token"):
        return {"signed_in": False,
                "next": "Run `python tools/bambu_cloud.py login <email>` in a "
                        "terminal on this PC."}
    now = now or time.time()
    exp = record.get("expires_at")
    out = {"signed_in": True, "email": record.get("email"),
           "region": record.get("region", "global"),
           "signed_in_at": record.get("saved_at"),
           "printer": record.get("printer_name"),
           "serial": record.get("serial")}
    if exp:
        days = (exp - now) / 86400.0
        out["expires"] = datetime.datetime.fromtimestamp(exp).strftime("%Y-%m-%d")
        out["days_left"] = round(days, 1)
        if days <= 0:
            out["signed_in"] = False
            out["next"] = ("The token has expired. Run `python "
                           "tools/bambu_cloud.py login` again.")
        elif days < 7:
            out["warning"] = ("The sign-in runs out in %.0f days; signing in "
                              "again needs an emailed code." % days)
    return out


# ── signing in ───────────────────────────────────────────────────────

def login(email, password, ask_code, region="global", http_fn=None):
    """
    Bambu's sign-in has three outcomes, and all three are handled:

      * the token comes straight back;
      * `verifyCode` — Bambu emails a six-digit code, which `ask_code` gets
        from the person, and the sign-in is repeated with it;
      * `tfa` — two-factor: a CSRF cookie from bambulab.com, then the TFA
        code, and the token comes back as a cookie rather than in the body.

    `ask_code(prompt)` returns the code the person typed. The password is
    used for one request and is not kept.
    Returns the token record to save.
    """
    http_fn = http_fn or http
    api = API[region]
    url = api + "/v1/user-service/user/login"
    r = http_fn("POST", url, HEADERS,
                {"account": email, "password": password, "apiError": ""})
    if r.status != 200:
        raise _refused(r, "Signing in")
    body = r.json()
    token = body.get("accessToken", "")
    expires_in = body.get("expiresIn")

    if not token and body.get("loginType") == "verifyCode":
        s = http_fn("POST", api + "/v1/user-service/user/sendemail/code",
                    HEADERS, {"email": email, "type": "codeLogin"})
        if s.status != 200:
            raise _refused(s, "Asking Bambu to email a code")
        for attempt in range(3):
            code = (ask_code("Bambu has emailed a code to %s. Code: " % email)
                    or "").strip()
            r = http_fn("POST", url, HEADERS, {"account": email, "code": code})
            if r.status == 200 and r.json().get("accessToken"):
                body = r.json()
                token, expires_in = body["accessToken"], body.get("expiresIn")
                break
            err = r.json().get("code")
            if err == 1:
                raise CloudError("That code has expired. Run login again for a "
                                 "new one.")
            if attempt == 2:
                raise CloudError("The code was refused three times.")
            print("That code was refused — check it and try again.")

    elif not token and body.get("loginType") == "tfa":
        # The CSRF address moved in September 2026 (/api/sign-in/csrf -> /api/csrf).
        c = http_fn("GET", WEB[region] + "/api/csrf", HEADERS)
        csrf = c.cookies.get("bbl_csrf_token", "")
        if not csrf:
            raise CloudError("Two-factor sign-in: Bambu didn't hand out a CSRF "
                             "cookie (HTTP %d). Its sign-in pages may have "
                             "changed again." % c.status)
        h = dict(HEADERS, **{"x-bbl-csrf-token": csrf})
        code = (ask_code("Two-factor code: ") or "").strip()
        t = http_fn("POST", WEB[region] + "/api/sign-in/tfa", h,
                    {"tfaKey": body.get("tfaKey"), "tfaCode": code},
                    cookies={"bbl_csrf_token": csrf})
        token = t.cookies.get("token", "")
        if not token:
            raise _refused(t, "Two-factor sign-in")

    if not token:
        raise CloudError("Bambu didn't return a token (loginType=%r). Nothing "
                         "was saved." % body.get("loginType"))

    claims = jwt_claims(token)
    now = time.time()
    expires_at = claims.get("exp") or (now + float(expires_in) if expires_in
                                       else now + 90 * 86400)
    username = claims.get("username", "")
    if not username:
        p = http_fn("GET", api + "/v1/design-user-service/my/preference",
                    dict(HEADERS, Authorization="Bearer " + token))
        uid = p.json().get("uid")
        username = "u_%s" % uid if uid else ""
    return {"email": email, "region": region, "token": token,
            "username": username, "saved_at": datetime.datetime.now().isoformat(
                timespec="seconds"), "expires_at": expires_at}


def _auth(record):
    return dict(HEADERS, Authorization="Bearer " + record["token"])


# ── the printer ──────────────────────────────────────────────────────

def list_devices(record=None, http_fn=None):
    """Printers bound to the account."""
    record = record or _require_record()
    http_fn = http_fn or http
    r = http_fn("GET", API[record.get("region", "global")]
                + "/v1/iot-service/api/user/bind", _auth(record))
    if r.status != 200:
        raise _refused(r, "Listing printers")
    out = []
    for d in r.json().get("devices", []) or []:
        out.append({"serial": d.get("dev_id"), "name": d.get("name"),
                    "model": d.get("dev_product_name"),
                    "model_code": d.get("dev_model_name"),
                    "online": d.get("online"),
                    "print_status": d.get("print_status"),
                    "nozzle": d.get("nozzle_diameter")})
    return out


def pick_printer(devices, serial=""):
    """The P1S, or the one asked for."""
    if serial:
        match = [d for d in devices if d["serial"] == serial]
        if not match:
            raise CloudError("No printer with serial %s on this account." % serial)
        return match[0]
    p1s = [d for d in devices if d.get("model") == "P1S"
           or d.get("model_code") in P1S_MODEL_CODES]
    if len(p1s) == 1:
        return p1s[0]
    if len(devices) == 1:
        return devices[0]
    if not devices:
        raise CloudError("No printers are bound to this Bambu account. Sign the "
                         "printer in to the account on its screen first.")
    raise CloudError("Several printers on the account: %s. Set "
                     "BAMBU_PRINTER_SERIAL in .env to choose."
                     % ", ".join("%s (%s)" % (d["name"], d["serial"])
                                 for d in devices))


def _require_record():
    record = load_token()
    state = account_state(record)
    if not state["signed_in"]:
        raise CloudError(state["next"])
    return record


def fetch_report(record, serial, wait_s=STATUS_WAIT_S):
    """
    Connect to the cloud broker, ask the printer for a full report
    (`pushall`), and return the merged `print` object.

    The broker is push-based: once connected the printer streams changes, so
    this asks once, collects for up to `wait_s`, and disconnects. It never
    polls in a loop — repeated sign-ins are what get accounts throttled, not
    reading status.
    """
    try:
        import paho.mqtt.client as mqtt
    except ImportError:
        raise CloudError("Live status needs paho-mqtt: "
                         "python -m pip install paho-mqtt")
    region = record.get("region", "global")
    merged, got_full, errors = {}, threading.Event(), []

    def on_connect(client, userdata, flags, rc, *args):
        code = getattr(rc, "value", rc)
        if code != 0:
            errors.append("the broker refused the connection (code %s) — "
                          "usually an expired token" % code)
            got_full.set()
            return
        client.subscribe("device/%s/report" % serial, qos=1)
        client.publish("device/%s/request" % serial, json.dumps(
            {"pushing": {"sequence_id": "1", "command": "pushall",
                         "version": 1, "push_target": 1}}), qos=1)

    def on_message(client, userdata, msg):
        try:
            data = json.loads(msg.payload)
        except ValueError:
            return
        pr = data.get("print")
        if isinstance(pr, dict):
            _deep_merge(merged, pr)
            if "gcode_state" in pr and ("ams" in pr or "nozzle_temper" in pr):
                got_full.set()

    try:
        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2,
                             client_id="bonfire-%d" % int(time.time()))
    except AttributeError:                          # paho-mqtt 1.x
        client = mqtt.Client(client_id="bonfire-%d" % int(time.time()))
    client.username_pw_set(record["username"], password=record["token"])
    client.tls_set(cert_reqs=ssl.CERT_REQUIRED)
    client.on_connect, client.on_message = on_connect, on_message
    try:
        client.connect(MQTT_HOST[region], MQTT_PORT, keepalive=30)
    except Exception as exc:
        raise CloudError("Couldn't reach Bambu's cloud broker: %s" % exc)
    client.loop_start()
    got_full.wait(wait_s)
    client.loop_stop()
    try:
        client.disconnect()
    except Exception:
        pass
    if errors:
        raise CloudError(errors[0])
    if not merged:
        raise CloudError("The printer didn't answer within %gs. Is it switched "
                         "on, online, and not in LAN-only or Developer Mode?"
                         % wait_s)
    return merged


def lan_access_code(serial="", record=None, http_fn=None):
    """The printer's LAN access code, as Bambu Cloud reports it for a bound
    printer. For bambu_lan.py's FTPS login only: it is not stored, and nothing
    that calls this may print or return it."""
    record = record or _require_record()
    http_fn = http_fn or http
    r = http_fn("GET", API[record.get("region", "global")]
                + "/v1/iot-service/api/user/bind", _auth(record))
    if r.status != 200:
        raise _refused(r, "Fetching the access code")
    devs = r.json().get("devices", []) or []
    want = serial or record.get("serial", "")
    for d in devs:
        if (not want or d.get("dev_id") == want) and d.get("dev_access_code"):
            return d["dev_access_code"]
    raise CloudError("Bambu Cloud didn't return an access code for this printer.")


_SEQ = [int(time.time()) % 100000]


def next_sequence():
    _SEQ[0] += 1
    return str(_SEQ[0])


def command_payload(command, **fields):
    """A `print` command the printer will act on. Every one carries a fresh
    sequence_id and a `param` — without both, the broker accepts the message
    and the printer silently ignores it (bambulabs_api issue #183)."""
    body = {"sequence_id": next_sequence(), "command": command, "param": ""}
    body.update(fields)
    return {"print": body}


def send_command(payload, serial="", record=None, wait_s=8.0):
    """
    Publish one command and watch for the printer's answer.

    The printer echoes a command it has handled as a `print` message with the
    same command and sequence_id, plus `result` ("success"/"fail") and often a
    `reason`. Returns what came back: the echo (if any) and the latest state.
    """
    try:
        import paho.mqtt.client as mqtt
    except ImportError:
        raise CloudError("Sending commands needs paho-mqtt: "
                         "python -m pip install paho-mqtt")
    record = record or _require_record()
    serial = serial or record.get("serial") or pick_printer(
        list_devices(record))["serial"]
    region = record.get("region", "global")
    body = payload["print"]
    seq, cmd = body["sequence_id"], body["command"]
    seen = {"echo": None, "state": None, "error": None, "fun": None}
    done, errors = threading.Event(), []

    def on_connect(client, userdata, flags, rc, *args):
        code = getattr(rc, "value", rc)
        if code != 0:
            errors.append("the broker refused the connection (code %s)" % code)
            done.set()
            return
        client.subscribe("device/%s/report" % serial, qos=1)
        client.publish("device/%s/request" % serial, json.dumps(payload), qos=1)

    def on_message(client, userdata, msg):
        try:
            pr = json.loads(msg.payload).get("print") or {}
        except ValueError:
            return
        if "gcode_state" in pr:
            seen["state"] = pr["gcode_state"]
        if pr.get("print_error"):
            seen["error"] = pr["print_error"]
        if pr.get("fun") is not None:
            seen["fun"] = pr["fun"]
        if pr.get("command") == cmd and str(pr.get("sequence_id")) == seq:
            seen["echo"] = {k: pr.get(k) for k in ("result", "reason", "err_code")
                            if pr.get(k) is not None}
            done.set()

    try:
        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2,
                             client_id="bonfire-%d" % int(time.time()))
    except AttributeError:
        client = mqtt.Client(client_id="bonfire-%d" % int(time.time()))
    client.username_pw_set(record["username"], password=record["token"])
    client.tls_set(cert_reqs=ssl.CERT_REQUIRED)
    client.on_connect, client.on_message = on_connect, on_message
    try:
        client.connect(MQTT_HOST[region], MQTT_PORT, keepalive=30)
    except Exception as exc:
        raise CloudError("Couldn't reach Bambu's cloud broker: %s" % exc)
    client.loop_start()
    done.wait(wait_s)
    time.sleep(0.5)                     # let a state change arrive after the echo
    client.loop_stop()
    try:
        client.disconnect()
    except Exception:
        pass
    if errors:
        raise CloudError(errors[0])
    return {"serial": serial, "command": cmd, "sequence_id": seq,
            "echo": seen["echo"], "state": seen["state"],
            "print_error": seen["error"], "fun": seen["fun"]}


def _deep_merge(into, new):
    for k, v in new.items():
        if isinstance(v, dict) and isinstance(into.get(k), dict):
            _deep_merge(into[k], v)
        else:
            into[k] = v


# ── making sense of the report ───────────────────────────────────────

STATES = {
    "IDLE": "idle", "RUNNING": "printing", "PAUSE": "paused",
    "FINISH": "finished", "FAILED": "failed", "PREPARE": "preparing",
    "SLICING": "slicing",
}


def hms_code(attr, code):
    """HMS entries arrive as two ints; Bambu's wiki names them as four hex
    groups, e.g. 0300_0100_0001_0007."""
    return "%04X_%04X_%04X_%04X" % ((attr >> 16) & 0xFFFF, attr & 0xFFFF,
                                    (code >> 16) & 0xFFFF, code & 0xFFFF)


def hms_url(code):
    return "https://wiki.bambulab.com/en/x1/troubleshooting/hmscode/%s" % code


def parse_ams(pr):
    """Every loaded spool, by the slot number Bambu Studio shows (1-4 for the
    first AMS), plus the external spool holder."""
    slots = []
    ams = pr.get("ams") or {}
    units = ams.get("ams", []) if isinstance(ams, dict) else []
    for unit in units:
        u = int(unit.get("id", 0))
        for tray in unit.get("tray", []) or []:
            t = int(tray.get("id", 0))
            loaded = bool(tray.get("tray_type"))
            slots.append({
                "slot": u * 4 + t + 1,
                "ams": u + 1,
                "loaded": loaded,
                "type": tray.get("tray_type") or "",
                "brand": tray.get("tray_sub_brands") or "",
                "colour": _colour(tray.get("tray_color")),
                "remaining_pct": _remain(tray.get("remain")),
                "filament_id": tray.get("tray_info_idx") or "",
            })
    ext = pr.get("vt_tray")
    if isinstance(ext, dict) and ext.get("tray_type"):
        slots.append({"slot": "external", "ams": None, "loaded": True,
                      "type": ext.get("tray_type"),
                      "brand": ext.get("tray_sub_brands") or "",
                      "colour": _colour(ext.get("tray_color")),
                      "remaining_pct": _remain(ext.get("remain")),
                      "filament_id": ext.get("tray_info_idx") or ""})
    return slots


def _colour(rgba):
    """AMS colours come as RRGGBBAA; Studio and the presets use #RRGGBB."""
    if not rgba:
        return ""
    return "#" + str(rgba)[:6].upper()


def _remain(value):
    try:
        v = int(value)
    except (TypeError, ValueError):
        return None
    return v if v >= 0 else None       # -1 = unknown (non-Bambu spool)


def parse_status(pr, device=None):
    state = pr.get("gcode_state", "")
    hms = [hms_code(h.get("attr", 0), h.get("code", 0))
           for h in pr.get("hms", []) or []]
    fun = pr.get("fun")
    try:
        fun_bits = int(str(fun), 16) if fun is not None else 0
    except ValueError:
        fun_bits = 0
    out = {
        "printer": (device or {}).get("name"),
        "serial": (device or {}).get("serial"),
        "state": STATES.get(state, state.lower() or "unknown"),
        "raw_state": state,
        "job": pr.get("subtask_name") or pr.get("gcode_file") or "",
        "progress_pct": pr.get("mc_percent"),
        "layer": pr.get("layer_num"),
        "total_layers": pr.get("total_layer_num"),
        # Sources disagree on the unit; the ha-bambulab integration, which is
        # the most used, treats it as minutes.
        "remaining_min": pr.get("mc_remaining_time"),
        "nozzle_c": pr.get("nozzle_temper"),
        "nozzle_target_c": pr.get("nozzle_target_temper"),
        "bed_c": pr.get("bed_temper"),
        "bed_target_c": pr.get("bed_target_temper"),
        "chamber_c": pr.get("chamber_temper"),
        "errors": [{"code": c, "help": hms_url(c)} for c in hms],
        "print_error": pr.get("print_error") or 0,
        "ams": parse_ams(pr),
        # Firmware 01.08.02+ can require signed commands, which would block
        # pause/resume/stop from here. Read-only status is unaffected.
        "commands_need_signing": bool(fun_bits & 0x20000000),
    }
    return out


def printer_status(serial="", wait_s=STATUS_WAIT_S):
    """Everything worth knowing about the printer right now."""
    record = _require_record()
    devices = list_devices(record)
    device = pick_printer(devices, serial or os.environ.get(
        "BAMBU_PRINTER_SERIAL", "") or record.get("serial", ""))
    if not device.get("online"):
        return {"printer": device["name"], "serial": device["serial"],
                "state": "offline", "ams": [], "errors": [],
                "note": "The cloud says the printer is offline."}
    pr = fetch_report(record, device["serial"], wait_s)
    return parse_status(pr, device)


def format_status(s):
    if s.get("state") == "offline":
        return "%s is offline." % (s.get("printer") or "The printer")
    lines = ["%s: %s" % (s.get("printer") or "Printer", s["state"])]
    if s["state"] in ("printing", "paused", "preparing"):
        lines.append("  %s — %s%%, layer %s of %s, about %s min left"
                     % (s["job"] or "(unnamed job)", s.get("progress_pct"),
                        s.get("layer"), s.get("total_layers"),
                        s.get("remaining_min")))
    elif s["job"]:
        lines.append("  last job: %s" % s["job"])
    def temp(now, target):
        now = "?" if now is None else "%.0f" % float(now)
        if target:
            return "%s → %.0f °C" % (now, float(target))
        return "%s °C" % now
    lines.append("  nozzle %s, bed %s"
                 % (temp(s.get("nozzle_c"), s.get("nozzle_target_c")),
                    temp(s.get("bed_c"), s.get("bed_target_c"))))
    for e in s.get("errors", []):
        lines.append("  ! HMS %s — %s" % (e["code"], e["help"]))
    if s.get("ams"):
        lines.append("  AMS:")
        unknown = 0
        for t in s["ams"]:
            if not t["loaded"]:
                lines.append("    slot %s: empty" % t["slot"])
                continue
            name = t["brand"] if t["brand"] and t["type"] in t["brand"] \
                else " ".join(x for x in (t["brand"], t["type"]) if x)
            left = ""
            if t["remaining_pct"] is not None:
                left = ", %d%% left" % t["remaining_pct"]
            else:
                unknown += 1
            lines.append("    slot %s: %s %s%s" % (t["slot"], name, t["colour"], left))
        if unknown:
            lines.append("    (amount left isn't reported for %s — the AMS only "
                         "tracks Bambu RFID spools, and only with \"update "
                         "remaining filament\" on in the printer's AMS settings)"
                         % ("any slot" if unknown == len([t for t in s["ams"]
                                                          if t["loaded"]])
                            else "%d slot%s" % (unknown, "" if unknown == 1 else "s")))
    if s.get("commands_need_signing"):
        lines.append("  note: this firmware asks for signed commands, which may "
                     "block pause/stop from here (status is fine)")
    return "\n".join(lines)


# ── command line ─────────────────────────────────────────────────────

def _cli(argv):
    cmd = argv[1] if len(argv) > 1 else "status"
    try:
        if cmd == "login":
            email = argv[2] if len(argv) > 2 else (
                os.environ.get("BAMBU_EMAIL") or input("Bambu account email: "))
            region = "china" if "--china" in argv else "global"
            print("Signing in to Bambu as %s. The password is sent to Bambu "
                  "only and isn't stored." % email)
            password = getpass.getpass("Bambu password (hidden): ")
            record = login(email, password, input, region)
            password = None
            devices = list_devices(record)
            if devices:
                try:
                    d = pick_printer(devices, os.environ.get(
                        "BAMBU_PRINTER_SERIAL", ""))
                    record["serial"], record["printer_name"] = d["serial"], d["name"]
                except CloudError as exc:
                    print(exc)
            save_token(record)
            st = account_state(record)
            print("Signed in. Token saved to tools/bambu_cloud.local.json "
                  "(good until %s)." % st.get("expires", "about 3 months"))
            for d in devices:
                print("  %s  %s  %s  %s" % (d["name"], d["model"], d["serial"],
                                            "online" if d["online"] else "offline"))
        elif cmd == "logout":
            print("Signed out." if forget_token() else "Wasn't signed in.")
        elif cmd == "devices":
            for d in list_devices():
                print("%s  %s  %s  %s" % (d["name"], d["model"], d["serial"],
                                          "online" if d["online"] else "offline"))
        elif cmd == "account":
            print(json.dumps(account_state(), indent=2))
        elif cmd == "status":
            print(format_status(printer_status()))
        else:
            print(__doc__)
            return 2
    except CloudError as exc:
        print("Couldn't: %s" % exc)
        return 1
    except KeyboardInterrupt:
        print("\nStopped.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(_cli(sys.argv))
