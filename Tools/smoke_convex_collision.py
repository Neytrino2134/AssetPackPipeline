"""Real convex generation and blocking capsule sweep in an isolated project."""
import json
import sys
from pathlib import Path
import unreal as u
plugin=Path(__file__).resolve().parents[1];project=plugin.parents[1]
sys.path.insert(0,str(plugin/'Content/Python'))
from asset_pack_pipeline import collision,runtime,media
assert Path(u.Paths.get_project_file_path()).resolve().is_relative_to(project/'Saved/RenderViewsSmoke')
folder=project/'Saved/CollisionSmoke';folder.mkdir(exist_ok=True)
result={'passed':False,'meshes':[]}
try:
    source=r'D:\Work\3D Stocks\3D Asset Packs\!NewAssetPack\22_Fantasy_Stone_Arches_Ready\!Unreal\FBX\SM_Fantasy_Stone_01_01_LOD0.fbx'
    options=u.FbxImportUI();options.automated_import_should_detect_type=False;options.import_as_skeletal=False
    options.mesh_type_to_import=u.FBXImportType.FBXIT_STATIC_MESH;options.original_import_type=u.FBXImportType.FBXIT_STATIC_MESH
    options.import_materials=False;options.import_textures=False;options.static_mesh_import_data.auto_generate_collision=False
    imported=runtime.import_file(source,'/Game/CollisionRegression','Stone',options,u.FbxFactory())
    stone=next(obj for obj in imported if isinstance(obj,u.StaticMesh))
    base='/Game/NativeRegression_8bcf273e'
    mid=u.EditorAssetLibrary.duplicate_asset(base+'/StaticMeshes/Nanite/SM_Containers_01_02_MID','/Game/CollisionRegression/TestMID')
    lod=u.EditorAssetLibrary.duplicate_asset(base+'/StaticMeshes/LOD/SM_Containers_01_02_LODS','/Game/CollisionRegression/TestLODS')
    instance=u.load_asset(base+'/Materials/Instances/MI_Containers_01_02')
    for mesh,nanite,sizes in ((stone,False,[1]),(mid,True,[1]),(lod,False,[1,.5,.25,.125,.0625])):
        before=[mesh.get_num_triangles(i) for i in range(runtime.smes().get_lod_count(mesh))]
        profile={'source_format':'FBX','collision':'convex','lod_screen_sizes':sizes,'nanite_enabled':nanite}
        runtime._settings({'profile':profile},mesh,instance)
        check=collision.inspect(mesh,'convex',runtime.smes())
        assert before==[mesh.get_num_triangles(i) for i in range(runtime.smes().get_lod_count(mesh))]
        assert mesh.get_editor_property('nanite_settings').enabled==nanite
        assert check['collision_shape_counts']['box_elems']==0 and check['collision_shape_counts']['convex_elems']>0
        u.EditorAssetLibrary.save_loaded_asset(mesh)
        result['meshes'].append(dict(path=mesh.get_path_name(),**check))
    u.EditorLoadingAndSavingUtils.new_blank_map(False)
    actor=u.get_editor_subsystem(u.EditorActorSubsystem).spawn_actor_from_class(u.StaticMeshActor,u.Vector(0,0,0))
    actor.static_mesh_component.set_static_mesh(stone)
    actor.static_mesh_component.set_collision_profile_name('BlockAll')
    actor.static_mesh_component.set_collision_enabled(u.CollisionEnabled.QUERY_AND_PHYSICS)
    center,extent=actor.get_actor_bounds(False)
    start=u.Vector(center.x,center.y-extent.y-100,center.z)
    end=u.Vector(center.x,center.y+extent.y+100,center.z)
    hit=u.SystemLibrary.capsule_trace_single_for_objects(actor,start,end,10,30,
        [u.ObjectTypeQuery.OBJECT_TYPE_QUERY1],False,[],u.DrawDebugTrace.NONE,False)
    data=hit if isinstance(hit,u.HitResult) else next((v for v in (hit or []) if isinstance(v,u.HitResult)),None)
    result['capsule_sweep_blocked']=bool(data and data.to_tuple()[0])
    result['pawn_response']=str(actor.static_mesh_component.get_collision_response_to_channel(u.CollisionChannel.ECC_PAWN))
    assert result['capsule_sweep_blocked']
    assert actor.static_mesh_component.get_collision_response_to_channel(u.CollisionChannel.ECC_PAWN)==u.CollisionResponseType.ECR_BLOCK
    camera=u.get_editor_subsystem(u.EditorActorSubsystem).spawn_actor_from_class(u.CameraActor,u.Vector(500,500,500))
    result['render_collision_audit']=media.collision_audit(camera,actor,camera,True)
    assert result['render_collision_audit']['passed']
    result['passed']=True
except Exception:
    import traceback
    result['error']=traceback.format_exc()
(folder/'result.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
u.SystemLibrary.quit_editor()
