"""Real engine vector/read-back checks, confined to the copied floor test host."""
import json
import sys
from pathlib import Path
import unreal as u
plugin=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(plugin/'Content/Python'))
from asset_pack_pipeline import overview,lighting
folder=plugin.parents[1]/'Saved/OverviewFloorSmoke'
assert Path(u.Paths.get_project_file_path()).resolve().is_relative_to(folder)
result={'passed':False,'views':[]}
try:
    data=json.loads((folder/'spec.json').read_text(encoding='utf-8'))
    manifest=data['manifest']['variants'][0]
    les=u.get_editor_subsystem(u.LevelEditorSubsystem)
    assert les.load_level(overview.settings(manifest['profile'])['map_path'])
    actors=overview._actors(manifest['profile'])
    camera=actors['Camera_Overview'];light=actors['KeyLight']
    original=camera.get_actor_rotation()
    original_position=camera.get_actor_location()
    light.set_actor_rotation(u.Rotator(pitch=-45,yaw=60,roll=0),False)
    assert les.save_current_level()
    overview.open_map(manifest)
    def check():
        ray=light.get_actor_forward_vector();front=camera.get_actor_forward_vector()
        horizontal_dot=ray.x*front.x+ray.y*front.y
        assert ray.z<-.6 and horizontal_dot>.5,(ray,front,horizontal_dot)
        assert not lighting.apply_key(light,camera,u),'Light update must be idempotent'
        result['views'].append({'camera_yaw':camera.get_actor_rotation().yaw,
            'light_ray':[ray.x,ray.y,ray.z],'camera_side_dot':horizontal_dot})
    check()
    for yaw in (-180,-90,-60,0,90,180):
        camera.set_actor_rotation(u.Rotator(pitch=-15,yaw=yaw,roll=0),False)
        lighting.apply_key(light,camera,u);check()
    camera.set_actor_rotation(original,False)
    lighting.apply_key(light,camera,u)
    assert camera.get_actor_location()==original_position
    assert les.save_current_level()
    result.update(passed=True,overview_upgraded=True,individual_orbit_directions_passed=True)
except Exception:
    import traceback
    result['error']=traceback.format_exc()
(folder/'LightingResult.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
u.SystemLibrary.quit_editor()
