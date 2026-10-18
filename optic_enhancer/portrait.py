from __future__ import annotations

"""Portrait Look — SSS on skin, translucency on hair cards, optional Cycles preset.

Does not sculpt, displace, or replace hair cards with curves.
"""

import bpy
from bpy.props import BoolProperty, FloatProperty

from .host import (
    is_eye_material,
    is_glass_family,
    is_transparent_family,
    material_meshes,
    resolve_armature,
    resolve_shade_objects,
    should_skip_lod,
)

P_PREFIX = "AAS.OE.P."
P_FLAG = "oe_portrait"
P_MIX = P_PREFIX + "HairMix"
P_TRANS = P_PREFIX + "Translucent"
P_GEO = P_PREFIX + "Geo"
P_LW = P_PREFIX + "LayerWeight"
P_ADD = P_PREFIX + "Add"
P_FAC = P_PREFIX + "Fac"
P_SSS_STORE = "oe_sss_prev"
P_BLEND_STORE = "oe_hair_blend"
P_SHADOW_STORE = "oe_hair_shadow"
P_CULL_STORE = "oe_hair_cull"
P_RENDER_FLAG = "oe_portrait_render"

SSS_DEFAULT = 55.0
HAIR_DEFAULT = 18.0

_SSS_STRENGTH = ("SSS Strength", "Subsurface Strength", "Scatter Strength")
_SSS_MAP = (
    "Subsurface",
    "SSS (Subsurface Scattering)",
    "Scatter",
    "Subsurface Color",
)
_SKIN_PARTS = ("head", "face", "skin")
_HAIR_PARTS = ("hair", "lash", "brow", "fur")
_SKIP_PARTS = ("eye", "glass", "ice", "crystal", "snow", "particle", "vfx")
_PORTRAIT_PROPS = ("oe_sss", "oe_hair", "oe_cycles")


def _is_mesh_subset(objects) -> bool:
    return bool(objects) and all(getattr(o, "type", "") == "MESH" for o in objects)


def portrait_is_on(context) -> bool:
    objs = _targets(context)
    mesh_subset = _is_mesh_subset(objs)
    for obj in objs:
        if not mesh_subset:
            arm = resolve_armature(obj) or obj
            if arm is not None and arm.get(P_FLAG):
                return True
        for mesh in material_meshes(obj):
            for mat in _mesh_materials(mesh):
                if _material_has_portrait(mat):
                    return True
    if mesh_subset:
        return False
    scene = getattr(context, "scene", None)
    if scene is not None and scene.get(P_RENDER_FLAG):
        return True
    return False


def _portrait_update(self, context):
    try:
        if portrait_is_on(context):
            apply_portrait(_targets(context), context.scene)
    except Exception:
        pass


def apply_portrait(objects, scene=None) -> int:
    scene = scene or getattr(bpy.context, "scene", None)
    cfg = _settings(scene)
    count = 0
    seen: set[int] = set()
    for obj in objects:
        for mesh in material_meshes(obj):
            if _skip_lod(mesh):
                continue
            for mat in _mesh_materials(mesh):
                if mat is None or id(mat) in seen:
                    continue
                seen.add(id(mat))
                if _apply_skin(mat, cfg["sss"]):
                    count += 1
                elif _apply_hair(mat, cfg["hair"]):
                    count += 1
    if scene is not None and getattr(scene, "oe_cycles", True):
        _apply_render(scene)
    _set_flags(objects, True)
    return count


def remove_portrait(objects) -> int:
    count = 0
    seen: set[int] = set()
    for obj in objects:
        for mesh in material_meshes(obj):
            for mat in _mesh_materials(mesh):
                if mat is None or id(mat) in seen:
                    continue
                seen.add(id(mat))
                if _remove_skin(mat) or _remove_hair(mat):
                    count += 1
    if not _is_mesh_subset(objects):
        scene = getattr(bpy.context, "scene", None)
        if scene is not None:
            _restore_render(scene)
    _set_flags(objects, False)
    return count


