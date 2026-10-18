from __future__ import annotations

"""Studio camera / lights via Apex Auto Shader ops.

Prefer apexaddon.add_camera / camera_preset. Local 3-point fallback only if
those ops fail. Hard Auto Shader dependency stays elsewhere (host helpers).
"""

import logging
import traceback

import bpy
from bpy.props import BoolProperty, FloatProperty

_log = logging.getLogger("optic_enhancer.lights")

CAMERA_NAME = "Apex Camera"
LIGHT_NAMES = ("Apex Light Left", "Apex Light Overhead", "Apex Light Right")
BASE_ENERGY = (450.0, 280.0, 160.0)
ORIG_KEY = "oe_light_energy"
_PROPS = ("oe_light_boost", "oe_dof")
_DOF_FLAG = "oe_dof_prev"
_DOF_DIST = "oe_dof_dist_prev"
_DOF_FSTOP = "oe_dof_fstop_prev"
_PRESET_KEY = "oe_cam_preset"


def _log_exc(where: str) -> None:
    try:
        _log.exception("Optic Enhancer lights %s failed", where)
    except Exception:
        pass
    try:
        print(f"[Optic Enhancer] lights {where} failed:\n{traceback.format_exc()}")
    except Exception:
        pass


def _camera_exists() -> bool:
    cam = bpy.data.objects.get(CAMERA_NAME)
    return cam is not None and getattr(cam, "type", "") == "CAMERA"


def _ops_available() -> bool:
    """True when Apex camera operators are registered."""
    try:
        return hasattr(bpy.ops.apexaddon, "add_camera") and hasattr(
            bpy.ops.apexaddon, "camera_preset"
        )
    except Exception:
        return False


def _try_add_camera() -> bool:
    if not _ops_available():
        return False
    try:
        bpy.ops.apexaddon.add_camera()
    except Exception:
        _log_exc("add_camera")
        return False
    return _camera_exists()


def _try_camera_preset(preset: str) -> bool:
    if not _ops_available():
        return False
    try:
        bpy.ops.apexaddon.camera_preset(preset=preset)
        return True
    except Exception:
        _log_exc("camera_preset")
        return False


def _fallback_rig(context) -> bool:
    """Minimal 3-point + camera when Apex ops are missing or fail."""
    scene = getattr(context, "scene", None)
    if scene is None:
        return False
    coll = scene.collection
    if not _camera_exists():
        try:
            data = bpy.data.cameras.new(CAMERA_NAME)
            cam = bpy.data.objects.new(CAMERA_NAME, data)
            coll.objects.link(cam)
            cam.location = (0.0, -3.0, 1.2)
            scene.camera = cam
        except Exception:
            _log_exc("fallback camera")
            return False
    specs = (
        (LIGHT_NAMES[0], BASE_ENERGY[0], (-1.6, -1.0, 2.2)),
        (LIGHT_NAMES[1], BASE_ENERGY[1], (0.0, 0.4, 3.2)),
        (LIGHT_NAMES[2], BASE_ENERGY[2], (1.6, -0.7, 1.4)),
    )
    for name, energy, loc in specs:
        if bpy.data.objects.get(name) is not None:
            continue
        try:
            data = bpy.data.lights.new(name, "AREA")
            data.energy = energy
            data.shape = "SQUARE"
            data.size = 1.0
            obj = bpy.data.objects.new(name, data)
            obj.location = loc
            coll.objects.link(obj)
        except Exception:
            continue
    return _camera_exists()


def _ensure_camera(context) -> bool:
    if _camera_exists():
        return True
    if _try_add_camera():
        return True
    return _fallback_rig(context)


def _host_scene_prop(name: str) -> bool:
    """True when Apex Auto Shader 2.1+ registered this Scene property."""
    try:
        return hasattr(bpy.types.Scene, name)
    except Exception:
        return False


def apply_boost(scene) -> None:
    if scene is None:
        return
    if _host_scene_prop("apex_light_boost"):
        # One multiplier. The host captures the rig energy; do not capture again.
        try:
            pct = float(getattr(scene, "oe_light_boost", 0.0) or 0.0)
        except (TypeError, ValueError):
            return
        try:
            current = float(getattr(scene, "apex_light_boost", 0.0) or 0.0)
        except (TypeError, ValueError):
            current = 0.0
        if abs(current - pct) > 1e-4:
            scene.apex_light_boost = pct
        return
    try:
        pct = float(getattr(scene, "oe_light_boost", 0.0) or 0.0)
    except (TypeError, ValueError):
        pct = 0.0
    mul = 1.0 + max(0.0, pct) / 100.0
    for name, base in zip(LIGHT_NAMES, BASE_ENERGY):
        obj = bpy.data.objects.get(name)
        if obj is None or getattr(obj, "type", "") != "LIGHT":
            continue
        data = getattr(obj, "data", None)
        if data is None:
            continue
        if obj.get(ORIG_KEY) is None:
            try:
                obj[ORIG_KEY] = float(getattr(data, "energy", base))
            except Exception:
                obj[ORIG_KEY] = float(base)
        try:
            data.energy = float(obj[ORIG_KEY]) * mul
        except Exception:
            pass


