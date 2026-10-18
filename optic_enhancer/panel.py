from __future__ import annotations

import bpy
from bpy.props import StringProperty

from . import glow, host, lights, optics, portrait, presets, render, wear


_HELPS = {
    "armor": (
        "Darkens tight plate gaps by multiplying albedo. Baked normals and the "
        "Apex shader stay intact. Leave rounding mix at 0% unless a close-up "
        "needs geo-edge rounding. Optional silhouette subdiv is not applied. "
        "Edge wear and mythic glow are reversible overlays."
    ),
    "portrait": (
        "Skin SSS on head/face and materials that already have a scatter map. "
        "Translucency on hair cards (hashed alpha, backface wrap). Optional Cycles preset: "
        "AgX, high-quality normals, denoising. No new meshes, no pore scans."
    ),
    "render": (
        "Blender 5.2 lookdev. Cycles texture cache, viewport texture scale, "
        "EEVEE screen tracing with backface hits, Fast GI, and overscan. "
        "Thin Wall only on local hair/cloth Principled shaders — shared Apex "
        "groups stay untouched. Remove restores the previous render settings."
    ),
}


class OE_OT_help(bpy.types.Operator):
    bl_idname = "opticenhancer.help"
    bl_label = ""
    bl_description = "Explain this section"
    bl_options = {"INTERNAL"}
    topic: StringProperty(default="armor")

    @classmethod
    def description(cls, context, properties):
        return _HELPS.get(getattr(properties, "topic", ""), cls.bl_description)

    def execute(self, context):
        text = _HELPS.get(self.topic, "")
        if text:
            self.report({"INFO"}, text)
        return {"FINISHED"}


def _scope_note(objs) -> str:
    if objs and all(getattr(o, "type", "") == "MESH" for o in objs):
        if len(objs) == 1:
            return f" on mesh {objs[0].name}"
        return f" on {len(objs)} meshes"
    return ""


def _reset_targets(context) -> list:
    objs = optics._targets(context)
    if objs:
        return objs
    return portrait._targets(context)


class OE_OT_enhance(bpy.types.Operator):
    bl_idname = "opticenhancer.enhance"
    bl_label = "Optic Enhancer"
    bl_description = "Toggle plate crease pass. Click again to restore."
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return host.is_available()

    def execute(self, context):
        if not host.is_available():
            self.report({"ERROR"}, "Apex Auto Shader is not installed")
            return {"CANCELLED"}
        objs = optics._targets(context)
        if not objs:
            self.report({"ERROR"}, "Select the character armature or a mesh")
            return {"CANCELLED"}
        note = _scope_note(objs)
        if optics.optics_is_on(context):
            n = optics.remove_optics(objs)
            optics._set_flags(objs, False)
            self.report({"INFO"}, f"Optic Enhancer removed ({n} material(s){note})")
            return {"FINISHED"}
        n = optics.apply_optics(objs, context.scene)
        optics._set_flags(objs, True)
        if n == 0:
            self.report({"WARNING"}, "No shaded Apex materials found. Shade the model first.")
            return {"CANCELLED"}
        self.report({"INFO"}, f"Optic Enhancer applied ({n} material(s){note})")
        return {"FINISHED"}


class OE_OT_portrait(bpy.types.Operator):
    bl_idname = "opticenhancer.portrait"
    bl_label = "Portrait Look"
    bl_description = "Toggle skin SSS, hair-card wrap, optional Cycles preset."
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return host.is_available()

    def execute(self, context):
        if not host.is_available():
            self.report({"ERROR"}, "Apex Auto Shader is not installed")
            return {"CANCELLED"}
        objs = portrait._targets(context)
        if not objs:
            self.report({"ERROR"}, "Select the character armature or a mesh")
            return {"CANCELLED"}
        note = _scope_note(objs)
        if portrait.portrait_is_on(context):
            n = portrait.remove_portrait(objs)
            self.report({"INFO"}, f"Portrait Look removed ({n} material(s){note})")
            return {"FINISHED"}
        n = portrait.apply_portrait(objs, context.scene)
        if n == 0:
            self.report(
                {"WARNING"},
                "No skin or hair materials found. Shade the model first.",
            )
            if not portrait.portrait_is_on(context):
                return {"CANCELLED"}
        self.report({"INFO"}, f"Portrait Look applied ({n} material(s){note})")
        return {"FINISHED"}


