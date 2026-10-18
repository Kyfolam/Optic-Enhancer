from __future__ import annotations

"""Optic Enhance — reversible look pass for Apex CAST models.

Default: multiply albedo in tight creases. Baked normals and the Apex BSDF
stay intact. Optional bevel mix (off) and cavity multiply. Does not edit
mesh datablocks, UVs, vertex groups, armatures, animation, or texture images.
"""

import re

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

HP_PREFIX = "AAS.HP."
HP_FLAG = "apex_highpoly"
HP_BEVEL = HP_PREFIX + "Bevel"
HP_MIX_N = HP_PREFIX + "MixNormal"
HP_AO = HP_PREFIX + "AO"
HP_GATE = HP_PREFIX + "Gate"
HP_INV = HP_PREFIX + "Inv"
HP_MUL = HP_PREFIX + "Mul"
HP_COL = HP_PREFIX + "AlbedoMul"
HP_CAV = HP_PREFIX + "CavityMul"
HP_DARK = HP_PREFIX + "Dark"
HP_MIX_S = HP_PREFIX + "AOMix"
HP_BUMP = HP_PREFIX + "Bump"
HP_DISP = HP_PREFIX + "Disp"
HP_DISP_MODE = "apex_optic_disp_method"
MOD_SUBSURF = "AAS.Optics.Subsurf"

BEVEL_RADIUS = 0.0035
AO_DISTANCE = 0.035
AO_STRENGTH = 12.0
NORMAL_MIX = 0.0
DISP_SCALE = 0.0035
CAVITY_FAC = 0.4
AO_GATE = 0.22

_NORMAL_NAMES = ("Normal Map", "Normal", "NormalMap", "nrm")
_ALBEDO_NAMES = ("Albedo", "Albedo / Color", "Color", "Base Color", "Diffuse")
_SKIP_PARTS = (
    "hair",
    "eye",
    "glass",
    "fur",
    "ice",
    "crystal",
    "snow",
    "lash",
    "brow",
    "particle",
    "vfx",
)
_OPTIC_PROPS = (
    "oe_bevel",
    "oe_mix",
    "oe_ao",
    "oe_ao_dist",
    "oe_subdiv",
    "oe_displace",
    "oe_auto",
)


def _is_mesh_subset(objects) -> bool:
    return bool(objects) and all(getattr(o, "type", "") == "MESH" for o in objects)


def optics_is_on(context) -> bool:
    objs = _targets(context)
    mesh_subset = _is_mesh_subset(objs)
    for obj in objs:
        for mesh in material_meshes(obj):
            if _mesh_has_hp(mesh) or _mesh_has_subsurf(mesh):
                return True
            if mesh_subset:
                continue
            arm = resolve_armature(mesh)
            if arm is not None and arm.get(HP_FLAG):
                return True
    return False


highpoly_is_on = optics_is_on


def _optic_update(self, context):
    try:
        sync_optic_settings(context)
    except Exception:
        pass


def apply_optics(objects, scene=None) -> int:
    from . import glow, wear

    scene = scene or getattr(bpy.context, "scene", None)
    count = 0
    seen: set[int] = set()
    for obj in objects:
        for mesh in material_meshes(obj):
            for mat in _mesh_materials(mesh):
                if mat is None or id(mat) in seen:
                    continue
                seen.add(id(mat))
                hit = False
                if not _skip_mesh(mesh) and not _skip_material(mat):
                    if _apply_material(mat, scene):
                        hit = True
                    if wear.apply_to_material(mat, scene):
                        hit = True
                if glow.apply_to_material(mat, mesh, scene):
                    hit = True
                if hit:
                    count += 1
    if scene is not None and getattr(scene, "oe_subdiv", False):
        _apply_subsurf(objects)
    return count


