"""Shared camera-side key light for overview and individual asset studios."""
def key_rotation(camera_yaw):
    # Pitch 225 points down with reversed horizontal direction. At the default
    # camera yaw -90 this gives yaw 60, illuminating from the +Y camera side.
    return {'pitch':225.0,'yaw':(float(camera_yaw)+150.0)%360.0,'roll':0.0}


def apply_key(light,camera,engine):
    rotation=engine.Rotator(**key_rotation(camera.get_actor_rotation().yaw))
    desired=engine.MathLibrary.get_forward_vector(rotation)
    current=light.get_actor_forward_vector()
    if sum((a-b)**2 for a,b in zip((current.x,current.y,current.z),(desired.x,desired.y,desired.z)))<1e-10:
        return False
    light.modify()
    light.set_actor_rotation(rotation,False)
    return True
