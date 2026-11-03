"""Explicit viewport modes: lit is mandatory; diagnostics are additional frames."""
from pathlib import Path

MODES={'lit':('VMI_LIT','Lit'),'wireframe':('VMI_WIREFRAME','Wireframe'),
       'collision_visibility':('VMI_COLLISION_VISIBILITY','CollisionVisibility'),
       'collision_pawn':('VMI_COLLISION_PAWN','CollisionPawn')}

def settings(value=None):
    if value is None:value=[]
    if not isinstance(value,(list,tuple)) or any(not isinstance(v,str) or v not in MODES for v in value):
        raise ValueError('Render view modes must be lit, wireframe, collision_visibility or collision_pawn')
    return ['lit']+[mode for mode in MODES if mode!='lit' and mode in value]

def suffix(mode):
    if mode not in MODES:raise ValueError('Unknown render view mode')
    return '_'+MODES[mode][1]

def expand(rows,modes,frame_views=None):
    result=[]
    for row in rows:
        selected = settings(modes) if frame_views is None else (
            frame_views.get(str(row.get('lod_index')), []) if isinstance(frame_views, dict) else frame_views
        )
        for mode in selected:
            path=Path(row['output_path'])
            result.append(dict(row,render_view=mode,id=row['id']+suffix(mode),
                output_path=str(path.with_name(path.stem+suffix(mode)+path.suffix))))
    return result