def remove_optics(objects) -> int:
    from . import glow, wear

    count = 0
    seen: set[int] = set()
    for obj in objects:
        for mesh in material_meshes(obj):
            _remove_subsurf(mesh)
            for mat in _mesh_materials(mesh):
                if mat is None or id(mat) in seen:
                    continue
                seen.add(id(mat))
                w = wear.remove_from_material(mat)
                g = glow.remove_from_material(mat)
                if w or g or _remove_material(mat):
                    count += 1
    return count


apply_highpoly = apply_optics
remove_highpoly = remove_optics


def sync_optic_settings(context) -> None:
    scene = context.scene
    cfg = _settings(scene)
    bevel = cfg["bevel"]
    mix_f = cfg["mix"]
    ao_s = cfg["ao"]
    ao_d = cfg["ao_dist"]
    for mat in bpy.data.materials:
        tree = getattr(mat, "node_tree", None)
        if tree is None:
            continue
        nodes = tree.nodes
        n_bevel = nodes.get(HP_BEVEL)
        if n_bevel is not None:
            try:
                n_bevel.inputs["Radius"].default_value = bevel
            except Exception:
                pass
        n_mix = nodes.get(HP_MIX_N)
        if n_mix is not None:
            fac = _enabled_input(n_mix, "Factor")
            if fac is not None:
                try:
                    fac.default_value = mix_f
                except Exception:
                    pass
        n_mul = nodes.get(HP_MUL)
        if n_mul is not None:
            try:
                n_mul.inputs[1].default_value = ao_s
            except Exception:
                pass
        n_ao = nodes.get(HP_AO)
        if n_ao is not None:
            try:
                n_ao.inputs["Distance"].default_value = ao_d
            except Exception:
                pass
        n_cav = nodes.get(HP_CAV)
        if n_cav is not None:
            fac = _enabled_input(n_cav, "Factor")
            if fac is not None:
                try:
                    fac.default_value = CAVITY_FAC
                except Exception:
                    pass
        group = _apex_group(tree)
        if group is not None:
            if mix_f > 0.001:
                _insert_normal_mix(tree, nodes, group, cfg)
            else:
                _remove_bevel_chain(tree, nodes)
    if not optics_is_on(context):
        return
    objs = _targets(context)
    if getattr(scene, "oe_subdiv", False):
        _apply_subsurf(objs)
    else:
        for obj in objs:
            for mesh in material_meshes(obj):
                _remove_subsurf(mesh)
    if getattr(scene, "oe_displace", False):
        _apply_cavity_all(objs, scene)
    else:
        _remove_cavity_all(objs)
    try:
        from . import glow, wear

        wear.sync_wear(context)
        glow.sync_glow(context)
    except Exception:
        pass


def _targets(context) -> list:
    selected = list(getattr(context, "selected_objects", []) or [])
    meshes = [o for o in selected if o is not None and getattr(o, "type", "") == "MESH"]
    if not meshes:
        active = getattr(context, "active_object", None)
        if active is not None and getattr(active, "type", "") == "MESH":
            meshes = [active]
    if meshes:
        return meshes
    objs = resolve_shade_objects(context)
    return [o for o in objs if o is not None and o.type in {"ARMATURE", "MESH"}]


def _set_flags(objects, on: bool) -> None:
    if _is_mesh_subset(objects):
        return
    for obj in objects:
        arm = resolve_armature(obj) or obj
        try:
            if on:
                arm[HP_FLAG] = 1
            elif HP_FLAG in arm:
                del arm[HP_FLAG]
        except Exception:
            pass


def _mesh_has_hp(mesh) -> bool:
    for mat in _mesh_materials(mesh):
        if _material_has_hp(mat):
            return True
    return False


def _mesh_has_subsurf(mesh) -> bool:
    try:
        return MOD_SUBSURF in mesh.modifiers
    except Exception:
        return False


def _material_has_hp(mat) -> bool:
    tree = getattr(mat, "node_tree", None)
    if tree is None:
        return False
    return any(
        n.name.startswith(HP_PREFIX)
        or n.name.startswith("AAS.OE.Wear.")
        or n.name.startswith("AAS.OE.Ilm.")
        for n in tree.nodes
    )


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


