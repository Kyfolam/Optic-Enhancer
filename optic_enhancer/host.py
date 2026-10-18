from __future__ import annotations

"""Detect Apex Auto Shader and borrow its mesh/material helpers when present.

Fail closed: no local fallbacks. Missing host → empty / None / False.
Soft pin: warn in UI when host bl_info version is older than MIN_HOST_VERSION.
2.1.0 is the joint-release floor: studio light boost and close-up DOF live on
the host. Optic Enhancer drives those instead of stacking a second multiplier.

Host modules may live flat (anim.py, extras.py, naming.py) or in packages
(anim/, shade/extras.py, naming/). Look up both.
"""

import importlib
import sys

import bpy

HOST_NAME = "Apex Auto Shader"
_HOST_TAIL = "apex_auto_shader"
MIN_HOST_VERSION = (2, 1, 0)

# Preferred dotted names under the host package, first hit wins.
_SUBMODULE_ALIASES = {
    "anim": ("anim", "anim.character", "anim_character"),
    "naming": ("naming", "naming.tex", "naming_tex"),
    "extras": ("extras", "shade.extras"),
    "blender_compat": ("blender_compat",),
    "utils": ("utils", "shade.utils"),
}


def is_available() -> bool:
    try:
        addons = bpy.context.preferences.addons
        for key in addons.keys():
            if key == _HOST_TAIL or key.endswith("." + _HOST_TAIL):
                return True
    except Exception:
        pass
    for name in sys.modules:
        if name == _HOST_TAIL or name.endswith("." + _HOST_TAIL):
            return True
    try:
        import addon_utils

        for mod in addon_utils.modules():
            info = addon_utils.module_bl_info(mod) or {}
            if info.get("name") == HOST_NAME:
                loaded, _default = addon_utils.check(mod.__name__)
                if loaded:
                    return True
    except Exception:
        pass
    return False


def module():
    if _HOST_TAIL in sys.modules:
        return sys.modules[_HOST_TAIL]
    for name, mod in sys.modules.items():
        if name.endswith("." + _HOST_TAIL):
            return mod
    return None


def host_bl_info() -> dict:
    """Return Apex Auto Shader bl_info when discoverable, else {}."""
    host = module()
    if host is not None:
        info = getattr(host, "bl_info", None)
        if isinstance(info, dict) and info:
            return info
    try:
        import addon_utils

        for mod in addon_utils.modules():
            info = addon_utils.module_bl_info(mod) or {}
            if info.get("name") == HOST_NAME:
                return dict(info)
            name = getattr(mod, "__name__", "") or ""
            if name == _HOST_TAIL or name.endswith("." + _HOST_TAIL):
                return dict(info)
    except Exception:
        pass
    return {}


def host_version() -> tuple[int, ...] | None:
    """Return host (major, minor, patch) or None if unknown."""
    info = host_bl_info()
    ver = info.get("version")
    if not isinstance(ver, (tuple, list)) or len(ver) < 2:
        return None
    out: list[int] = []
    for part in list(ver)[:3]:
        try:
            out.append(int(part))
        except (TypeError, ValueError):
            return None
    while len(out) < 3:
        out.append(0)
    return tuple(out)


def meets_min_version() -> bool:
    """True when host is present and bl_info version >= MIN_HOST_VERSION."""
    if not is_available():
        return False
    ver = host_version()
    if ver is None:
        return False
    return ver >= MIN_HOST_VERSION


def version_warning() -> str | None:
    """UI string when host is loaded but older than the soft pin, else None."""
    if not is_available():
        return None
    ver = host_version()
    need = ".".join(str(x) for x in MIN_HOST_VERSION)
    if ver is None:
        return f"Apex Auto Shader version unknown — need {need}+"
    if ver < MIN_HOST_VERSION:
        have = ".".join(str(x) for x in ver)
        return f"Apex Auto Shader {have} is old — need {need}+"
    return None


def _walk_attr(root, dotted: str):
    cur = root
    for part in dotted.split("."):
        cur = getattr(cur, part, None)
        if cur is None:
            return None
    return cur


def submodule(key: str):
    """Return a host submodule by stable alias (anim, naming, extras, …)."""
    host = module()
    if host is None:
        return None
    pkg = getattr(host, "__name__", "") or _HOST_TAIL
    for dotted in _SUBMODULE_ALIASES.get(key, (key,)):
        found = _walk_attr(host, dotted)
        if found is not None:
            return found
        qual = f"{pkg}.{dotted}"
        if qual in sys.modules:
            return sys.modules[qual]
        try:
            return importlib.import_module(qual)
        except Exception:
            continue
    return None


def utils_module():
    """Host utils module (shade_selected hook target)."""
    return submodule("utils")


def _call(mod_name: str, func_name: str, *args, **kwargs):
    sub = submodule(mod_name)
    if sub is None:
        return None
    fn = getattr(sub, func_name, None)
    if fn is None:
        return None
    try:
        return fn(*args, **kwargs)
    except Exception:
        return None


def resolve_shade_objects(context) -> list:
    found = _call("anim", "resolve_shade_objects", context)
    if not found:
        return []
    return [o for o in found if o is not None and o.type in {"ARMATURE", "MESH"}]


def material_meshes(obj) -> list:
    found = _call("blender_compat", "material_meshes", obj)
    if found is None:
        return []
    return found


def resolve_armature(obj):
    return _call("blender_compat", "resolve_armature", obj)


def is_eye_material(name: str) -> bool:
    found = _call("naming", "is_eye_material", name)
    return bool(found) if found is not None else False


def is_glass_family(name: str) -> bool:
    found = _call("naming", "is_glass_family", name)
    return bool(found) if found is not None else False


def is_transparent_family(name: str) -> bool:
    found = _call("naming", "is_transparent_family", name)
    return bool(found) if found is not None else False


def should_skip_lod(mesh) -> bool:
    found = _call("extras", "should_skip_lod", mesh)
    return bool(found) if found is not None else False
