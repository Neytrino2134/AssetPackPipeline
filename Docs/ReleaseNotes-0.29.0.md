# MESHFLOW Asset Pack Pipeline v0.29.0

- Quick Start/Wizard use fitted Auto Convex simple collision instead of a single box.
- Professional settings expose convex / box / none and hull-count/vertex/precision budgets.
- Convex and primitive shape counts are validated separately and preserved in clean-project checks.
- Settings-only updates regenerate collisions without mesh reimport.
- Render collision audit samples inside a convex hull, allowing concave mesh centres to remain empty.
- Existing explicit box/none profiles remain supported; convex generation never silently falls back to a box.

Validated in UE 5.8.4 Win64 on a real stone mesh and copied LOD/MID assets,
including capsule blocking and Pawn response; 151 unit tests.