def _skip_name(name: str) -> bool:
    low = (name or "").lower()
    return any(part in low for part in _SKIP_PARTS)


def _skip_mesh(mesh) -> bool:
    name = getattr(mesh, "name", "") or ""
    if _skip_name(name):
        return True
    if is_eye_material(name) or is_glass_family(name):
        return True
    try:
        if should_skip_lod(mesh):
            return True
    except Exception:
        pass
    return False


def _skip_material(mat) -> bool:
    if mat is None:
        return True
    name = getattr(mat, "name", "") or ""
    if is_eye_material(name) or is_glass_family(name) or is_transparent_family(name):
        return True
    if _skip_name(name):
        return True
    return False


def _as_factor(value, fallback: float) -> float:
    try:
        v = float(value)
    except (TypeError, ValueError):
        v = fallback
    if v > 1.0:
        v = v / 100.0
    return max(0.0, min(1.0, v))


def _settings(scene) -> dict:
    mix_default = NORMAL_MIX / 100.0
    ao_default = AO_STRENGTH / 100.0
    return {
        "bevel": float(getattr(scene, "oe_bevel", BEVEL_RADIUS) if scene else BEVEL_RADIUS),
        "mix": _as_factor(getattr(scene, "oe_mix", NORMAL_MIX) if scene else NORMAL_MIX, mix_default),
        "ao": _as_factor(getattr(scene, "oe_ao", AO_STRENGTH) if scene else AO_STRENGTH, ao_default),
        "ao_dist": float(getattr(scene, "oe_ao_dist", AO_DISTANCE) if scene else AO_DISTANCE),
        "displace": bool(getattr(scene, "oe_displace", False) if scene else False),
    }


def _apply_material(mat, scene) -> bool:
    tree = getattr(mat, "node_tree", None)
    if tree is None or not getattr(mat, "use_nodes", False):
        return False
    group = _apex_group(tree)
    if group is None:
        return False
    nodes = tree.nodes
    cfg = _settings(scene)
    changed = False
    if cfg["mix"] > 0.001 and _insert_normal_mix(tree, nodes, group, cfg):
        changed = True
    if _insert_ao_mix(tree, nodes, group, cfg):
        changed = True
    if cfg["displace"] and _insert_cavity_relief(mat, tree, nodes, cfg):
        changed = True
    return changed


def _remove_material(mat) -> bool:
    tree = getattr(mat, "node_tree", None)
    if tree is None:
        return False
    nodes = tree.nodes
    hp = [n for n in nodes if n.name.startswith(HP_PREFIX)]
    if not hp:
        return False
    mix_n = nodes.get(HP_MIX_N)
    if mix_n is not None:
        _restore_mix_vector(tree, mix_n)
    mix_s = nodes.get(HP_MIX_S)
    if mix_s is not None:
        _restore_mix_shader(tree, mix_s)
    _restore_albedo(tree, nodes)
    bevel = nodes.get(HP_BEVEL)
    if bevel is not None:
        _disconnect_outputs(tree, bevel)
    _restore_displacement(mat, tree)
    for node in list(hp):
        try:
            nodes.remove(node)
        except Exception:
            pass
    return True


def _apply_cavity_all(objects, scene) -> None:
    seen: set[int] = set()
    cfg = _settings(scene)
    for obj in objects:
        for mesh in material_meshes(obj):
            if _skip_mesh(mesh):
                continue
            for mat in _mesh_materials(mesh):
                if mat is None or id(mat) in seen:
                    continue
                seen.add(id(mat))
                if _skip_material(mat) or _is_skin_or_head_material(mat):
                    _remove_cavity(mat)
                    continue
                tree = getattr(mat, "node_tree", None)
                if tree is None:
                    continue
                _insert_cavity_relief(mat, tree, tree.nodes, cfg)


