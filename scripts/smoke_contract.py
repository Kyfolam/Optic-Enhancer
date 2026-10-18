#!/usr/bin/env python3
"""Import Optic Enhancer without Blender and check the 2.1.0 host contract."""
from __future__ import annotations

import re
import sys
import types
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / "optic_enhancer"


def _mock_bpy() -> None:
    bpy = types.ModuleType("bpy")

    class _ID:
        bl_idname = ""
        bl_label = ""
        bl_description = ""
        bl_options = set()

        @classmethod
        def poll(cls, context):
            return True

    bpy.types = types.SimpleNamespace(
        Operator=_ID,
        Panel=_ID,
        PropertyGroup=_ID,
        AddonPreferences=_ID,
        Scene=type("Scene", (), {}),
    )
    bpy.props = types.SimpleNamespace(
        BoolProperty=lambda **k: None,
        EnumProperty=lambda **k: None,
        FloatProperty=lambda **k: None,
        StringProperty=lambda **k: None,
        CollectionProperty=lambda **k: None,
        IntProperty=lambda **k: None,
    )
    bpy.context = types.SimpleNamespace(preferences=types.SimpleNamespace(addons={}), scene=None)
    bpy.data = types.SimpleNamespace(objects={}, materials={}, images={})
    bpy.ops = types.SimpleNamespace()
    bpy.app = types.SimpleNamespace(
        version=(5, 2, 0),
        timers=types.SimpleNamespace(register=lambda *a, **k: None),
        handlers=types.SimpleNamespace(persistent=lambda f: f),
    )
    bpy.utils = types.SimpleNamespace(
        register_class=lambda cls: None,
        unregister_class=lambda cls: None,
    )
    extras = types.ModuleType("bpy_extras")
    io_utils = types.ModuleType("bpy_extras.io_utils")

    class _Helper:
        pass

    io_utils.ExportHelper = _Helper
    io_utils.ImportHelper = _Helper
    sys.modules["bpy"] = bpy
    sys.modules["bpy.props"] = bpy.props
    sys.modules["bpy.types"] = bpy.types
    sys.modules["bpy.app"] = bpy.app
    sys.modules["bpy.utils"] = bpy.utils
    sys.modules["bpy_extras"] = extras
    sys.modules["bpy_extras.io_utils"] = io_utils


def main() -> int:
    _mock_bpy()
    sys.path.insert(0, str(ROOT))
    import optic_enhancer
    from optic_enhancer import host, hook, lights, optics, panel, portrait, presets, render, wear

    assert optic_enhancer.bl_info["version"] == (1, 0, 0)
    assert optic_enhancer.bl_info["blender"] == (5, 2, 0)
    manifest = (PKG / "blender_manifest.toml").read_text(encoding="utf-8")
    ver = re.search(r'(?m)^version\s*=\s*"([^"]+)"', manifest)
    blender_min = re.search(r'(?m)^blender_version_min\s*=\s*"([^"]+)"', manifest)
    assert ver and ver.group(1) == "1.0.0", manifest
    assert blender_min and blender_min.group(1) == "5.2.0", manifest
    assert host.MIN_HOST_VERSION == (2, 1, 0), host.MIN_HOST_VERSION

    ids = {cls.bl_idname for cls in panel.classes}
    assert "OE_PT_lights" not in ids, ids
    assert "opticenhancer.light_preset" not in ids, ids
    assert "opticenhancer.uninstall" not in ids, ids
    assert "OE_PT_render" in ids, ids
    assert "OE_PT_armor" in ids and "OE_PT_portrait" in ids
    assert "opticenhancer.reset_all" in ids
    panel_src = (PKG / "panel.py").read_text(encoding="utf-8")
    assert "OE_OT_uninstall.bl_idname" not in panel_src
    from optic_enhancer import prefs
    from optic_enhancer.install import other_copies, read_zip_manifest

    pref_ids = {cls.bl_idname for cls in prefs.classes}
    assert pref_ids == {
        "opticenhancer.install_zip",
        "opticenhancer.drop_old_copy",
        "opticenhancer.uninstall",
    }, pref_ids
    kept = Path("/tmp/oe-current")
    old = Path("/tmp/oe-old")
    kept.mkdir(exist_ok=True)
    old.mkdir(exist_ok=True)
    dupes = other_copies(
        [
            {"path": str(kept), "version": "1.0.0"},
            {"path": str(old), "version": "0.9.0"},
        ],
        current=kept,
    )
    assert len(dupes) == 1 and Path(dupes[0]["path"]).resolve() == old.resolve()
    zpath = Path("/tmp/oe-not-this.zip")
    with zipfile.ZipFile(zpath, "w") as zf:
        zf.writestr("optic_enhancer/blender_manifest.toml", 'id = "optic_enhancer"\nversion = "1.0.0"\n')
    meta = read_zip_manifest(str(zpath))
    assert meta == {"id": "optic_enhancer", "version": "1.0.0"}, meta
    render_ids = {cls.bl_idname for cls in render.classes}
    assert render_ids == {
        "opticenhancer.render_look",
        "opticenhancer.generate_tx",
        "opticenhancer.copy_linking",
    }, render_ids
    preset_ids = {cls.bl_idname for cls in presets.classes}
    assert preset_ids == {
        "opticenhancer.preset_export",
        "opticenhancer.preset_import",
    }, preset_ids

    for fn in (
        hook.install,
        hook.uninstall,
        lights.apply_preset,
        lights.apply_boost,
        optics.apply_optics,
        optics.remove_optics,
        portrait.apply_portrait,
        portrait.remove_portrait,
        wear.apply_to_material,
        render.enable_look,
        render.disable_look,
        render.reapply_materials,
        host.resolve_shade_objects,
        host.version_warning,
    ):
        assert callable(fn), fn

    needed = {
        "anim": ("resolve_shade_objects",),
        "naming": ("is_eye_material", "is_glass_family", "is_transparent_family"),
        "extras": ("should_skip_lod",),
        "blender_compat": ("material_meshes", "resolve_armature"),
        "utils": ("shade_selected",),
    }
    for key, names in needed.items():
        aliases = host._SUBMODULE_ALIASES[key]
        assert aliases, key
        for name in names:
            assert isinstance(name, str) and name
    assert "shade.utils" in host._SUBMODULE_ALIASES["utils"]

    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "2.1.0" in readme
    assert "Lookdev" in readme or "lookdev" in readme.lower()
    print("smoke_contract: OK")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"smoke_contract: FAIL: {exc}", file=sys.stderr)
        raise
