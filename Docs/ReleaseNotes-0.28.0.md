# MESHFLOW Asset Pack Pipeline v0.28.0

- Still captures explicitly select Lit regardless of the editor viewport mode.
- Quick Start and Wizard add a second render-options column with optional
  Wireframe, Visibility Collision and Player Collision images.
- Lit remains mandatory; diagnostic images are additional files with mode suffixes.
- The original viewport mode is restored after completion, cancellation or error.
- Slate exposes the same optional render modes; profile setting: previews.view_modes.
- Final ZIPs retain distinct mode names and the individual review page filters modes.

Validated: 146 unit tests, Custom UI layout, native Slate lifecycle, 12 real GPU
captures across Overview, LOW and MID/Nanite, starting/restoring Wireframe.
Unreal Engine 5.8.4 Win64 / BuildId 55116800.
