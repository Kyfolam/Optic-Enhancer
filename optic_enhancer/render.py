from __future__ import annotations

"""Blender 5.2 lookdev. Reversible scene render settings and local material tweaks.

Does not edit shared Apex node groups. Thin Wall and Random Walk only touch
Principled BSDFs that live on the material itself.
"""

import json

import bpy
from bpy.props import BoolProperty, FloatProperty

from .host import material_meshes, resolve_shade_objects

FLAG = "oe_render_on"
STORE_KEY = "oe_render_store"
THIN_PREV = "oe_thin_wall_prev"
SSS_PREV = "oe_sss_method_prev"

_THIN_PARTS = (
    "hair",
    "lash",
    "brow",
    "fur",
    "cloth",
    "fabric",
    "cape",
    "banner",
    "flag",
    "skirt",
    "coat",
    "paper",
    "leaf",
    "card",
    "ribbon",
    "veil",
    "scarf",
    "wing",
)
_THIN_SKIP = (
    "eye",
    "glass",
    "skin",
    "head",
    "face",
    "metal",
    "armor",
    "plate",
    "iris",
    "teeth",
)
_SKIN_PARTS = ("skin", "head", "face")
_PROPS = (
    "oe_tx_cache",
    "oe_viewport_tex",
    "oe_eevee_rt",
    "oe_thin_wall",
    "oe_caustics",
)

_CACHE_PATHS = (
    "render.use_texture_cache",
    "render.use_auto_generate_texture_cache",
)
_CYCLES_PATHS = (
    "cycles.use_adaptive_sampling",
    "cycles.use_denoising",
    "cycles.denoiser",
    "cycles.use_light_tree",
    "cycles.transparent_max_bounces",
    "cycles.blur_glossy",
    "cycles.sample_clamp_indirect",
    "cycles.texture_resolution",
    "cycles.texture_resolution_render",
    "cycles.caustics_reflective",
    "cycles.caustics_refractive",
    "render.use_high_quality_normals",
    "world.cycles.use_shadows",
)
_EEVEE_PATHS = (
    "eevee.use_raytracing",
    "eevee.ray_tracing_method",
    "eevee.ray_tracing_options.use_backface_hit",
    "eevee.ray_tracing_options.backface_radiance_scale",
    "eevee.ray_tracing_options.screen_trace_quality",
    "eevee.ray_tracing_options.use_denoise",
    "eevee.ray_tracing_options.denoise_bilateral",
    "eevee.use_fast_gi",
    "eevee.fast_gi_method",
    "eevee.use_overscan",
    "eevee.overscan_size",
    "eevee.use_shadows",
    "eevee.shadow_pool_size",
    "eevee.shadow_ray_count",
    "eevee.taa_render_samples",
    "eevee.taa_samples",
)


def blender_52() -> bool:
    try:
        return tuple(bpy.app.version) >= (5, 2, 0)
    except Exception:
        return False


def look_is_on(scene) -> bool:
    return bool(scene is not None and scene.get(FLAG))


def _load_store(scene) -> dict:
    raw = scene.get(STORE_KEY) if scene is not None else None
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _save_store(scene, data: dict) -> None:
    try:
        scene[STORE_KEY] = json.dumps(data, sort_keys=True)
    except Exception:
        pass


def _parent_attr(scene, path: str):
    parts = path.split(".")
    cur = scene
    for part in parts[:-1]:
        cur = getattr(cur, part, None)
        if cur is None:
            return None, parts[-1]
    return cur, parts[-1]


def _capture(store: dict, path: str, holder, attr: str) -> None:
    if path in store:
        return
    try:
        val = getattr(holder, attr)
    except Exception:
        return
    if isinstance(val, bool):
        store[path] = bool(val)
    elif isinstance(val, int) and not isinstance(val, bool):
        store[path] = int(val)
    elif isinstance(val, float):
        store[path] = float(val)
    else:
        try:
            store[path] = str(val)
        except Exception:
            pass


def _assign(holder, attr: str, value) -> bool:
    try:
        current = getattr(holder, attr)
    except Exception:
        return False
    try:
        if isinstance(current, bool):
            setattr(holder, attr, bool(value))
        elif isinstance(current, int) and not isinstance(current, bool):
            setattr(holder, attr, int(value))
        elif isinstance(current, float):
            setattr(holder, attr, float(value))
        elif isinstance(current, str):
            setattr(holder, attr, str(value))
        else:
            setattr(holder, attr, value)
        return True
    except Exception:
        try:
            setattr(holder, attr, value)
            return True
        except Exception:
            return False