def _remove_cavity_all(objects) -> None:
    seen: set[int] = set()
    for obj in objects:
        for mesh in material_meshes(obj):
            for mat in _mesh_materials(mesh):
                if mat is None or id(mat) in seen:
                    continue
                seen.add(id(mat))
                _remove_cavity(mat)


def _remove_cavity(mat) -> None:
    tree = getattr(mat, "node_tree", None)
    if tree is None:
        return
    nodes = tree.nodes
    cav = nodes.get(HP_CAV)
    if cav is not None:
        orig = None
        a = _color_a(cav)
        if a is not None and a.is_linked:
            orig = a.links[0].from_socket
        out = _color_out(cav)
        dests = [ln.to_socket for ln in list(out.links)] if out is not None else []
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
        try:
            nodes.remove(cav)
        except Exception:
            pass
    _restore_displacement(mat, tree)
    for name in (HP_DISP, HP_BUMP):
        node = nodes.get(name)
        if node is None:
            continue
        _disconnect_outputs(tree, node)
        try:
            nodes.remove(node)
        except Exception:
            pass


_SKIN_TOKENS = {"head", "face", "skin", "faceskin"}


def _name_tokens(name: str) -> set[str]:
    return {part for part in re.split(r"[^a-z0-9]+", (name or "").lower()) if part}


def _is_skin_or_head_material(mat) -> bool:
    """Head and skin materials must keep their albedo. Cavity would darken them."""
    if mat is None:
        return False
    if _name_tokens(getattr(mat, "name", "") or "") & _SKIN_TOKENS:
        return True
    try:
        objects = list(bpy.data.objects)
    except Exception:
        objects = []
    for obj in objects:
        if getattr(obj, "type", "") != "MESH":
            continue
        data = getattr(obj, "data", None)
        slots = getattr(data, "materials", None) if data is not None else None
        if not slots:
            continue
        try:
            used = mat in list(slots)
        except Exception:
            used = False
        if not used:
            continue
        if _name_tokens(getattr(obj, "name", "") or "") & _SKIN_TOKENS:
            return True
    return False


def _apply_subsurf(objects) -> int:
    scene = getattr(bpy.context, "scene", None)
    # Off by default. The checkbox is the only switch; never add a modifier while it is off.
    if scene is None or not bool(getattr(scene, "oe_subdiv", False)):
        return 0
    n = 0
    for obj in objects:
        for mesh in material_meshes(obj):
            if _skip_mesh(mesh):
                continue
            if mesh.type != "MESH":
                continue
            if MOD_SUBSURF in mesh.modifiers:
                continue
            try:
                mod = mesh.modifiers.new(MOD_SUBSURF, "SUBSURF")
            except Exception:
                continue
            try:
                mod.levels = 1
                mod.render_levels = 1
            except Exception:
                pass
            for attr, value in (
                ("uv_smooth", "PRESERVE_CORNERS"),
                ("boundary_smooth", "PRESERVE_CORNERS"),
                ("quality", 3),
                ("show_only_control_edges", True),
            ):
                if hasattr(mod, attr):
                    try:
                        setattr(mod, attr, value)
                    except Exception:
                        pass
            _place_after_armature(mesh, MOD_SUBSURF)
            n += 1
    return n


def _remove_subsurf(mesh) -> None:
    try:
        mod = mesh.modifiers.get(MOD_SUBSURF)
    except Exception:
        return
    if mod is None:
        return
    try:
        mesh.modifiers.remove(mod)
    except Exception:
        pass


def _place_after_armature(obj, name: str) -> None:
    mods = obj.modifiers
    if name not in mods:
        return
    arm = next((i for i, m in enumerate(mods) if m.type == "ARMATURE"), None)
    if arm is None:
        return
    cur = next((i for i, m in enumerate(mods) if m.name == name), None)
    if cur is None:
        return
    target = min(arm + 1, len(mods) - 1)
    if cur == target:
        return
    try:
        mods.move(cur, target)
    except Exception:
        pass


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
    output = _material_output(tree)
    if output is None:
        return None
    sock = _surface_input(output)
    if sock is None or not sock.is_linked:
        return None
    src = sock.links[0].from_node
    if getattr(src, "type", "") == "GROUP":
        return src
    if getattr(src, "type", "") == "MIX_SHADER":
        for idx in (2, 1):
            inp = src.inputs[idx] if idx < len(src.inputs) else None
            if inp is not None and inp.is_linked:
                cand = inp.links[0].from_node
                if getattr(cand, "type", "") == "GROUP":
                    return cand
    return None


