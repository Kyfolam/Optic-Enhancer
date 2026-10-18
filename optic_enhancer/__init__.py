bl_info = {
    "name": "Optic Enhancer",
    "description": "Look expansion pack for Apex Auto Shader — creases, wear, mythic glow, portrait, 5.2 lookdev",
    "author": "Kyfolam",
    "version": (1, 0, 0),
    "blender": (5, 2, 0),
    "location": "View3D > Sidebar > Optic Enhancer",
    "doc_url": "https://github.com/Kyfolam/Optic-Enhancer",
    "category": "Material",
}

from . import glow, hook, host, lights, optics, portrait, presets, render, wear, panel, prefs


def register():
    panel.register()
    prefs.register()
    hook.install()


def unregister():
    try:
        hook.uninstall()
    except Exception:
        pass
    try:
        prefs.unregister()
    except Exception:
        pass
    panel.unregister()


if __name__ == "__main__":
    register()
