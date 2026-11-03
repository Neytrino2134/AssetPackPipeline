# MESHFLOW Asset Pack Pipeline v0.30.3

- Fix: visible lighting seams along UV island borders that do not appear in Blender.
  Blender and glTF bake tangent-space normal maps in the OpenGL (Y+) convention,
  while Unreal samples DirectX (Y-). Normal textures were imported without flipping
  the green channel. The importer now enables Flip Green Channel on `T_*_Normal`.
- New profile setting `normal_map_convention`: `OpenGL` (default) or `DirectX`
  (e.g. 3ds Max or Substance DirectX exports). Professional mode: «Формат карты
  нормалей» in «Master material и instances».
- Asset read-back checks the flag; changing the convention invalidates incremental
  receipts so the change is never skipped.
- Already imported packs: run «Обновить материалы и настройки без импорта мешей»
  (settings-only update) to re-apply texture settings without mesh reimport.

Diagnosis: three 2048² normal maps of the Stone Arches Blender pack were analysed
for gradient-field consistency; all match OpenGL by a 4–5× margin. FBX sources have
per-vertex normals and no tangents, so Unreal builds MikkTSpace tangents like Blender.
Tip: MID meshes exported as quads are triangulated by Unreal; triangulate on export
to match the bake exactly.

Same C++ module as v0.30.0. Validated with unit tests. Unreal Engine 5.8.4 Win64.