def _material_output(tree):
    for node in tree.nodes:
        if node.type == "OUTPUT_MATERIAL":
            return node
    return None


def _surface_input(output):
    try:
        return output.inputs.get("Surface") or output.inputs[0]
    except Exception:
        return None


def _normal_input(group):
    for name in _NORMAL_NAMES:
        try:
            sock = group.inputs.get(name)
        except Exception:
            sock = None
        if sock is not None:
            return sock
    for sock in group.inputs:
        if "normal" in (sock.name or "").lower():
            return sock
    return None


def _insert_normal_mix(tree, nodes, group, cfg) -> bool:
    if float(cfg.get("mix", 0.0)) <= 0.001:
        return False
    nrm = _normal_input(group)
    if nrm is None:
        return False
    if any(n.name == HP_MIX_N or n.name == HP_BEVEL for n in nodes):
        return False
    gx, gy = group.location
    bevel = nodes.new("ShaderNodeBevel")
    bevel.name = HP_BEVEL
    bevel.label = "Optic Bevel"
    bevel.location = (gx - 420.0, gy + 80.0)
    try:
        bevel.samples = 4
    except Exception:
        pass
    try:
        bevel.inputs["Radius"].default_value = cfg["bevel"]
    except Exception:
        pass

    orig_from = None
    if nrm.is_linked:
        try:
            orig_from = nrm.links[0].from_socket
        except Exception:
            orig_from = None

    if orig_from is None:
        try:
            tree.links.new(bevel.outputs["Normal"], nrm)
        except Exception:
            tree.links.new(bevel.outputs[0], nrm)
        return True

    mix = nodes.new("ShaderNodeMix")
    mix.name = HP_MIX_N
    mix.label = "Optic Normal"
    mix.location = (gx - 220.0, gy + 40.0)
    try:
        mix.data_type = "VECTOR"
    except Exception:
        pass
    try:
        mix.clamp_factor = True
    except Exception:
        pass
    fac = _enabled_input(mix, "Factor")
    if fac is not None:
        try:
            fac.default_value = cfg["mix"]
        except Exception:
            pass
    a = _enabled_input(mix, "A", "VECTOR")
    b = _enabled_input(mix, "B", "VECTOR")
    out = _enabled_output(mix, "Result", "VECTOR") or _enabled_output(mix, "Vector")
    if out is None and mix.outputs:
        out = mix.outputs[-1]
    if out is None:
        return False
    try:
        tree.links.remove(nrm.links[0])
    except Exception:
        pass
    if a is not None:
        tree.links.new(orig_from, a)
    if b is not None:
        try:
            tree.links.new(bevel.outputs["Normal"], b)
        except Exception:
            tree.links.new(bevel.outputs[0], b)
    tree.links.new(out, nrm)
    return True


def _albedo_input(group):
    for name in _ALBEDO_NAMES:
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


def _color_a(node):
    return (
        _enabled_input(node, "A", "RGBA")
        or _enabled_input(node, "A")
        or (node.inputs[6] if len(node.inputs) > 6 else None)
    )


def _color_b(node):
    return (
        _enabled_input(node, "B", "RGBA")
        or _enabled_input(node, "B")
        or (node.inputs[7] if len(node.inputs) > 7 else None)
    )


def _color_out(node):
    return (
        _enabled_output(node, "Result", "RGBA")
        or _enabled_output(node, "Result")
        or _enabled_output(node, "Color")
        or (node.outputs[-1] if node.outputs else None)
    )