class OE_OT_reset_all(bpy.types.Operator):
    bl_idname = "opticenhancer.reset_all"
    bl_label = "Reset all OE passes"
    bl_description = (
        "Remove crease, wear, glow, portrait, and lookdev render for the current targets"
    )
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return host.is_available()

    def execute(self, context):
        if not host.is_available():
            self.report({"ERROR"}, "Apex Auto Shader is not installed")
            return {"CANCELLED"}
        objs = _reset_targets(context)
        if not objs:
            self.report({"ERROR"}, "Select the character armature or a mesh")
            return {"CANCELLED"}
        note = _scope_note(objs)
        n_optics = optics.remove_optics(objs)
        optics._set_flags(objs, False)
        n_portrait = portrait.remove_portrait(objs)
        render_msg = ""
        if render.look_is_on(context.scene):
            render_msg = render.disable_look(context)
        total = n_optics + n_portrait
        self.report(
            {"INFO"},
            f"Reset OE passes ({n_optics} optic, {n_portrait} portrait material(s){note})",
        )
        if render_msg:
            self.report({"INFO"}, render_msg)
        if total == 0 and not render_msg:
            self.report({"WARNING"}, "No OE passes found on current targets")
        return {"FINISHED"}


def clear_all_effects() -> None:
    """Strip crease, wear, glow, portrait, subdiv, and lookdev from every object."""
    objects = [
        obj
        for obj in list(getattr(bpy.data, "objects", []) or [])
        if getattr(obj, "type", "") in {"MESH", "ARMATURE"}
    ]
    try:
        optics.remove_optics(objects)
        optics._set_flags(objects, False)
    except Exception:
        pass
    try:
        portrait.remove_portrait(objects)
    except Exception:
        pass
    for obj in list(getattr(bpy.data, "objects", []) or []):
        if getattr(obj, "type", "") != "MESH":
            continue
        mods = getattr(obj, "modifiers", None)
        if mods is None or "AAS.Optics.Subsurf" not in mods:
            continue
        try:
            mods.remove(mods["AAS.Optics.Subsurf"])
        except Exception:
            pass
    scene = getattr(bpy.context, "scene", None)
    try:
        if scene is not None and render.look_is_on(scene):
            render.disable_look(bpy.context)
    except Exception:
        pass
    try:
        portrait._restore_render(scene)
    except Exception:
        pass


class OE_OT_uninstall(bpy.types.Operator):
    bl_idname = "opticenhancer.uninstall"
    bl_label = "Deinstallieren"
    bl_description = (
        "Entfernt alle Optic-Enhancer-Effekte und schaltet das Addon aus"
    )
    bl_options = {"INTERNAL"}

    def invoke(self, context, event):
        return context.window_manager.invoke_confirm(self, event)

    def execute(self, context):
        clear_all_effects()
        pkg = __package__ or "optic_enhancer"

        def _uninstall():
            try:
                bpy.ops.preferences.addon_disable(module=pkg)
            except Exception:
                pass
            try:
                bpy.ops.extensions.package_uninstall(
                    repo="user_default", pkg_id="optic_enhancer"
                )
            except Exception:
                try:
                    bpy.ops.preferences.addon_remove(module=pkg)
                except Exception:
                    pass
            return None

        try:
            bpy.app.timers.register(_uninstall, first_interval=0.25)
        except Exception:
            _uninstall()
        self.report({"INFO"}, "Optic Enhancer wird deinstalliert")
        return {"FINISHED"}


def _help(layout, topic: str) -> None:
    op = layout.operator(OE_OT_help.bl_idname, text="", icon="INFO", emboss=False)
    op.topic = topic


def _draw_host_missing(layout) -> None:
    box = layout.box()
    box.label(text="Apex Auto Shader required", icon="ERROR")
    box.label(text="Install and enable it, then restart Blender.")
    box.label(text="This pack does nothing on its own.")


def _draw_host_version_warning(layout) -> None:
    warn = host.version_warning()
    if not warn:
        return
    box = layout.box()
    box.label(text=warn, icon="ERROR")
    box.label(text="Update Apex Auto Shader for best results.")


