from __future__ import annotations

"""Wrap Apex Auto Shader shade_selected so optic passes run after shade."""

import logging
import traceback

import bpy

from . import host, optics, portrait

_log = logging.getLogger("optic_enhancer.hook")
_RETRYING = False


def _apply_after(objects) -> None:
    scene = getattr(bpy.context, "scene", None)
    if scene is None:
        return
    objs = [o for o in list(objects or []) if o is not None]
    if not objs:
        return
    if getattr(scene, "oe_auto", True):
        optics.apply_optics(objs, scene)
        optics._set_flags(objs, True)
        portrait.apply_portrait(objs, scene)
    try:
        from . import render

        render.reapply_materials(objs, scene)
    except Exception:
        _log_exc("render look")


def _log_exc(where: str) -> None:
    """Log without breaking the host shade path."""
    try:
        _log.exception("Optic Enhancer %s failed", where)
    except Exception:
        pass
    try:
        print(f"[Optic Enhancer] {where} failed:\n{traceback.format_exc()}")
    except Exception:
        pass


def _wrap(orig):
    def wrapped(objects, *args, **kwargs):
        result = orig(objects, *args, **kwargs)
        try:
            _apply_after(objects)
        except Exception:
            _log_exc("after-shade pass")
        return result

    wrapped._oe_wrapped = True
    wrapped._oe_orig = orig
    return wrapped


def _utils():
    return host.utils_module()


def _is_wrapped() -> bool:
    utils = _utils()
    orig = getattr(utils, "shade_selected", None) if utils is not None else None
    return bool(orig is not None and getattr(orig, "_oe_wrapped", False))


def _retry():
    global _RETRYING
    try:
        install(retry=False)
    except Exception:
        _log_exc("hook retry install")
    if _is_wrapped():
        _RETRYING = False
        return None
    return 1.0


def install(retry: bool = True) -> None:
    global _RETRYING
    try:
        if host.module() is None:
            if retry and not _RETRYING:
                _RETRYING = True
                try:
                    bpy.app.timers.register(_retry, first_interval=0.5, persistent=True)
                except Exception:
                    _RETRYING = False
                    _log_exc("hook timer register")
            return
        utils = _utils()
        if utils is None:
            return
        orig = getattr(utils, "shade_selected", None)
        if orig is None:
            return
        if getattr(orig, "_oe_wrapped", False):
            return
        utils.shade_selected = _wrap(orig)
    except Exception:
        _log_exc("hook install")


def uninstall() -> None:
    global _RETRYING
    _RETRYING = False
    try:
        utils = _utils()
        if utils is None:
            return
        current = getattr(utils, "shade_selected", None)
        orig = getattr(current, "_oe_orig", None) if current is not None else None
        if orig is not None:
            utils.shade_selected = orig
    except Exception:
        _log_exc("hook uninstall")