def _set(scene, store: dict, path: str, value) -> bool:
    holder, attr = _parent_attr(scene, path)
    if holder is None or not hasattr(holder, attr):
        return False
    _capture(store, path, holder, attr)
    return _assign(holder, attr, value)


def _set_at_least(scene, store: dict, path: str, minimum: float) -> bool:
    holder, attr = _parent_attr(scene, path)
    if holder is None or not hasattr(holder, attr):
        return False
    _capture(store, path, holder, attr)
    try:
        current = float(getattr(holder, attr))
    except (TypeError, ValueError):
        return False
    if current >= float(minimum):
        return True
    return _assign(holder, attr, minimum)


def _set_enum_at_least(scene, store: dict, path: str, minimum: int) -> bool:
    holder, attr = _parent_attr(scene, path)
    if holder is None or not hasattr(holder, attr):
        return False
    _capture(store, path, holder, attr)
    try:
        current = int(getattr(holder, attr))
    except (TypeError, ValueError):
        return False
    if current >= minimum:
        return True
    if _assign(holder, attr, str(minimum)):
        return True
    return _assign(holder, attr, int(minimum))


def _restore_paths(scene, store: dict, paths) -> None:
    for path in paths:
        if path not in store:
            continue
        holder, attr = _parent_attr(scene, path)
        if holder is None or not hasattr(holder, attr):
            continue
        _assign(holder, attr, store[path])


def _targets(context) -> list:
    selected = list(getattr(context, "selected_objects", []) or [])
    meshes = [o for o in selected if o is not None and getattr(o, "type", "") == "MESH"]
    if not meshes:
        active = getattr(context, "active_object", None)
        if active is not None and getattr(active, "type", "") == "MESH":
            meshes = [active]
    if meshes:
        return meshes
    return [
        o
        for o in resolve_shade_objects(context)
        if o is not None and o.type in {"ARMATURE", "MESH"}
    ]


def _mesh_materials(mesh) -> list:
    mats = []
    data = getattr(mesh, "data", None)
    slots = getattr(data, "materials", None) if data is not None else None
    if slots:
        mats.extend(list(slots))
    active = getattr(mesh, "active_material", None)
    if active is not None and active not in mats:
        mats.append(active)
    return mats


def _local_material(mat) -> bool:
    if mat is None:
        return False
    if getattr(mat, "library", None) is not None:
        return False
    if getattr(mat, "override_library", None) is not None:
        return False
    return True


def _is_principled(node) -> bool:
    return (
        getattr(node, "bl_idname", "") == "ShaderNodeBsdfPrincipled"
        or getattr(node, "type", "") == "BSDF_PRINCIPLED"
    )


def _name_has(name: str, parts) -> bool:
    low = (name or "").lower()
    return any(part in low for part in parts)


def _thin_material(mat) -> bool:
    name = getattr(mat, "name", "") or ""
    if _name_has(name, _THIN_SKIP):
        return False
    return _name_has(name, _THIN_PARTS)


def _skin_material(mat) -> bool:
    name = getattr(mat, "name", "") or ""
    if _name_has(name, ("eye", "glass", "hair", "lash", "brow")):
        return False
    return _name_has(name, _SKIN_PARTS)


def _bool_socket(node, name: str):
    try:
        return node.inputs.get(name)
    except Exception:
        return None


def _read_bool_socket(sock) -> bool:
    try:
        return bool(sock.default_value)
    except Exception:
        return False


def _write_bool_socket(sock, value: bool) -> bool:
    try:
        sock.default_value = bool(value)
        return True
    except Exception:
        try:
            sock.default_value = 1 if value else 0
            return True
        except Exception:
            return False


def _iter_target_materials(objects):
    seen: set[int] = set()
    for obj in objects or []:
        for mesh in material_meshes(obj):
            for mat in _mesh_materials(mesh):
                if mat is None or id(mat) in seen:
                    continue
                seen.add(id(mat))
                yield mat


def _apply_thin_node(node) -> bool:
    sock = _bool_socket(node, "Thin Wall")
    if sock is None or getattr(sock, "is_linked", False):
        return False
    if node.get(THIN_PREV) is None:
        try:
            node[THIN_PREV] = 1 if _read_bool_socket(sock) else 0
        except Exception:
            node[THIN_PREV] = 0
    return _write_bool_socket(sock, True)


