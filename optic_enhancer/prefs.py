from __future__ import annotations

import bpy

from .install import OE_OT_drop_old_copy, OE_OT_install_zip, schedule_existing_check
from .panel import OE_OT_uninstall

classes = (
    OE_OT_install_zip,
    OE_OT_drop_old_copy,
    OE_OT_uninstall,
)


class OpticEnhancerPreferences(bpy.types.AddonPreferences):
    bl_idname = __package__

    def draw(self, context):
        layout = self.layout
        layout.label(text="Look pack for Apex Auto Shader")
        row = layout.row(align=True)
        row.operator(OE_OT_install_zip.bl_idname, text="Install ZIP", icon="IMPORT")
        row.operator(OE_OT_uninstall.bl_idname, text="Uninstall", icon="TRASH")
        layout.label(text="Camera, lights, and close-up DOF live in the Apex Shader panel.")


def register():
    bpy.utils.register_class(OpticEnhancerPreferences)
    for cls in classes:
        bpy.utils.register_class(cls)
    schedule_existing_check()


def unregister():
    for cls in reversed(classes):
        try:
            bpy.utils.unregister_class(cls)
        except Exception:
            pass
    try:
        bpy.utils.unregister_class(OpticEnhancerPreferences)
    except Exception:
        pass
