# Optic Enhancer

Blender **5.2** look pack for [Apex Auto Shader](https://github.com/Kyfolam/Apex-Auto-Shader). Release **1.1.0**.

This tool is just for optic enhancement, additional tool for the Apex Auto Shader.
Install Apex Auto Shader first. **2.1.0** or newer, **2.2.0** is the current one.

---

## Install

1. Download the latest **Release** zip of this addon
2. **Edit → Preferences → Get Extensions → Install from Disk**
3. Enable **Optic Enhancer**

---

## How to use

Just use the sidebar tab **Optic Enhancer**. Press a button again to take that pass off.

### Optic Enhancer

**Crease** adds the gap shadow, edge wear, and mythic glow on the current selection. **Reset all OE passes** also clears portrait and lookdev on those meshes.

**Auto Optimize** follows the render engine. Eevee turns on ray tracing. Cycles turns on the texture cache.

Leave **Rounding mix** at 0%. Above that it replaces the baked CAST normal.

**Apply after shade** runs the passes after Auto Shader shades. Off means the buttons only.

### Portrait Look

Skin SSS on the head and face, translucency on hair cards. The Cycles preset sets AgX, high-quality normals, and denoising. No new meshes.

### Render

**Lookdev render** sets the Blender 5.2 viewport: texture cache, a lower viewport texture size, EEVEE ray tracing, thin-wall hair and cloth, optional caustics. **Remove Lookdev** writes the old render settings back.

**Generate tx** and **Copy linking** sit on the same panel.

### Camera

Front, 3/4, Close-up, light boost, and close-up depth of field stay in **Apex Shader → Camera**. This addon does not add a second light panel.

---

## Features

- **Crease** — gap shadow, edge wear, mythic glow only where a glow map already exists
- **Portrait** — skin SSS, hair cards, optional Cycles preset
- **Lookdev** — Cycles texture cache, EEVEE ray tracing, thin wall on hair and cloth, fully reversible
- **Presets** — export and import the Optic Enhancer settings as JSON

---

## Preferences

**Install ZIP** and **Uninstall** are in the addon preferences, not in the sidebar. If this addon is already installed, Install ZIP asks before it removes the old copy.

---

## 1.1.0

- Auto Optimize for the current render engine
- Install ZIP and Uninstall in the addon preferences
- Works with Apex Auto Shader 2.1.0 and newer

## 1.0.0

- Crease, edge wear, mythic glow, portrait, and Blender 5.2 lookdev
