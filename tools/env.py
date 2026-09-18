"""
Bonfire machine-local settings: reads `.env` from the project root.

`.env` holds the values that differ from PC to PC (where this folder is, where
Blender is installed). It is gitignored; `.env.example` is the tracked template.

Run inside Blender (via the Blender MCP) or any Python 3:

    import os, runpy
    env = runpy.run_path(os.path.join(BONFIRE, "tools", "env.py"))   # BONFIRE = this folder

    env["read"]()                 # {'BONFIRE_HOME': ..., 'BLENDER_PATH': ...}
    env["get"]("BLENDER_PATH")    # one value: os.environ first, then .env
    env["load"]()                 # copy .env into os.environ for this process
    print(env["report"]())        # what is set, what is missing, what is wrong
    print(env["apply_command"]())  # commands to put BLENDER_* in the user environment

Two different readers, which is the whole reason this file exists:

- **Bonfire's own tools** (this process): `load()` is enough. Nothing is
  written outside this folder.
- **The Blender MCP server**: started by the Claude desktop app, not by us, so
  it never sees `.env`. It reads `BLENDER_PATH`, `BLENDER_MCP_HOST` and
  `BLENDER_MCP_PORT` from the *user* environment. `apply_command()` prints the
  `setx` lines that copy them there; run them yourself in a terminal, then
  restart the Claude desktop app so it picks them up.

Format: `KEY=value`, one per line. `#` starts a comment. Surrounding quotes are
stripped. Values are used verbatim otherwise, so Windows paths with spaces and
backslashes need no escaping. A key with an empty value counts as unset, so a
`.env` copied straight from the template behaves the same as no `.env` at all.
"""
import os
import subprocess

# Keys the Blender MCP server reads from the user environment (it cannot read .env).
MCP_KEYS = ("BLENDER_PATH", "BLENDER_MCP_HOST", "BLENDER_MCP_PORT")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # Project Bonfire/
ENV_FILE = os.path.join(ROOT, ".env")
ENV_EXAMPLE = os.path.join(ROOT, ".env.example")


def user_env(key):
    """
    The value stored in the *user* environment, not this process's copy of it.

    That distinction matters: load() sets variables inside whatever process
    calls it, so checking os.environ afterwards always says "set" and tells you
    nothing about what the Claude desktop app will see when it next starts.
    Returns None when unset, or when the user environment can't be read.
    """
    if os.name != "nt":
        return None                                  # POSIX: it lives in a shell profile, not a store
    try:
        import winreg                                # pylint: disable=import-outside-toplevel
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as k:
            value, _ = winreg.QueryValueEx(k, key)
            return value
    except OSError:
        return None


def read(path=None):
    """Parse the .env file into a dict. Missing file -> {}."""
    path = path or ENV_FILE
    values = {}
    if not os.path.isfile(path):
        return values
    with open(path, encoding="utf-8") as fh:
        for raw in fh:
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            if line.lower().startswith("export "):
                line = line[7:].strip()
            if "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
                value = value[1:-1]
            if key and value:                # empty value == unset (see .env.example)
                values[key] = value
    return values


def load(overwrite=False, path=None):
    """
    Copy .env values into os.environ for this process only.

    Existing environment variables win unless overwrite=True, so a real
    environment variable can always override the file.
    Returns the keys that were set.
    """
    applied = []
    for key, value in read(path).items():
        if overwrite or not os.environ.get(key):
            os.environ[key] = value
            applied.append(key)
    return applied


def get(key, default=None):
    """One value: the environment first, then .env, then default."""
    return os.environ.get(key) or read().get(key, default)


def apply_command(keys=MCP_KEYS):
    """
    The commands that copy .env values into the *user* environment, where the
    Claude desktop app's Blender MCP server can see them. Nothing is run here —
    changing the user environment is left to you.
    """
    values = read()
    missing = [k for k in keys if not values.get(k)]
    lines = []
    if os.name == "nt":
        lines += ['setx {:s} "{:s}"'.format(k, values[k]) for k in keys if values.get(k)]
        note = ("Run these once in PowerShell or Command Prompt, then restart the Claude\n"
                "desktop app (setx only affects programs started afterwards).")
    else:
        lines += ['export {:s}="{:s}"'.format(k, values[k]) for k in keys if values.get(k)]
        note = "Add these to your shell profile (~/.profile or ~/.zshrc), then restart the app."
    out = "\n".join(lines) or "(nothing to set — .env has none of: {:s})".format(", ".join(keys))
    if missing:
        out += "\n\nMissing from .env: {:s}".format(", ".join(missing))
    return "{:s}\n\n{:s}".format(out, note)


def report():
    """Readable status: the file, the values, and whether they point at real things."""
    values = read()
    out = ["Project Bonfire .env"]
    out.append("  file:    {:s}{:s}".format(ENV_FILE, "" if os.path.isfile(ENV_FILE) else "   (MISSING)"))
    out.append("  example: {:s}{:s}".format(ENV_EXAMPLE, "" if os.path.isfile(ENV_EXAMPLE) else "   (MISSING)"))
    if not values:
        out.append("  no values — copy .env.example to .env and fill it in")
        return "\n".join(out)

    out.append("")
    out.append("  {:<18} {:<8} {:<9} value".format("key", "in .env", "user env"))
    for key in sorted(set(list(values) + list(MCP_KEYS) + ["BONFIRE_HOME"])):
        in_file = "yes" if values.get(key) else "-"
        stored = user_env(key)
        if stored is None:
            in_env = "-"
        elif values.get(key) and stored != values[key]:
            in_env = "differs"
        else:
            in_env = "yes"
        out.append("  {:<18} {:<8} {:<9} {:s}".format(key, in_file, in_env, values.get(key, "")))

    out.append("")
    if not values.get("BLENDER_PATH"):
        out.append("  ! BLENDER_PATH is not filled in — background (CLI) mode will not work")
    home = values.get("BONFIRE_HOME")
    if home and os.path.normcase(os.path.abspath(home)) != os.path.normcase(ROOT):
        out.append("  ! BONFIRE_HOME does not point at this folder ({:s})".format(ROOT))
    blender = values.get("BLENDER_PATH")
    if blender and not os.path.isfile(blender):
        out.append("  ! BLENDER_PATH is not a file on this machine")
    elif blender:
        out.append("  Blender found: {:s}".format(_blender_version(blender)))

    if os.name == "nt":
        pending = [k for k in MCP_KEYS if values.get(k) and user_env(k) != values[k]]
        if pending:
            out.append("  Not in the user environment yet (or out of date): {:s}".format(", ".join(pending)))
            out.append("  -> print apply_command(), run what it shows, then restart the desktop app")
        else:
            out.append("  User environment matches .env — the MCP server sees it once the app restarts")
    return "\n".join(out)


def _blender_version(blender):
    """`blender --version` first line, or the error, for report()."""
    try:
        done = subprocess.run([blender, "--version"], capture_output=True, text=True, timeout=30)
        return (done.stdout or done.stderr).strip().splitlines()[0]
    except Exception as ex:                                  # pylint: disable=broad-exception-caught
        return "could not run it: {!r}".format(ex)
