from __future__ import annotations

"""Mythic / emissive boost. Prefix AAS.OE.Ilm. Does not invent glow on every mesh."""

import bpy
from bpy.props import FloatProperty

from .host import is_eye_material, is_glass_family, should_skip_lod

ILM_PREFIX = "AAS.OE.Ilm."
ILM_COL = ILM_PREFIX + "Col"
ILM_STR = ILM_PREFIX + "Str"
GLOW_DEFAULT = 25.0
_NAME_PARTS = ("mythic", "prestige", "ilm", "emiss")
_SKIP_PARTS = ("eye", "glass", "vfx", "particle")
_COLOR_NAMES = ("Emission Color", "Emission", "Emissive Color", "Emissive")
_STRENGTH_NAMES = ("Emission Strength", "Emissive Strength")
_PROPS = ("oe_glow",)


def _as_factor(value, fallback: float) -> float:
    try:
        v = float(value)
    except (TypeError, ValueError):
        v = fallback
    if v > 1.0:
        v = v / 100.0
    return max(0.0, min(1.0, v))


def _boost(scene) -> float:
    return 1.0 + _as_factor(getattr(scene, "oe_glow", GLOW_DEFAULT) if scene else GLOW_DEFAULT, 0.25)


def _skip_name(name: str) -> bool:
    low = (name or "").lower()
    if is_eye_material(name) or is_glass_family(name):
        return True
    return any(part in low for part in _SKIP_PARTS)


def _skip_mesh(mesh) -> bool:
    name = getattr(mesh, "name", "") or ""
    if _skip_name(name):
        return True
    try:
        if should_skip_lod(mesh):
            return True
    except Exception:
        pass
    return False


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


def _sock(group, names):
    for name in names:
        try:
            sock = group.inputs.get(name)
        except Exception:
            sock = None
        if sock is not None:
            return sock
    return None


def _emission_color(group):
    sock = _sock(group, _COLOR_NAMES)
    if sock is not None:
        low = (sock.name or "").lower()
        if "strength" in low:
            return None
        return sock
    for s in group.inputs:
        low = (s.name or "").lower()
        if ("emission" in low or "emissive" in low) and "strength" not in low:
            return s
    return None


def _emission_strength(group):
    sock = _sock(group, _STRENGTH_NAMES)
    if sock is not None:
        return sock
    for s in group.inputs:
        low = (s.name or "").lower()
        if "strength" in low and ("emiss" in low or "emit" in low):
            return s
    return None


def _name_hit(mat, mesh) -> bool:
    blob = " ".join(
        (
            getattr(mat, "name", "") or "",
            getattr(mesh, "name", "") or "",
        )
    ).lower()
    return any(part in blob for part in _NAME_PARTS)


def _should_glow(mat, mesh, group) -> bool:
    color = _emission_color(group)
    linked = color is not None and getattr(color, "is_linked", False)
    if linked or _name_hit(mat, mesh):
        return color is not None or _emission_strength(group) is not None
    return False


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


def _set_boost(nodes, boost: float) -> None:
    mix = nodes.get(ILM_COL)
    if mix is not None:
        b = _color_b(mix)
        if b is not None:
            try:
                b.default_value = (boost, boost, boost, 1.0)
            except Exception:
                pass
    strn = nodes.get(ILM_STR)
    if strn is not None:
        try:
            strn.inputs[1].default_value = boost
        except Exception:
            pass


def apply_to_material(mat, mesh, scene=None) -> bool:
    if mat is None or _skip_name(getattr(mat, "name", "") or ""):
        return False
    if mesh is not None and _skip_mesh(mesh):
        return False
    tree = getattr(mat, "node_tree", None)
    if tree is None or not getattr(mat, "use_nodes", False):
        return False
    group = _apex_group(tree)
    if group is None or not _should_glow(mat, mesh, group):
        return False
    boost = _boost(scene)
    nodes = tree.nodes
    if nodes.get(ILM_COL) is not None or nodes.get(ILM_STR) is not None:
        _set_boost(nodes, boost)
        return False
    changed = False
    color = _emission_color(group)
    if color is not None:
        changed = _insert_color(tree, nodes, group, color, boost) or changed
    strength = _emission_strength(group)
    if strength is not None:
        changed = _insert_strength(tree, nodes, group, strength, boost) or changed
    return changed


