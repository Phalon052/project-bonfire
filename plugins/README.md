# Plugins (Blender add-ons / extensions)

**Default rule for every plugin: use it as-is.** Read the plugin's documentation, its source code, and Blender's operator reference as needed to figure out how to drive it. No special instructions are needed unless a plugin misbehaves.

If a plugin doesn't work well out of the box, add a file `plugins/<plugin-name>.md` with instructions **for that plugin only**, using the template below. Read that file whenever the plugin is used.

## Index

| Plugin | Used for | Installed? | Notes file |
|---|---|---|---|
| BoltFactory | Screws, bolts, nuts | Yes | `boltfactory.md` |
| Extra Mesh Objects | Gears (spur, helical, bevel, crown, worm); pipe joints and other shapes | Yes (0.4.1) | `extra_mesh_objects.md` |

## Fallback

If no plugin fits, or a plugin's output isn't accurate enough for printing, generate the part directly with a Python script (e.g. involute gear teeth or thread profiles calculated from the specs). Say when this fallback is used.

## Template for a plugin file

```markdown
# <Plugin name>

- **Status:** Installed / not installed · version:
- **Where it is in Blender:** (menu path)
- **Use it for:**
- **Don't use it for:**

## Instructions specific to this plugin
- (e.g. "Always set X before Y", "Ignore the preset list", "Scale output by ...")

## Known problems and workarounds
-
```