def _restore_thin_node(node) -> bool:
    prev = node.get(THIN_PREV)
    if prev is None:
        return False
    sock = _bool_socket(node, "Thin Wall")
    if sock is not None and not getattr(sock, "is_linked", False):
        _write_bool_socket(sock, bool(int(prev)))
    try:
        del node[THIN_PREV]
    except Exception:
        pass
    return True


def _apply_skin_node(node) -> bool:
    if not hasattr(node, "subsurface_method"):
        return False
    try:
        current = str(node.subsurface_method)
    except Exception:
        return False
    if current != "RANDOM_WALK_LEGACY":
        return False
    if node.get(SSS_PREV) is None:
        try:
            node[SSS_PREV] = current
        except Exception:
            return False
    try:
        node.subsurface_method = "RANDOM_WALK"
    except Exception:
        return False
    return True


def _restore_skin_node(node) -> bool:
    prev = node.get(SSS_PREV)
    if prev is None:
        return False
    if hasattr(node, "subsurface_method"):
        try:
            node.subsurface_method = str(prev)
        except Exception:
            pass
    try:
        del node[SSS_PREV]
    except Exception:
        pass
    return True


def _walk_material_nodes(mat):
    tree = getattr(mat, "node_tree", None)
    if tree is None:
        return
    for node in tree.nodes:
        if _is_principled(node):
            yield node


def apply_material_tweaks(objects, scene) -> int:
    """Thin Wall on thin-card materials, new Random Walk on legacy skin."""
    if scene is None or not getattr(scene, "oe_thin_wall", True):
        remove_material_tweaks(None)
        return 0
    count = 0
    for mat in _iter_target_materials(objects):
        if not _local_material(mat):
            continue
        thin = _thin_material(mat)
        skin = _skin_material(mat)
        if not thin and not skin:
            continue
        hit = False
        for node in _walk_material_nodes(mat):
            if thin and _apply_thin_node(node):
                hit = True
            if skin and _apply_skin_node(node):
                hit = True
        if hit:
            count += 1
    return count


def remove_material_tweaks(objects=None) -> int:
    """Restore tagged Principled nodes. objects=None scans every material."""
    count = 0
    if objects is None:
        mats = list(bpy.data.materials)
    else:
        mats = list(_iter_target_materials(objects))
    for mat in mats:
        if mat is None:
            continue
        hit = False
        for node in _walk_material_nodes(mat):
            if _restore_thin_node(node) or _restore_skin_node(node):
                hit = True
        if hit:
            count += 1
    return count


def _apply_cache(scene, store: dict) -> None:
    if not getattr(scene, "oe_tx_cache", True):
        _restore_paths(scene, store, _CACHE_PATHS)
        return
    _set(scene, store, "render.use_texture_cache", True)
    _set(scene, store, "render.use_auto_generate_texture_cache", True)


def _viewport_factor(scene) -> float:
    try:
        pct = float(getattr(scene, "oe_viewport_tex", 100.0))
    except (TypeError, ValueError):
        pct = 100.0
    return max(0.1, min(1.0, pct / 100.0))


def _apply_cycles(scene, store: dict) -> None:
    _set(scene, store, "cycles.use_adaptive_sampling", True)
    _set(scene, store, "cycles.use_denoising", True)
    _set(scene, store, "cycles.denoiser", "OPENIMAGEDENOISE")
    _set(scene, store, "cycles.use_light_tree", True)
    _set_at_least(scene, store, "cycles.transparent_max_bounces", 16)
    _set_at_least(scene, store, "cycles.blur_glossy", 0.5)
    holder, attr = _parent_attr(scene, "cycles.sample_clamp_indirect")
    if holder is not None and hasattr(holder, attr):
        _capture(store, "cycles.sample_clamp_indirect", holder, attr)
        try:
            current = float(getattr(holder, attr))
        except (TypeError, ValueError):
            current = 10.0
        if current <= 0.0:
            _assign(holder, attr, 10.0)
    factor = _viewport_factor(scene)
    _set(scene, store, "cycles.texture_resolution", factor)
    _set(scene, store, "cycles.texture_resolution_render", 1.0)
    caustics = bool(getattr(scene, "oe_caustics", False))
    _set(scene, store, "cycles.caustics_reflective", caustics)
    _set(scene, store, "cycles.caustics_refractive", caustics)
    _set(scene, store, "render.use_high_quality_normals", True)
    _set(scene, store, "world.cycles.use_shadows", True)