def _new_color_multiply(nodes, name: str, label: str, location, factor: float):
    mix = nodes.new("ShaderNodeMix")
    mix.name = name
    mix.label = label
    mix.location = location
    try:
        mix.data_type = "RGBA"
    except Exception:
        pass
    try:
        mix.blend_type = "MULTIPLY"
    except Exception:
        pass
    try:
        mix.clamp_factor = True
    except Exception:
        pass
    fac = _enabled_input(mix, "Factor")
    if fac is not None:
        try:
            fac.default_value = factor
        except Exception:
            pass
    return mix


def _insert_ao_mix(tree, nodes, group, cfg) -> bool:
    if nodes.get(HP_COL) is not None:
        return False
    albedo = _albedo_input(group)
    if albedo is None:
        return False
    gx, gy = group.location
    ao = nodes.new("ShaderNodeAmbientOcclusion")
    ao.name = HP_AO
    ao.label = "Optic AO"
    ao.location = (gx - 720.0, gy - 80.0)
    try:
        ao.samples = 8
        ao.inside = False
        ao.only_local = False
    except Exception:
        pass
    try:
        ao.inputs["Distance"].default_value = cfg["ao_dist"]
    except Exception:
        pass

    gate = nodes.new("ShaderNodeMapRange")
    gate.name = HP_GATE
    gate.label = "Crease gate"
    gate.location = (gx - 520.0, gy - 80.0)
    try:
        gate.clamp = True
        gate.inputs["From Min"].default_value = 0.0
        gate.inputs["From Max"].default_value = AO_GATE
        gate.inputs["To Min"].default_value = 1.0
        gate.inputs["To Max"].default_value = 0.0
    except Exception:
        pass
    try:
        tree.links.new(ao.outputs["Color"], gate.inputs["Value"])
    except Exception:
        tree.links.new(ao.outputs[0], gate.inputs[0])

    mul = nodes.new("ShaderNodeMath")
    mul.name = HP_MUL
    mul.label = "AO Strength"
    mul.location = (gx - 340.0, gy - 80.0)
    mul.operation = "MULTIPLY"
    try:
        mul.inputs[1].default_value = cfg["ao"]
        tree.links.new(gate.outputs[0], mul.inputs[0])
    except Exception:
        pass

    inv = nodes.new("ShaderNodeMath")
    inv.name = HP_INV
    inv.label = "Albedo factor"
    inv.location = (gx - 180.0, gy - 80.0)
    inv.operation = "SUBTRACT"
    try:
        inv.inputs[0].default_value = 1.0
        tree.links.new(mul.outputs[0], inv.inputs[1])
    except Exception:
        pass

    mix = _new_color_multiply(nodes, HP_COL, "Optic Albedo", (gx - 220.0, gy + 160.0), 1.0)
    a = _color_a(mix)
    b = _color_b(mix)
    out = _color_out(mix)
    if out is None:
        return False

    orig_from = None
    if albedo.is_linked:
        try:
            orig_from = albedo.links[0].from_socket
        except Exception:
            orig_from = None
        try:
            tree.links.remove(albedo.links[0])
        except Exception:
            pass
    elif a is not None:
        try:
            a.default_value = tuple(albedo.default_value)
        except Exception:
            pass

    if orig_from is not None and a is not None:
        tree.links.new(orig_from, a)
    if b is not None:
        try:
            tree.links.new(inv.outputs[0], b)
        except Exception:
            pass
    tree.links.new(out, albedo)
    return True


def _find_cavity_tex(nodes):
    for node in nodes:
        if getattr(node, "type", "") != "TEX_IMAGE":
            continue
        image = getattr(node, "image", None)
        bits = [
            getattr(node, "name", ""),
            getattr(node, "label", ""),
            getattr(image, "name", "") if image is not None else "",
            getattr(image, "filepath", "") if image is not None else "",
        ]
        blob = " ".join(str(b) for b in bits).lower()
        if "cavity" in blob:
            return node
    return None


