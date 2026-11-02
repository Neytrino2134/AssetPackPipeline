"""Simple collision generation and geometry read-back; no complex-as-simple."""
from . import profiles

def inspect(mesh,mode,subsystem):
    import unreal as u
    body=mesh.get_editor_property('body_setup')
    aggregate=body.get_editor_property('agg_geom')
    counts={name:len(aggregate.get_editor_property(name)) for name in ('box_elems','sphere_elems','sphyl_elems','convex_elems')}
    primitives=subsystem.get_simple_collision_count(mesh)
    convex=subsystem.get_convex_collision_count(mesh)
    total=primitives+convex
    shape_ok=(total==0 if mode=='none' else total==1 and counts['box_elems']==1 if mode=='box'
              else total>0 and counts['convex_elems']==total)
    complexity=body.get_editor_property('collision_trace_flag')
    return {'simple_collision_count':total,'collision_shape_counts':counts,'collision_mode':mode,
            'primitive_collision_count':primitives,'convex_collision_count':convex,
            'collision_complexity':str(complexity),'collision_count_ok':shape_ok,
            'collision_complexity_ok':complexity==u.CollisionTraceFlag.CTF_USE_SIMPLE_AND_COMPLEX}

def apply(mesh,profile,subsystem):
    import unreal as u
    mode=profile.get('collision','convex')
    if mode not in ('none','box','convex'):raise ValueError('Unknown collision mode')
    body=mesh.get_editor_property('body_setup');body.modify()
    body.set_editor_property('collision_trace_flag',u.CollisionTraceFlag.CTF_USE_SIMPLE_AND_COMPLEX)
    subsystem.remove_collisions(mesh)
    if mode=='box':
        if subsystem.add_simple_collisions(mesh,u.ScriptingCollisionShapeType.BOX)<0:raise RuntimeError('Box collision generation failed')
    elif mode=='convex':
        config=profiles.convex_settings(profile)
        if not subsystem.set_convex_decomposition_collisions(mesh,config['hull_count'],config['max_hull_verts'],config['precision']):
            raise RuntimeError('Auto Convex collision generation failed; no box fallback was applied')
    result=inspect(mesh,mode,subsystem)
    if not result['collision_count_ok'] or not result['collision_complexity_ok']:
        raise RuntimeError('Collision read-back failed: '+str(result))
    return result