class OE_PT_armor(bpy.types.Panel):
    bl_label = "Optic Enhancer"
    bl_idname = "OE_PT_armor"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Optic Enhancer"

    def draw_header(self, context):
        _help(self.layout, "armor")

    def draw(self, context):
        layout = self.layout
        if not host.is_available():
            _draw_host_missing(layout)
            return
        _draw_host_version_warning(layout)
        scene = context.scene
        on = optics.optics_is_on(context)
        layout.operator(
            OE_OT_enhance.bl_idname,
            text="Remove Optic Enhancer" if on else "Optic Enhancer",
            icon="SHADERFX",
            depress=on,
        )
        layout.operator(
            OE_OT_reset_all.bl_idname,
            text="Reset all OE passes",
            icon="LOOP_BACK",
        )
        col = layout.column(align=True)
        col.prop(scene, "oe_ao")
        col.prop(scene, "oe_ao_dist")
        col.prop(scene, "oe_mix")
        col.prop(scene, "oe_bevel")
        col.separator()
        col.prop(scene, "oe_wear")
        col.prop(scene, "oe_glow")
        col.separator()
        col.prop(scene, "oe_subdiv")
        col.prop(scene, "oe_displace")
        col.separator()
        col.prop(scene, "oe_auto")
        layout.separator()
        row = layout.row(align=True)
        row.operator("opticenhancer.preset_export", text="Export", icon="EXPORT")
        row.operator("opticenhancer.preset_import", text="Import", icon="IMPORT")


class OE_PT_portrait(bpy.types.Panel):
    bl_label = "Portrait Look"
    bl_idname = "OE_PT_portrait"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Optic Enhancer"

    @classmethod
    def poll(cls, context):
        return host.is_available()

    def draw_header(self, context):
        _help(self.layout, "portrait")

    def draw(self, context):
        layout = self.layout
        scene = context.scene
        on = portrait.portrait_is_on(context)
        layout.operator(
            OE_OT_portrait.bl_idname,
            text="Remove Portrait Look" if on else "Portrait Look",
            icon="SHADING_RENDERED",
            depress=on,
        )
        col = layout.column(align=True)
        col.prop(scene, "oe_sss")
        col.prop(scene, "oe_hair")
        col.prop(scene, "oe_cycles")


class OE_PT_render(bpy.types.Panel):
    bl_label = "Render"
    bl_idname = "OE_PT_render"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Optic Enhancer"

    @classmethod
    def poll(cls, context):
        return host.is_available()

    def draw_header(self, context):
        _help(self.layout, "render")

    def draw(self, context):
        layout = self.layout
        if not render.blender_52():
            box = layout.box()
            box.label(text="Needs Blender 5.2 LTS", icon="ERROR")
            return
        scene = context.scene
        on = render.look_is_on(scene)
        layout.operator(
            render.OE_OT_render_look.bl_idname,
            text="Remove Lookdev" if on else "Lookdev render",
            icon="RENDER_RESULT",
            depress=on,
        )
        col = layout.column(align=True)
        col.prop(scene, "oe_tx_cache")
        col.prop(scene, "oe_viewport_tex")
        col.prop(scene, "oe_eevee_rt")
        col.prop(scene, "oe_thin_wall")
        col.prop(scene, "oe_caustics")
        row = layout.row(align=True)
        row.operator(render.OE_OT_generate_tx.bl_idname, text="Generate tx", icon="TEXTURE")
        row.operator(render.OE_OT_copy_linking.bl_idname, text="Copy linking", icon="LINKED")


classes = (
    OE_OT_help,
    OE_OT_enhance,
    OE_OT_portrait,
    OE_OT_reset_all,
    OE_PT_armor,
    OE_PT_portrait,
    OE_PT_render,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    presets.register()
    render.register()
    optics.register_props()
    wear.register_props()
    glow.register_props()
    portrait.register_props()
    lights.register_props()


def _safe(fn) -> None:
    try:
        fn()
    except Exception:
        pass


def unregister():
    """Drop every panel, operator, and scene property this addon registered."""
    _safe(lights.unregister_props)
    _safe(portrait.unregister_props)
    _safe(glow.unregister_props)
    _safe(wear.unregister_props)
    _safe(optics.unregister_props)
    _safe(presets.unregister)
    for cls in reversed(classes):
        try:
            bpy.utils.unregister_class(cls)
        except Exception:
            pass
    _safe(render.unregister)