def _apply_eevee(scene, store: dict) -> None:
    if not getattr(scene, "oe_eevee_rt", True):
        _restore_paths(scene, store, _EEVEE_PATHS)
        return
    _set(scene, store, "eevee.use_raytracing", True)
    _set(scene, store, "eevee.ray_tracing_method", "SCREEN")
    _set(scene, store, "eevee.ray_tracing_options.use_backface_hit", True)
    _set(scene, store, "eevee.ray_tracing_options.backface_radiance_scale", 0.35)
    _set_at_least(scene, store, "eevee.ray_tracing_options.screen_trace_quality", 0.35)
    _set(scene, store, "eevee.ray_tracing_options.use_denoise", True)
    _set(scene, store, "eevee.ray_tracing_options.denoise_bilateral", True)
    _set(scene, store, "eevee.use_fast_gi", True)
    _set(scene, store, "eevee.fast_gi_method", "GLOBAL_ILLUMINATION")
    _set(scene, store, "eevee.use_overscan", True)
    _set_at_least(scene, store, "eevee.overscan_size", 5.0)
    _set(scene, store, "eevee.use_shadows", True)
    _set_enum_at_least(scene, store, "eevee.shadow_pool_size", 1024)
    _set_at_least(scene, store, "eevee.shadow_ray_count", 2)
    _set_at_least(scene, store, "eevee.taa_render_samples", 64)
    _set_at_least(scene, store, "eevee.taa_samples", 16)


def enable_look(context) -> tuple[bool, str]:
    scene = getattr(context, "scene", None)
    if scene is None:
        return False, "No scene"
    if not blender_52():
        return False, "Lookdev needs Blender 5.2 or newer"
    store = _load_store(scene)
    _apply_cache(scene, store)
    _apply_cycles(scene, store)
    _apply_eevee(scene, store)
    _save_store(scene, store)
    n = 0
    try:
        n = apply_material_tweaks(_targets(context), scene)
    except Exception:
        n = 0
    try:
        scene[FLAG] = 1
    except Exception:
        pass
    return True, f"Lookdev render on ({n} material tweak(s))"


def disable_look(context) -> str:
    scene = getattr(context, "scene", None)
    if scene is None:
        return "No scene"
    store = _load_store(scene)
    _restore_paths(scene, store, _CACHE_PATHS + _CYCLES_PATHS + _EEVEE_PATHS)
    n = 0
    try:
        n = remove_material_tweaks(None)
    except Exception:
        n = 0
    for key in (STORE_KEY, FLAG):
        if key in scene:
            try:
                del scene[key]
            except Exception:
                pass
    return f"Lookdev render restored ({n} material tweak(s))"


def refresh_look(context) -> None:
    if not look_is_on(getattr(context, "scene", None)):
        return
    enable_look(context)


def reapply_materials(objects, scene) -> None:
    """After a shade, keep thin-wall tweaks if lookdev is already on."""
    if not look_is_on(scene):
        return
    try:
        apply_material_tweaks(objects, scene)
    except Exception:
        pass


def _look_update(self, context):
    try:
        refresh_look(context)
    except Exception:
        pass


class OE_OT_render_look(bpy.types.Operator):
    bl_idname = "opticenhancer.render_look"
    bl_label = "Lookdev render"
    bl_description = (
        "Toggle Blender 5.2 lookdev: texture cache, EEVEE ray tracing, "
        "Thin Wall on local hair/cloth shaders. Restores previous settings."
    )
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        from . import host

        return host.is_available() and getattr(context, "scene", None) is not None

    def execute(self, context):
        if not blender_52():
            self.report({"ERROR"}, "Lookdev needs Blender 5.2 or newer")
            return {"CANCELLED"}
        if look_is_on(context.scene):
            self.report({"INFO"}, disable_look(context))
            return {"FINISHED"}
        ok, message = enable_look(context)
        if not ok:
            self.report({"ERROR"}, message)
            return {"CANCELLED"}
        self.report({"INFO"}, message)
        return {"FINISHED"}