def apply_preset(context, preset: str) -> bool:
    key = preset if preset in {"front", "three_quarter", "closeup"} else "front"
    # Prefer AAS ops; create via add_camera first, fallback only if that fails.
    if not _ensure_camera(context):
        return False
    host_preset = _try_camera_preset(key)
    scene = getattr(context, "scene", None)
    if scene is not None:
        try:
            scene[_PRESET_KEY] = key
        except Exception:
            pass
    # Host 2.1 camera_preset already applies apex_light_boost and close-up DOF.
    if not host_preset or not _host_scene_prop("apex_light_boost"):
        apply_boost(scene)
    if not host_preset or not _host_scene_prop("apex_closeup_dof"):
        _sync_dof(context)
    return True


def _studio_camera(context):
    found = bpy.data.objects.get(CAMERA_NAME)
    if found is not None and getattr(found, "type", "") == "CAMERA":
        return found
    scene = getattr(context, "scene", None)
    cam = getattr(scene, "camera", None) if scene is not None else None
    if cam is not None and getattr(cam, "type", "") == "CAMERA":
        return cam
    return None


def _sync_dof(context) -> None:
    """Shallow DOF only for the close-up preset, and only when oe_dof is on."""
    scene = getattr(context, "scene", None)
    cam = _studio_camera(context)
    if scene is None or cam is None:
        return
    if _host_scene_prop("apex_closeup_dof"):
        try:
            scene.apex_closeup_dof = bool(getattr(scene, "oe_dof", False))
        except Exception:
            pass
        return
    data = getattr(cam, "data", None)
    dof = getattr(data, "dof", None) if data is not None else None
    if dof is None or not hasattr(dof, "use_dof"):
        return
    preset = str(scene.get(_PRESET_KEY) or "")
    want = preset == "closeup" and bool(getattr(scene, "oe_dof", False))
    if want:
        if cam.get(_DOF_FLAG) is None:
            try:
                cam[_DOF_FLAG] = 1 if bool(dof.use_dof) else 0
            except Exception:
                cam[_DOF_FLAG] = 0
            try:
                cam[_DOF_DIST] = float(getattr(dof, "focus_distance", 0.35))
            except Exception:
                cam[_DOF_DIST] = 0.35
            try:
                cam[_DOF_FSTOP] = float(getattr(dof, "aperture_fstop", 2.8))
            except Exception:
                cam[_DOF_FSTOP] = 2.8
        try:
            dof.focus_object = None
        except Exception:
            pass
        dist = 0.35
        target = getattr(context, "active_object", None)
        if target is not None and target != cam:
            try:
                delta = cam.matrix_world.translation - target.matrix_world.translation
                dist = float(delta.length)
            except Exception:
                dist = 0.35
        try:
            dof.use_dof = True
            dof.focus_distance = max(0.05, dist)
        except Exception:
            pass
        if hasattr(dof, "aperture_fstop"):
            try:
                dof.aperture_fstop = 2.8
            except Exception:
                pass
        return
    if cam.get(_DOF_FLAG) is None:
        return
    try:
        dof.use_dof = bool(int(cam[_DOF_FLAG]))
    except Exception:
        pass
    if hasattr(dof, "focus_distance") and cam.get(_DOF_DIST) is not None:
        try:
            dof.focus_distance = float(cam[_DOF_DIST])
        except Exception:
            pass
    if hasattr(dof, "aperture_fstop") and cam.get(_DOF_FSTOP) is not None:
        try:
            dof.aperture_fstop = float(cam[_DOF_FSTOP])
        except Exception:
            pass
    for key in (_DOF_FLAG, _DOF_DIST, _DOF_FSTOP):
        if key in cam:
            try:
                del cam[key]
            except Exception:
                pass


def _dof_update(self, context):
    try:
        _sync_dof(context)
    except Exception:
        pass


def _boost_update(self, context):
    try:
        apply_boost(getattr(context, "scene", None))
    except Exception:
        pass


def register_props():
    bpy.types.Scene.oe_light_boost = FloatProperty(
        name="Light boost",
        description="Multiply Apex studio light energy. 0% keeps Auto Shader values.",
        default=0.0,
        min=0.0,
        max=200.0,
        soft_min=0.0,
        soft_max=100.0,
        step=100,
        precision=0,
        subtype="PERCENTAGE",
        update=_boost_update,
    )
    bpy.types.Scene.oe_dof = BoolProperty(
        name="Close-up DOF",
        description="Shallow depth of field on the studio camera when the close-up preset is active. Focuses the active object.",
        default=False,
        update=_dof_update,
    )


def unregister_props():
    for attr in _PROPS:
        if hasattr(bpy.types.Scene, attr):
            delattr(bpy.types.Scene, attr)