def _settings(scene) -> dict:
    return {
        "sss": _as_factor(getattr(scene, "oe_sss", SSS_DEFAULT) if scene else SSS_DEFAULT, 0.55),
        "hair": _as_factor(getattr(scene, "oe_hair", HAIR_DEFAULT) if scene else HAIR_DEFAULT, 0.18),
    }


def _as_factor(value, fallback: float) -> float:
    try:
        v = float(value)
    except (TypeError, ValueError):
        v = fallback
    if v > 1.0:
        v = v / 100.0
    return max(0.0, min(1.0, v))


def _targets(context) -> list:
    selected = list(getattr(context, "selected_objects", []) or [])
    meshes = [o for o in selected if o is not None and getattr(o, "type", "") == "MESH"]
    if not meshes:
        active = getattr(context, "active_object", None)
        if active is not None and getattr(active, "type", "") == "MESH":
            meshes = [active]
    if meshes:
        return meshes
    return [o for o in resolve_shade_objects(context) if o is not None and o.type in {"ARMATURE", "MESH"}]


def _set_flags(objects, on: bool) -> None:
    if _is_mesh_subset(objects):
        return
    for obj in objects:
        arm = resolve_armature(obj) or obj
        try:
            if on:
                arm[P_FLAG] = 1
            elif P_FLAG in arm:
                del arm[P_FLAG]
        except Exception:
            pass


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


def _skip_lod(mesh) -> bool:
    try:
        return bool(should_skip_lod(mesh))
    except Exception:
        return False


def _skip_common(name: str) -> bool:
    low = (name or "").lower()
    if is_eye_material(name) or is_glass_family(name) or is_transparent_family(name):
        return True
    return any(part in low for part in _SKIP_PARTS)


def _is_hair_name(name: str) -> bool:
    low = (name or "").lower()
    return any(part in low for part in _HAIR_PARTS)


def _is_skin_name(name: str) -> bool:
    low = (name or "").lower()
    return any(part in low for part in _SKIN_PARTS)


def _apex_group(tree):
    groups = []
    for node in tree.nodes:
        if getattr(node, "type", "") != "GROUP":
            continue
        ng = getattr(node, "node_tree", None)
        name = ((ng.name if ng is not None else "") or node.name or "").lower()
        if "apex" in name or "cores" in name:
            groups.append(node)
    if groups:
        return groups[0]
    for node in tree.nodes:
        if node.type == "OUTPUT_MATERIAL":
            try:
                sock = node.inputs.get("Surface") or node.inputs[0]
            except Exception:
                continue
            if sock is not None and sock.is_linked:
                src = sock.links[0].from_node
                if getattr(src, "type", "") == "GROUP":
                    return src
    return None


def _has_sss_map(group) -> bool:
    for name in _SSS_MAP:
        try:
            sock = group.inputs.get(name)
        except Exception:
            sock = None
        if sock is not None and getattr(sock, "is_linked", False):
            return True
    return False


def _sss_socket(group):
    for name in _SSS_STRENGTH:
        try:
            sock = group.inputs.get(name)
        except Exception:
            sock = None
        if sock is not None:
            return sock
    for sock in group.inputs:
        low = (sock.name or "").lower()
        if "sss" in low and "strength" in low:
            return sock
    return None


def _is_skin_material(mat, group) -> bool:
    name = getattr(mat, "name", "") or ""
    if _skip_common(name) or _is_hair_name(name):
        return False
    if _is_skin_name(name):
        return True
    return group is not None and _has_sss_map(group)


def _material_has_portrait(mat) -> bool:
    if mat is None:
        return False
    if mat.get(P_SSS_STORE) is not None or mat.get(P_BLEND_STORE) is not None:
        return True
    tree = getattr(mat, "node_tree", None)
    if tree is None:
        return False
    return any(n.name.startswith(P_PREFIX) for n in tree.nodes)


