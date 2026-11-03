# MESHFLOW Asset Pack Pipeline v0.30.2

- Fix: «Подготовить меши и сцены» / «Проверить исходники» stopped with
  `Invalid asset id` when MeshInfo model IDs start with a digit
  (e.g. `52_Ruini_Skali_Pesok_01_01`). IDs may now start with a Latin letter or a
  digit and contain Latin letters, digits and underscores. Unreal asset names keep
  their prefixes (`SM_`, `MI_`, `T_`), so they still begin with a letter.
- The per-model override form in Professional mode uses the same rule; the Slate
  form already accepted such IDs.

Same C++ module as v0.30.0. Validated: unit tests including a scan of a
digit-leading model ID and rejection of invalid IDs. Unreal Engine 5.8.4 Win64.