def _insert_cavity_relief(mat, tree, nodes, cfg) -> bool:
    if _is_skin_or_head_material(mat):
        return False
    if nodes.get(HP_CAV) is not None:
        return False
    cav = _find_cavity_tex(nodes)
    if cav is None:
        return False
    group = _apex_group(tree)
    if group is None:
        return False
    gx, gy = group.location
    mix = _new_color_multiply(
        nodes, HP_CAV, "Optic Cavity", (gx - 400.0, gy + 160.0), CAVITY_FAC
    )
    a = _color_a(mix)
    b = _color_b(mix)
    out = _color_out(mix)
    if out is None or a is None or b is None:
        return False
    try:
        tree.links.new(cav.outputs["Color"], b)
    except Exception:
        return False

    col = nodes.get(HP_COL)
    dest = _color_a(col) if col is not None else _albedo_input(group)
    if dest is None:
        return False
    orig_from = None
    if dest.is_linked:
        try:
            orig_from = dest.links[0].from_socket
        except Exception:
            orig_from = None
        try:
            tree.links.remove(dest.links[0])
        except Exception:
            pass
    if orig_from is not None:
        tree.links.new(orig_from, a)
    tree.links.new(out, dest)
    return True


def _restore_albedo(tree, nodes) -> None:
    col = nodes.get(HP_COL)
    cav = nodes.get(HP_CAV)
    first = cav if cav is not None else col
    last = col if col is not None else cav
    if first is None or last is None:
        return
    orig = None
    a = _color_a(first)
    if a is not None and a.is_linked:
        orig = a.links[0].from_socket
    out = _color_out(last)
    dests = [ln.to_socket for ln in list(out.links)] if out is not None else []
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


def _remove_bevel_chain(tree, nodes) -> None:
    mix_n = nodes.get(HP_MIX_N)
    if mix_n is not None:
        _restore_mix_vector(tree, mix_n)
    bevel = nodes.get(HP_BEVEL)
    if bevel is not None:
        _disconnect_outputs(tree, bevel)
    for name in (HP_MIX_N, HP_BEVEL):
        node = nodes.get(name)
        if node is None:
            continue
        try:
            nodes.remove(node)
        except Exception:
            pass


def _restore_displacement(mat, tree) -> None:
    output = _material_output(tree)
    disp = tree.nodes.get(HP_DISP)
    if output is not None and disp is not None:
        try:
            sock = output.inputs.get("Displacement")
            if sock is not None and sock.is_linked:
                src = sock.links[0].from_node
                if src == disp:
                    tree.links.remove(sock.links[0])
        except Exception:
            pass
    stored = mat.get(HP_DISP_MODE, "") if mat is not None else ""
    if stored:
        for holder, attr in ((mat, "displacement_method"), (getattr(mat, "cycles", None), "displacement_method")):
            if holder is None or not hasattr(holder, attr):
                continue
            try:
                setattr(holder, attr, stored)
                break
            except Exception:
                continue
        try:
            del mat[HP_DISP_MODE]
        except Exception:
            pass


def _shader_insert_socket(tree, group):
    try:
        shader_out = group.outputs[0]
    except Exception:
        return None
    links = list(getattr(shader_out, "links", []) or [])
    for ln in links:
        to_node = ln.to_node
        to_sock = ln.to_socket
        if to_node is None:
            continue
        if to_node.type == "OUTPUT_MATERIAL" and to_sock == _surface_input(to_node):
            return to_sock
        if to_node.type == "MIX_SHADER":
            return to_sock
        if to_node.name.startswith(HP_PREFIX):
            return None
    output = _material_output(tree)
    if output is None:
        return None
    return _surface_input(output)


def _restore_mix_vector(tree, mix) -> None:
    orig = None
    a = _enabled_input(mix, "A", "VECTOR")
    if a is not None and a.is_linked:
        orig = a.links[0].from_socket
    dests = []
    out = _enabled_output(mix, "Result", "VECTOR") or _enabled_output(mix, "Vector")
    if out is None and mix.outputs:
        out = mix.outputs[-1]
    if out is not None:
        dests = [ln.to_socket for ln in list(out.links)]
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


