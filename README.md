# Optic Enhancer

Blender **5.2** look pack for [Apex Auto Shader](https://github.com/Kyfolam/Apex-Auto-Shader) **2.1.0**. Release **1.0.0**.

It does not shade, import, or search skins on its own. Install [Apex Auto Shader 2.1.0](https://github.com/Kyfolam/Apex-Auto-Shader/releases/tag/v2.1.0) first.

---

## Install

1. Install and enable [Apex Auto Shader 2.1.0](https://github.com/Kyfolam/Apex-Auto-Shader/releases/tag/v2.1.0)
2. Download the latest **Release** zip of this addon
3. **Edit → Preferences → Get Extensions → Install from Disk**
4. Enable **Optic Enhancer**

The zip root must be the folder `optic_enhancer/`. Do not install a GitHub source zip. Blender rejects a root named `Optic-Enhancer-main`.

`MIN_HOST_VERSION` is **2.1.0**. An older Auto Shader still loads, and the sidebar warns.

---

## How to use

Shade the model with Auto Shader first. Sidebar tab **Optic Enhancer**. Everything that touches a material or the render can be removed again.

### Optic Enhancer

Crease, edge wear, and mythic glow on the current selection. Press the button again to take them off. **Reset all OE passes** also clears portrait and lookdev on those meshes.

Leave **Rounding mix** at 0%. Above that it replaces the baked CAST normal.

**Apply after shade** runs the passes after `shade_selected`. Off means the buttons only.

One selected mesh is the only target. An armature, or nothing selected, uses the character meshes Auto Shader already resolves.

### Portrait Look

Skin SSS on the head and face, translucency on hair cards. Press again to put the previous render state back. The Cycles preset sets AgX, high-quality normals, and denoising. No new meshes.

### Render

Blender 5.2 lookdev: texture cache, a lower viewport texture size, EEVEE ray tracing, thin-wall hair and cloth cards, optional caustics. **Remove Lookdev** writes the old render settings back. Shared Apex node groups are not edited.

### Camera

Front, 3/4, Close-up, light boost, and close-up depth of field stay in **Apex Shader → Camera**. This addon does not add a second lights panel.

---

## Features

- **Armor** — crease shadow in the plate gaps, edge wear, mythic glow only where a glow map already exists
- **Portrait** — skin SSS, hair cards, optional Cycles preset
- **Lookdev** — Cycles texture cache, EEVEE ray tracing, thin wall on local hair and cloth, fully reversible
- **Presets** — export and import the Optic Enhancer settings as JSON

---

## Preferences

**Install ZIP** and **Uninstall** are in the addon preferences, not in the sidebar. If this addon is already installed, Install ZIP asks before it removes the old copy and installs the new one.

---

## Not included

- No CAST import and no skin list. Both stay in [Apex Auto Shader](https://github.com/Kyfolam/Apex-Auto-Shader).
- No second studio rig. Light boost and close-up DOF belong to Auto Shader 2.1.0, so the lights are not multiplied twice.
- Cinematic is a shader in Auto Shader. Lookdev does not change it.
- Corner rounding stays at 0% on purpose.
