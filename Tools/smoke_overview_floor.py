"""Check real floor/frustum coverage in a disposable copied content project."""
import json
import math
import sys
from pathlib import Path
import unreal as u
plugin=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(plugin/'Content/Python'))
from asset_pack_pipeline import overview
output=plugin.parents[1]/'Saved/OverviewFloorSmoke'
assert Path(u.Paths.get_project_file_path()).resolve().is_relative_to(output)
result={'passed':False}
try:
    data=json.loads((output/'spec.json').read_text(encoding='utf-8'))
    manifest=data['manifest']['variants'][0]
    map_path=overview.settings(manifest['profile'])['map_path']
    assert u.get_editor_subsystem(u.LevelEditorSubsystem).load_level(map_path)
    actors=overview._actors(manifest['profile'])
    def transforms(items):
        values={}
        for key,actor in items.items():
            if key=='Floor':continue
            p=actor.get_actor_location();r=actor.get_actor_rotation();s=actor.get_actor_scale3d()
            values[key]=[p.x,p.y,p.z,r.pitch,r.yaw,r.roll,s.x,s.y,s.z]
        return values
    actors['Floor'].set_actor_scale3d(u.Vector(10,10,.1))
    assert u.get_editor_subsystem(u.LevelEditorSubsystem).save_current_level()
    before=transforms(actors)
    old_scale=str(actors['Floor'].get_actor_scale3d())
    overview.open_map(manifest)
    actors=overview._actors(manifest['profile'])
    assert before==transforms(actors)
    assert not overview.ensure_backdrop_floor(manifest),'Floor migration must be idempotent'
    floor=actors['Floor'];center,extent=floor.get_actor_bounds(False)
    assert extent.x>=100000 and extent.y>=100000
    points=[]
    for key in ('Camera_Overview','Camera_Detail'):
        camera=actors[key];position=camera.get_actor_location()
        assert abs(position.x-center.x)<extent.x and abs(position.y-center.y)<extent.y
        f=camera.get_actor_forward_vector();r=camera.get_actor_right_vector();up=camera.get_actor_up_vector()
        horizontal=math.tan(math.radians(camera.camera_component.field_of_view/2))
        for aspect in (16/9,4/3,1):
            for x,y in ((-1,-1),(-1,1),(1,-1),(1,1)):
                ray=f+r*(x*horizontal)+up*(y*horizontal/aspect)
                assert ray.z<0,'Corner ray must hit the floor'
                t=-position.z/ray.z
                hit=position+ray*t
                assert abs(hit.x-center.x)<extent.x and abs(hit.y-center.y)<extent.y
                points.append([hit.x,hit.y])
    result.update(passed=True,old_scale=old_scale,new_scale=str(floor.get_actor_scale3d()),
                  width_cm=extent.x*2,depth_cm=extent.y*2,frustum_hits=len(points),
                  cameras_and_meshes_unchanged=True)
except Exception:
    import traceback
    result['error']=traceback.format_exc()
(output/'result.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
u.SystemLibrary.quit_editor()