def _apply_skin(mat, strength: float) -> bool:
    tree = getattr(mat, "node_tree", None)
    if tree is None or not getattr(mat, "use_nodes", False):
        return False
    group = _apex_group(tree)
    if group is None or not _is_skin_material(mat, group):
        return False
    sock = _sss_socket(group)
    if sock is None:
        return False
    if mat.get(P_SSS_STORE) is None:
        try:
            mat[P_SSS_STORE] = float(sock.default_value)
        except Exception:
            mat[P_SSS_STORE] = 0.5
    try:
        sock.default_value = strength
    except Exception:
        return False
    return True


def _remove_skin(mat) -> bool:
    prev = mat.get(P_SSS_STORE) if mat is not None else None
    if prev is None:
        return False
    tree = getattr(mat, "node_tree", None)
    group = _apex_group(tree) if tree is not None else None
    sock = _sss_socket(group) if group is not None else None
    if sock is not None:
        try:
            sock.default_value = float(prev)
        except Exception:
            pass
    try:
        del mat[P_SSS_STORE]
    except Exception:
        pass
    return True


def _apply_hair(mat, amount: float) -> bool:
    tree = getattr(mat, "node_tree", None)
    if tree is None or not getattr(mat, "use_nodes", False):
        return False
    name = getattr(mat, "name", "") or ""
    if not _is_hair_name(name):
        return False
    if is_eye_material(name) or is_glass_family(name):
        return False
    group = _apex_group(tree)
    if group is None:
        return False
    nodes = tree.nodes
    if nodes.get(P_MIX) is None:
        if not _insert_hair_mix(tree, nodes, group, amount):
            return False
    else:
        fac = nodes.get(P_FAC)
        if fac is not None:
            try:
                fac.inputs[1].default_value = amount
            except Exception:
                pass
        else:
            mix = nodes.get(P_MIX)
            try:
                mix.inputs[0].default_value = amount
            except Exception:
                pass
    _set_hair_blend(mat)
    return True


def _hair_albedo_socket(group):
    for name in ("Albedo", "Albedo / Color", "Color", "Base Color", "Diffuse"):
        try:
            sock = group.inputs.get(name)
        except Exception:
            sock = None
        if sock is not None:
            return sock
    for sock in group.inputs:
        low = (sock.name or "").lower()
        if "albedo" in low or low in {"color", "base color", "diffuse"}:
            if "emit" in low or "emission" in low:
                continue
            return sock
    return None


def _insert_hair_mix(tree, nodes, group, amount: float) -> bool:
    output = None
    for node in nodes:
        if node.type == "OUTPUT_MATERIAL":
            output = node
            break
    if output is None:
        return False
    try:
        target = output.inputs.get("Surface") or output.inputs[0]
    except Exception:
        return False
    incoming = None
    if target.is_linked:
        incoming = target.links[0].from_socket
    else:
        try:
            incoming = group.outputs[0]
        except Exception:
            return False
    gx, gy = group.location
    trans = nodes.new("ShaderNodeBsdfTranslucent")
    trans.name = P_TRANS
    trans.label = "Hair wrap"
    trans.location = (gx + 260.0, gy - 80.0)
    albedo = _hair_albedo_socket(group)
    linked_color = False
    if albedo is not None and getattr(albedo, "is_linked", False):
        try:
            tree.links.new(albedo.links[0].from_socket, trans.inputs["Color"])
            linked_color = True
        except Exception:
            linked_color = False
    if not linked_color:
        try:
            trans.inputs["Color"].default_value = (0.42, 0.32, 0.24, 1.0)
        except Exception:
            pass

    geo = nodes.new("ShaderNodeNewGeometry")
    geo.name = P_GEO
    geo.label = "Hair geo"
    geo.location = (gx + 40.0, gy + 160.0)

    lw = nodes.new("ShaderNodeLayerWeight")
    lw.name = P_LW
    lw.label = "Hair facing"
    lw.location = (gx + 40.0, gy + 40.0)
    try:
        lw.inputs["Blend"].default_value = 0.5
    except Exception:
        pass

    add = nodes.new("ShaderNodeMath")
    add.name = P_ADD
    add.label = "Hair wrap add"
    add.location = (gx + 220.0, gy + 120.0)
    add.operation = "ADD"
    try:
        add.use_clamp = True
    except Exception:
        pass
    try:
        tree.links.new(geo.outputs["Backfacing"], add.inputs[0])
        tree.links.new(lw.outputs["Facing"], add.inputs[1])
    except Exception:
        pass

    mul = nodes.new("ShaderNodeMath")
    mul.name = P_FAC
    mul.label = "Hair wrap fac"
    mul.location = (gx + 380.0, gy + 120.0)
    mul.operation = "MULTIPLY"
    try:
        mul.use_clamp = True
    except Exception:
        pass
    try:
        mul.inputs[1].default_value = amount
        tree.links.new(add.outputs[0], mul.inputs[0])
    except Exception:
        pass

    mix = nodes.new("ShaderNodeMixShader")
    mix.name = P_MIX
    mix.label = "Hair mix"
    mix.location = (gx + 480.0, gy)
    try:
        tree.links.new(mul.outputs[0], mix.inputs[0])
        tree.links.new(incoming, mix.inputs[1])
        tree.links.new(trans.outputs[0], mix.inputs[2])
    except Exception:
        return False
    try:
        if target.is_linked:
            tree.links.remove(target.links[0])
    except Exception:
        pass
    tree.links.new(mix.outputs[0], target)
    return True


