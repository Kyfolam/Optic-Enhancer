from __future__ import annotations

"""Reversible edge wear / dirt overlay. Prefix AAS.OE.Wear."""

import bpy
from bpy.props import FloatProperty

from .host import is_eye_material, is_glass_family, is_transparent_family

WEAR_PREFIX = "AAS.OE.Wear."
WEAR_GEO = WEAR_PREFIX + "Geo"
WEAR_MAP = WEAR_PREFIX + "Map"
WEAR_FAC = WEAR_PREFIX + "Fac"
WEAR_MIX = WEAR_PREFIX + "Mix"
HP_COL = "AAS.HP.AlbedoMul"
DIRT = (0.14, 0.10, 0.08, 1.0)
WEAR_DEFAULT = 15.0

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
_PROPS = ("oe_wear",)


def _as_factor(value, fallback: float) -> float:
    try:
        v = float(value)
    except (TypeError, ValueError):
        v = fallback
    if v > 1.0:
        v = v / 100.0
    return max(0.0, min(1.0, v))


def _skip_name(name: str) -> bool:
    low = (name or "").lower()
    return any(part in low for part in _SKIP_PARTS)


def _skip_material(mat) -> bool:
    if mat is None:
        return True
    name = getattr(mat, "name", "") or ""
    if is_eye_material(name) or is_glass_family(name) or is_transparent_family(name):
        return True
    return _skip_name(name)


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
        if node.type != "OUTPUT_MATERIAL":
            continue
        try:
            sock = node.inputs.get("Surface") or node.inputs[0]
        except Exception:
            continue
        if sock is not None and sock.is_linked:
            src = sock.links[0].from_node
            if getattr(src, "type", "") == "GROUP":
                return src
    return None


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


def _set_factor(nodes, factor: float) -> None:
    facn = nodes.get(WEAR_FAC)
    if facn is None:
        return
    try:
        facn.inputs[1].default_value = factor
    except Exception:
        pass


def apply_to_material(mat, scene=None) -> bool:
    tree = getattr(mat, "node_tree", None)
    if tree is None or not getattr(mat, "use_nodes", False):
        return False
    if _skip_material(mat):
        return False
    group = _apex_group(tree)
    if group is None:
        return False
    factor = _as_factor(getattr(scene, "oe_wear", WEAR_DEFAULT) if scene else WEAR_DEFAULT, 0.15)
    nodes = tree.nodes
    if nodes.get(WEAR_MIX) is not None:
        _set_factor(nodes, factor)
        return False
    return _insert_wear(tree, nodes, group, factor)


def remove_from_material(mat) -> bool:
    tree = getattr(mat, "node_tree", None)
    if tree is None:
        return False
    nodes = tree.nodes
    mix = nodes.get(WEAR_MIX)
    hp_nodes = [n for n in nodes if n.name.startswith(WEAR_PREFIX)]
    if mix is None and not hp_nodes:
        return False
    if mix is not None:
        orig = None
        a = _color_a(mix)
        if a is not None and a.is_linked:
            orig = a.links[0].from_socket
        out = _color_out(mix)
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
    for node in list(hp_nodes):
        try:
            nodes.remove(node)
        except Exception:
            pass
    return True


def sync_wear(context) -> None:
    scene = getattr(context, "scene", None)
    factor = _as_factor(getattr(scene, "oe_wear", WEAR_DEFAULT) if scene else WEAR_DEFAULT, 0.15)
    for mat in bpy.data.materials:
        tree = getattr(mat, "node_tree", None)
        if tree is None:
            continue
        _set_factor(tree.nodes, factor)


def _insert_wear(tree, nodes, group, factor: float) -> bool:
    albedo = _albedo_input(group)
    if albedo is None:
        return False
    src = None
    hp = nodes.get(HP_COL)
    if hp is not None:
        hp_out = _color_out(hp)
        if hp_out is not None:
            for ln in list(hp_out.links):
                if ln.to_socket == albedo:
                    src = hp_out
                    break
            if src is None and albedo.is_linked and albedo.links[0].from_node == hp:
                src = hp_out
    if src is None and albedo.is_linked:
        try:
            src = albedo.links[0].from_socket
        except Exception:
            src = None
    if albedo.is_linked:
        try:
            tree.links.remove(albedo.links[0])
        except Exception:
            pass

    gx, gy = group.location
    geo = nodes.new("ShaderNodeNewGeometry")
    geo.name = WEAR_GEO
    geo.label = "Wear edges"
    geo.location = (gx - 720.0, gy + 280.0)

    mmap = nodes.new("ShaderNodeMapRange")
    mmap.name = WEAR_MAP
    mmap.label = "Wear mask"
    mmap.location = (gx - 500.0, gy + 280.0)
    try:
        mmap.clamp = True
        mmap.inputs["From Min"].default_value = 0.5
        mmap.inputs["From Max"].default_value = 0.62
        mmap.inputs["To Min"].default_value = 0.0
        mmap.inputs["To Max"].default_value = 1.0
    except Exception:
        pass
    linked_mask = False
    try:
        tree.links.new(geo.outputs["Pointiness"], mmap.inputs["Value"])
        linked_mask = True
    except Exception:
        pass
    if not linked_mask:
        try:
            bevel = nodes.new("ShaderNodeBevel")
            bevel.name = WEAR_PREFIX + "Bevel"
            bevel.location = (gx - 720.0, gy + 400.0)
            bevel.samples = 2
            bevel.inputs["Radius"].default_value = 0.002
            tree.links.new(bevel.outputs["Normal"], mmap.inputs["Value"])
        except Exception:
            pass

    facn = nodes.new("ShaderNodeMath")
    facn.name = WEAR_FAC
    facn.label = "Wear amount"
    facn.location = (gx - 320.0, gy + 280.0)
    facn.operation = "MULTIPLY"
    try:
        facn.use_clamp = True
    except Exception:
        pass
    try:
        facn.inputs[1].default_value = factor
        tree.links.new(mmap.outputs[0], facn.inputs[0])
    except Exception:
        pass

    mix = nodes.new("ShaderNodeMix")
    mix.name = WEAR_MIX
    mix.label = "Wear dirt"
    mix.location = (gx - 140.0, gy + 240.0)
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
    fac_in = _enabled_input(mix, "Factor")
    a = _color_a(mix)
    b = _color_b(mix)
    out = _color_out(mix)
    if out is None:
        return False
    if fac_in is not None:
        try:
            tree.links.new(facn.outputs[0], fac_in)
        except Exception:
            pass
    if b is not None:
        try:
            b.default_value = DIRT
        except Exception:
            pass
    if src is not None and a is not None:
        try:
            tree.links.new(src, a)
        except Exception:
            pass
    elif a is not None:
        try:
            a.default_value = tuple(albedo.default_value)
        except Exception:
            pass
    try:
        tree.links.new(out, albedo)
    except Exception:
        return False
    return True


def _wear_update(self, context):
    try:
        sync_wear(context)
    except Exception:
        pass


def register_props():
    bpy.types.Scene.oe_wear = FloatProperty(
        name="Edge wear",
        description="Dirt multiply on convex edges. 0% off.",
        default=WEAR_DEFAULT,
        min=0.0,
        max=60.0,
        soft_min=0.0,
        soft_max=40.0,
        step=100,
        precision=0,
        subtype="PERCENTAGE",
        update=_wear_update,
    )


def unregister_props():
    for attr in _PROPS:
        if hasattr(bpy.types.Scene, attr):
            delattr(bpy.types.Scene, attr)
