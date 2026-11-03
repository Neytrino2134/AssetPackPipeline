# MESHFLOW Asset Pack Pipeline v0.31.0

## Smart Normal map conversion
- New Quick Start option «Умное конвертирование Normal текстур» in «1. Исходники»
  (on by default; remembered between sessions). Off imports Normal maps as they are.
- The importer chooses the Normal map and its convention per model:
  1. MeshInfo texture entries (new Blender exporter): the `preferred` Normal entry;
     convention from `convention`, then `unreal.flip_green_channel`, then file suffix.
  2. Older MeshInfo without texture entries: `T_<id>_Normal_DirectX/_DX.png`, then
     `_OpenGL/_GL.png`, then `T_<id>_Normal.png`.
  3. DirectX → imported as-is; OpenGL or no label (Blender bake) → Flip Green Channel.
- BaseColor is also taken from MeshInfo texture entries when present.
- Professional mode «Формат карты нормалей»: `Auto` (new default), `OpenGL`, `DirectX`.
  Manual modes prefer a listed file in that convention when both exist.
- «Проверить исходники» logs the decision, e.g. «Normal: 10 DirectX — без конвертации».
- The decision is part of the scan manifest, asset read-back and incremental receipts.

## MeshInfo compatibility
- Mesh and texture paths resolve against the export root (new exporter) or, for
  older catalogs stored next to the files (e.g. `FBX/MeshInfo.json`), against that folder.

Validated on real Blender packs: Fantasy Stone Arches (new JSON → 10/10 DirectX, no
conversion; old FBX/MeshInfo.json → 10/10 DirectX by suffix) and Stone Arches (old,
unlabeled → 12/12 OpenGL, flipped). Gradient-field analysis confirmed the
`_Normal_DirectX.png` maps are DirectX and the plain maps OpenGL. 170 unit tests;
Custom UI option and session persistence checked in the window preview.
Same C++ module as v0.30.0. Unreal Engine 5.8.4 Win64.