def _restore_mix_shader(tree, mix) -> None:
    orig = None
    if len(mix.inputs) > 1 and mix.inputs[1].is_linked:
        orig = mix.inputs[1].links[0].from_socket
    dests = []
    if mix.outputs:
        dests = [ln.to_socket for ln in list(mix.outputs[0].links)]
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


def _disconnect_outputs(tree, node) -> None:
    for out in node.outputs:
        for ln in list(out.links):
            try:
                tree.links.remove(ln)
            except Exception:
                pass


def _enabled_input(node, name: str, sock_type: str | None = None):
    for sock in node.inputs:
        if sock.name != name:
            continue
        if getattr(sock, "enabled", True) is False:
            continue
        if getattr(sock, "hide", False):
            continue
        if sock_type and getattr(sock, "type", "") != sock_type:
            continue
        return sock
    try:
        return node.inputs.get(name)
    except Exception:
        return None


def _enabled_output(node, name: str, sock_type: str | None = None):
    for sock in node.outputs:
        if sock.name != name:
            continue
        if getattr(sock, "enabled", True) is False:
            continue
        if getattr(sock, "hide", False):
            continue
        if sock_type and getattr(sock, "type", "") != sock_type:
            continue
        return sock
    try:
        return node.outputs.get(name)
    except Exception:
        return None


def register_props():
    bpy.types.Scene.oe_bevel = FloatProperty(
        name="Corner width",
        description="How wide each plate corner is rounded. Mix must be above 0%.",
        default=BEVEL_RADIUS,
        min=0.0002,
        max=0.02,
        soft_min=0.001,
        soft_max=0.008,
        step=0.01,
        precision=4,
        subtype="DISTANCE",
        unit="LENGTH",
        update=_optic_update,
    )
    bpy.types.Scene.oe_mix = FloatProperty(
        name="Rounding mix",
        description="How much rounding replaces the baked normal. Leave at 0%.",
        default=NORMAL_MIX,
        min=0.0,
        max=100.0,
        soft_min=0.0,
        soft_max=20.0,
        step=100,
        precision=0,
        subtype="PERCENTAGE",
        update=_optic_update,
    )
    bpy.types.Scene.oe_ao = FloatProperty(
        name="Crease shadow",
        description="How much the darkest contact gaps darken the albedo.",
        default=AO_STRENGTH,
        min=0.0,
        max=100.0,
        soft_min=5.0,
        soft_max=20.0,
        step=100,
        precision=0,
        subtype="PERCENTAGE",
        update=_optic_update,
    )
    bpy.types.Scene.oe_ao_dist = FloatProperty(
        name="Shadow reach",
        description="How far contact AO looks for a gap.",
        default=AO_DISTANCE,
        min=0.005,
        max=0.25,
        soft_min=0.02,
        soft_max=0.1,
        step=0.1,
        precision=3,
        subtype="DISTANCE",
        unit="LENGTH",
        update=_optic_update,
    )
    bpy.types.Scene.oe_subdiv = BoolProperty(
        name="Round silhouette",
        description="Off by default. Adds a Subdivision Surface only while this is on.",
        default=False,
        update=_optic_update,
    )
    bpy.types.Scene.oe_displace = BoolProperty(
        name="Cavity depth",
        description="Multiply albedo with the existing cavity map. Head and skin materials are skipped.",
        default=False,
        update=_optic_update,
    )
    bpy.types.Scene.oe_auto = BoolProperty(
        name="Apply after shade",
        description="Run optic passes automatically after Apex Auto Shader shades.",
        default=True,
    )


def unregister_props():
    for attr in _OPTIC_PROPS:
        if hasattr(bpy.types.Scene, attr):
            delattr(bpy.types.Scene, attr)