def remove_from_material(mat) -> bool:
    tree = getattr(mat, "node_tree", None)
    if tree is None:
        return False
    nodes = tree.nodes
    found = [n for n in nodes if n.name.startswith(ILM_PREFIX)]
    if not found:
        return False
    mix = nodes.get(ILM_COL)
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
    strn = nodes.get(ILM_STR)
    if strn is not None:
        orig = None
        if strn.inputs and strn.inputs[0].is_linked:
            orig = strn.inputs[0].links[0].from_socket
        dests = [ln.to_socket for ln in list(strn.outputs[0].links)] if strn.outputs else []
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
                    try:
                        sock.default_value = float(strn.inputs[0].default_value)
                    except Exception:
                        pass
            else:
                try:
                    sock.default_value = float(strn.inputs[0].default_value)
                except Exception:
                    pass
    for node in list(found):
        try:
            nodes.remove(node)
        except Exception:
            pass
    return True


def sync_glow(context) -> None:
    scene = getattr(context, "scene", None)
    boost = _boost(scene)
    for mat in bpy.data.materials:
        tree = getattr(mat, "node_tree", None)
        if tree is None:
            continue
        _set_boost(tree.nodes, boost)


def _insert_color(tree, nodes, group, sock, boost: float) -> bool:
    if nodes.get(ILM_COL) is not None:
        return False
    gx, gy = group.location
    mix = nodes.new("ShaderNodeMix")
    mix.name = ILM_COL
    mix.label = "Ilm color"
    mix.location = (gx - 220.0, gy - 220.0)
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
            fac.default_value = 1.0
        except Exception:
            pass
    a = _color_a(mix)
    b = _color_b(mix)
    out = _color_out(mix)
    if out is None:
        return False
    if b is not None:
        try:
            b.default_value = (boost, boost, boost, 1.0)
        except Exception:
            pass
    orig = None
    if sock.is_linked:
        try:
            orig = sock.links[0].from_socket
        except Exception:
            orig = None
        try:
            tree.links.remove(sock.links[0])
        except Exception:
            pass
    elif a is not None:
        try:
            a.default_value = tuple(sock.default_value)
        except Exception:
            pass
    if orig is not None and a is not None:
        try:
            tree.links.new(orig, a)
        except Exception:
            pass
    try:
        tree.links.new(out, sock)
    except Exception:
        return False
    return True


def _insert_strength(tree, nodes, group, sock, boost: float) -> bool:
    if nodes.get(ILM_STR) is not None:
        return False
    gx, gy = group.location
    mul = nodes.new("ShaderNodeMath")
    mul.name = ILM_STR
    mul.label = "Ilm strength"
    mul.location = (gx - 220.0, gy - 360.0)
    mul.operation = "MULTIPLY"
    try:
        mul.inputs[1].default_value = boost
    except Exception:
        pass
    orig = None
    if sock.is_linked:
        try:
            orig = sock.links[0].from_socket
        except Exception:
            orig = None
        try:
            tree.links.remove(sock.links[0])
        except Exception:
            pass
    else:
        try:
            mul.inputs[0].default_value = float(sock.default_value)
        except Exception:
            try:
                mul.inputs[0].default_value = 1.0
            except Exception:
                pass
    if orig is not None:
        try:
            tree.links.new(orig, mul.inputs[0])
        except Exception:
            pass
    try:
        tree.links.new(mul.outputs[0], sock)
    except Exception:
        return False
    return True


def _glow_update(self, context):
    try:
        sync_glow(context)
    except Exception:
        pass


def register_props():
    bpy.types.Scene.oe_glow = FloatProperty(
        name="Mythic glow",
        description="Boost existing emission on mythic / ilm materials. Does nothing without an emission socket.",
        default=GLOW_DEFAULT,
        min=0.0,
        max=100.0,
        soft_min=0.0,
        soft_max=50.0,
        step=100,
        precision=0,
        subtype="PERCENTAGE",
        update=_glow_update,
    )


def unregister_props():
    for attr in _PROPS:
        if hasattr(bpy.types.Scene, attr):
            delattr(bpy.types.Scene, attr)