def _set_hair_blend(mat) -> None:
    if mat.get(P_BLEND_STORE) is None:
        try:
            if hasattr(mat, "surface_render_method"):
                mat[P_BLEND_STORE] = str(mat.surface_render_method)
            elif hasattr(mat, "blend_method"):
                mat[P_BLEND_STORE] = str(mat.blend_method)
        except Exception:
            mat[P_BLEND_STORE] = ""
    if mat.get(P_SHADOW_STORE) is None and hasattr(mat, "shadow_method"):
        try:
            mat[P_SHADOW_STORE] = str(mat.shadow_method)
        except Exception:
            pass
    if mat.get(P_CULL_STORE) is None:
        try:
            mat[P_CULL_STORE] = 1 if getattr(mat, "use_backface_culling", False) else 0
        except Exception:
            pass
    try:
        if hasattr(mat, "surface_render_method"):
            mat.surface_render_method = "DITHERED"
        if hasattr(mat, "blend_method"):
            mat.blend_method = "HASHED"
        if hasattr(mat, "shadow_method"):
            mat.shadow_method = "HASHED"
        mat.use_backface_culling = False
    except Exception:
        pass


def _remove_hair(mat) -> bool:
    tree = getattr(mat, "node_tree", None)
    changed = False
    if tree is not None:
        nodes = tree.nodes
        mix = nodes.get(P_MIX)
        if mix is not None:
            orig = None
            if len(mix.inputs) > 1 and mix.inputs[1].is_linked:
                orig = mix.inputs[1].links[0].from_socket
            dests = [ln.to_socket for ln in list(mix.outputs[0].links)] if mix.outputs else []
            for sock in dests:
                try:
                    if sock.is_linked:
                        tree.links.remove(sock.links[0])
                except Exception:
                    pass
                if orig is not None:
                    try:
                        tree.links.new(orig, sock)
                    except Exception:
                        pass
            for node in list(nodes):
                if node.name.startswith(P_PREFIX):
                    try:
                        nodes.remove(node)
                    except Exception:
                        pass
            changed = True
    blend = mat.get(P_BLEND_STORE) if mat is not None else None
    if blend is not None:
        try:
            if hasattr(mat, "surface_render_method") and blend:
                mat.surface_render_method = blend
            elif hasattr(mat, "blend_method") and blend:
                mat.blend_method = blend
        except Exception:
            pass
        try:
            del mat[P_BLEND_STORE]
        except Exception:
            pass
        changed = True
    shadow = mat.get(P_SHADOW_STORE) if mat is not None else None
    if shadow is not None:
        try:
            if hasattr(mat, "shadow_method"):
                mat.shadow_method = shadow
            del mat[P_SHADOW_STORE]
        except Exception:
            pass
    cull = mat.get(P_CULL_STORE) if mat is not None else None
    if cull is not None:
        try:
            mat.use_backface_culling = bool(int(cull))
            del mat[P_CULL_STORE]
        except Exception:
            pass
    return changed


