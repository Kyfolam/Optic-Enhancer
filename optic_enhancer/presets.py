from __future__ import annotations

"""Minimal export/import of Optic Enhancer scene props as JSON."""

import json
from pathlib import Path

import bpy
from bpy.props import StringProperty
from bpy_extras.io_utils import ExportHelper, ImportHelper

from . import host

PRESET_VERSION = 1
PRESET_KEYS = (
    "oe_bevel",
    "oe_mix",
    "oe_ao",
    "oe_ao_dist",
    "oe_subdiv",
    "oe_displace",
    "oe_auto",
    "oe_wear",
    "oe_glow",
    "oe_sss",
    "oe_hair",
    "oe_cycles",
    "oe_light_boost",
    "oe_tx_cache",
    "oe_viewport_tex",
    "oe_eevee_rt",
    "oe_thin_wall",
    "oe_caustics",
    "oe_dof",
)


def collect_scene_props(scene) -> dict:
    out = {"oe_preset_version": PRESET_VERSION, "props": {}}
    props = out["props"]
    for key in PRESET_KEYS:
        if not hasattr(scene, key):
            continue
        try:
            val = getattr(scene, key)
        except Exception:
            continue
        if isinstance(val, bool):
            props[key] = bool(val)
        elif isinstance(val, (int, float)):
            props[key] = float(val)
        else:
            props[key] = val
    return out


def apply_scene_props(scene, data: dict) -> int:
    props = data.get("props") if isinstance(data, dict) else None
    if not isinstance(props, dict):
        # Allow flat JSON without wrapper
        props = data if isinstance(data, dict) else {}
    count = 0
    for key in PRESET_KEYS:
        if key not in props:
            continue
        if not hasattr(scene, key):
            continue
        try:
            setattr(scene, key, props[key])
            count += 1
        except Exception:
            continue
    return count


class OE_OT_preset_export(bpy.types.Operator, ExportHelper):
    bl_idname = "opticenhancer.preset_export"
    bl_label = "Export OE preset"
    bl_description = "Write Optic Enhancer scene settings to a JSON file"
    bl_options = {"REGISTER"}

    filename_ext = ".json"
    filter_glob: StringProperty(default="*.json", options={"HIDDEN"})

    @classmethod
    def poll(cls, context):
        return host.is_available() and getattr(context, "scene", None) is not None

    def execute(self, context):
        scene = context.scene
        payload = collect_scene_props(scene)
        path = Path(bpy.path.abspath(self.filepath))
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        except Exception as exc:
            self.report({"ERROR"}, f"Export failed: {exc}")
            return {"CANCELLED"}
        self.report({"INFO"}, f"Exported OE preset ({len(payload.get('props', {}))} props)")
        return {"FINISHED"}


class OE_OT_preset_import(bpy.types.Operator, ImportHelper):
    bl_idname = "opticenhancer.preset_import"
    bl_label = "Import OE preset"
    bl_description = "Load Optic Enhancer scene settings from a JSON file"
    bl_options = {"REGISTER", "UNDO"}

    filename_ext = ".json"
    filter_glob: StringProperty(default="*.json", options={"HIDDEN"})

    @classmethod
    def poll(cls, context):
        return host.is_available() and getattr(context, "scene", None) is not None

    def execute(self, context):
        path = Path(bpy.path.abspath(self.filepath))
        try:
            raw = path.read_text(encoding="utf-8")
            data = json.loads(raw)
        except Exception as exc:
            self.report({"ERROR"}, f"Import failed: {exc}")
            return {"CANCELLED"}
        if not isinstance(data, dict):
            self.report({"ERROR"}, "Preset JSON must be an object")
            return {"CANCELLED"}
        n = apply_scene_props(context.scene, data)
        if n == 0:
            self.report({"WARNING"}, "No OE props applied")
            return {"CANCELLED"}
        self.report({"INFO"}, f"Imported OE preset ({n} props)")
        return {"FINISHED"}


classes = (
    OE_OT_preset_export,
    OE_OT_preset_import,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