class OE_OT_generate_tx(bpy.types.Operator):
    bl_idname = "opticenhancer.generate_tx"
    bl_label = "Generate tx"
    bl_description = (
        "Build Cycles texture-cache files for images used by shaders. "
        "Writes .tx files (disk space). Needs Blender 5.2."
    )
    bl_options = {"REGISTER"}

    @classmethod
    def poll(cls, context):
        from . import host

        return host.is_available() and getattr(context, "scene", None) is not None

    def execute(self, context):
        if not blender_52():
            self.report({"ERROR"}, "Texture cache needs Blender 5.2 or newer")
            return {"CANCELLED"}
        scene = context.scene
        try:
            if not bool(getattr(scene, "oe_tx_cache", True)):
                scene.oe_tx_cache = True
        except Exception:
            pass
        rnd = scene.render
        try:
            if hasattr(rnd, "use_texture_cache"):
                rnd.use_texture_cache = True
            if hasattr(rnd, "use_auto_generate_texture_cache"):
                rnd.use_auto_generate_texture_cache = True
        except Exception:
            pass
        op = getattr(getattr(bpy.ops, "render", None), "generate_texture_cache", None)
        if op is None:
            self.report({"ERROR"}, "render.generate_texture_cache is not available")
            return {"CANCELLED"}
        try:
            result = op()
        except RuntimeError as exc:
            self.report({"ERROR"}, f"Generate tx failed: {exc}")
            return {"CANCELLED"}
        if result is not None and "CANCELLED" in result:
            self.report({"WARNING"}, "Texture cache generate was cancelled")
            return {"CANCELLED"}
        self.report({"INFO"}, "Texture cache generate finished")
        return {"FINISHED"}


class OE_OT_copy_linking(bpy.types.Operator):
    bl_idname = "opticenhancer.copy_linking"
    bl_label = "Copy light linking"
    bl_description = (
        "Copy light linking and shadow linking from the active object "
        "onto the other selected objects"
    )
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        from . import host

        active = getattr(context, "active_object", None)
        selected = list(getattr(context, "selected_objects", []) or [])
        return host.is_available() and active is not None and len(selected) >= 2

    def execute(self, context):
        op = getattr(getattr(bpy.ops, "object", None), "make_links_data", None)
        if op is None:
            self.report({"ERROR"}, "object.make_links_data is not available")
            return {"CANCELLED"}
        done = []
        for kind in ("LIGHT_LINKING", "SHADOW_LINKING"):
            try:
                result = op(type=kind)
            except Exception as exc:
                self.report({"WARNING"}, f"{kind} failed: {exc}")
                continue
            if result is None or "FINISHED" in result:
                done.append(kind.replace("_", " ").lower())
        if not done:
            self.report({"ERROR"}, "Could not copy light or shadow linking")
            return {"CANCELLED"}
        self.report({"INFO"}, "Copied " + " and ".join(done))
        return {"FINISHED"}


classes = (
    OE_OT_render_look,
    OE_OT_generate_tx,
    OE_OT_copy_linking,
)


def register_props():
    bpy.types.Scene.oe_tx_cache = BoolProperty(
        name="Texture cache",
        description="Cycles 5.2 texture cache and auto-generate .tx files. Saves memory on CAST scenes.",
        default=True,
        update=_look_update,
    )
    bpy.types.Scene.oe_viewport_tex = FloatProperty(
        name="Viewport textures",
        description="Cycles viewport texture resolution while lookdev is on. Final render stays at 100%.",
        default=100.0,
        min=10.0,
        max=100.0,
        soft_min=25.0,
        soft_max=100.0,
        step=100,
        precision=0,
        subtype="PERCENTAGE",
        update=_look_update,
    )
    bpy.types.Scene.oe_eevee_rt = BoolProperty(
        name="EEVEE ray tracing",
        description="Screen trace, backface hits, Fast GI, overscan, and a larger shadow pool.",
        default=True,
        update=_look_update,
    )
    bpy.types.Scene.oe_thin_wall = BoolProperty(
        name="Thin Wall cards",
        description=(
            "Principled BSDF Thin Wall on local hair, cloth, and cape materials. "
            "Legacy skin Random Walk is upgraded. Shared Apex groups are not edited."
        ),
        default=True,
        update=_look_update,
    )
    bpy.types.Scene.oe_caustics = BoolProperty(
        name="Caustics",
        description="Reflective and refractive caustics while lookdev is on. Off is cleaner on armor.",
        default=False,
        update=_look_update,
    )


def unregister_props():
    for attr in _PROPS:
        if hasattr(bpy.types.Scene, attr):
            delattr(bpy.types.Scene, attr)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    register_props()


def unregister():
    unregister_props()
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