def _apply_render(scene) -> None:
    if scene.get(P_RENDER_FLAG):
        return
    stored = {}
    vs = getattr(scene, "view_settings", None)
    if vs is not None and hasattr(vs, "view_transform"):
        stored["view_transform"] = str(vs.view_transform)
        try:
            items = {item.identifier for item in vs.bl_rna.properties["view_transform"].enum_items}
            if "AgX" in items:
                vs.view_transform = "AgX"
            elif "Filmic" in items:
                vs.view_transform = "Filmic"
        except Exception:
            pass
    rnd = scene.render
    if hasattr(rnd, "use_high_quality_normals"):
        stored["hqn"] = bool(rnd.use_high_quality_normals)
        try:
            rnd.use_high_quality_normals = True
        except Exception:
            pass
    cycles = getattr(scene, "cycles", None)
    if cycles is not None:
        if hasattr(cycles, "use_denoising"):
            stored["denoising"] = bool(cycles.use_denoising)
            try:
                cycles.use_denoising = True
            except Exception:
                pass
        if hasattr(cycles, "denoiser"):
            stored["denoiser"] = str(cycles.denoiser)
            try:
                cycles.denoiser = "OPENIMAGEDENOISE"
            except Exception:
                pass
    for key, value in stored.items():
        try:
            scene["oe_r_" + key] = value
        except Exception:
            pass
    try:
        scene[P_RENDER_FLAG] = 1
    except Exception:
        pass


def _restore_render(scene) -> None:
    if not scene.get(P_RENDER_FLAG):
        return
    vs = getattr(scene, "view_settings", None)
    prev = scene.get("oe_r_view_transform")
    if vs is not None and prev:
        try:
            vs.view_transform = str(prev)
        except Exception:
            pass
    rnd = scene.render
    prev = scene.get("oe_r_hqn")
    if prev is not None and hasattr(rnd, "use_high_quality_normals"):
        try:
            rnd.use_high_quality_normals = bool(prev)
        except Exception:
            pass
    cycles = getattr(scene, "cycles", None)
    if cycles is not None:
        prev = scene.get("oe_r_denoising")
        if prev is not None and hasattr(cycles, "use_denoising"):
            try:
                cycles.use_denoising = bool(prev)
            except Exception:
                pass
        prev = scene.get("oe_r_denoiser")
        if prev:
            try:
                cycles.denoiser = str(prev)
            except Exception:
                pass
    for key in ("oe_r_view_transform", "oe_r_hqn", "oe_r_denoising", "oe_r_denoiser"):
        if key in scene:
            try:
                del scene[key]
            except Exception:
                pass
    try:
        del scene[P_RENDER_FLAG]
    except Exception:
        pass


def register_props():
    bpy.types.Scene.oe_sss = FloatProperty(
        name="Skin SSS",
        description="Subsurface amount on head/skin. Uses the Apex shader SSS strength.",
        default=SSS_DEFAULT,
        min=0.0,
        max=100.0,
        soft_min=20.0,
        soft_max=80.0,
        step=100,
        precision=0,
        subtype="PERCENTAGE",
        update=_portrait_update,
    )
    bpy.types.Scene.oe_hair = FloatProperty(
        name="Hair wrap",
        description="Translucency mixed into hair cards. Light passes through strands.",
        default=HAIR_DEFAULT,
        min=0.0,
        max=60.0,
        soft_min=8.0,
        soft_max=30.0,
        step=100,
        precision=0,
        subtype="PERCENTAGE",
        update=_portrait_update,
    )
    bpy.types.Scene.oe_cycles = BoolProperty(
        name="Cycles portrait",
        description="AgX, high-quality normals, denoising. Restored on remove.",
        default=True,
        update=_portrait_update,
    )


def unregister_props():
    for attr in _PORTRAIT_PROPS:
        if hasattr(bpy.types.Scene, attr):
            delattr(bpy.types.Scene, attr)
