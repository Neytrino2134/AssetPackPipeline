"""Automatic LOD boundary probes using original-mesh renderer draw-command CSVs."""
import csv
import html
import json
import math
import shutil
from pathlib import Path


def samples(screen_sizes, margin=.1):
    if len(screen_sizes)<2 or any(a<=b or b<=0 for a,b in zip(screen_sizes,screen_sizes[1:])):
        raise ValueError('Automatic LOD review requires descending positive screen sizes')
    result=[]
    for lod,threshold in enumerate(screen_sizes[1:],1):
        for side,factor in [('near',1+margin),('far',1-margin)]:
            size=threshold*factor
            expected=next((i for i in range(len(screen_sizes)-1,0,-1) if screen_sizes[i]>size),0)
            result.append({'boundary_lod':lod,'side':side,'target_screen_size':size,'expected_lod':expected})
    return result


def distance(radius,screen_size,aspect=16/9,fov=90):
    return max(1,aspect)*radius/(math.tan(math.radians(fov)/2)*screen_size)


def rows(assets,checks,config,folder,studio):
    result=[]
    for n,(asset,check) in enumerate(zip(assets,checks)):
        common={'asset_id':asset['id'],'yaw':config['yaw_angles'][0],'view_index':0,'map_path':studio,
                'status':'pending','capture_mode':'lit'}
        if n==0:
            for lod in range(check['lod_count']):
                result.append(dict(common,id=f'{asset["id"]}_calibration_{lod}',lod_index=lod,
                    expected_lod=lod,calibration=True,output_path=str(Path(folder)/f'Calibration_LOD{lod}.png')))
        for index,sample in enumerate(samples(check['screen_sizes'])):
            name=f'{asset["id"]}_boundary{sample["boundary_lod"]}_{sample["side"]}'
            result.append(dict(common,**sample,id=name,lod_index=sample['expected_lod'],automatic_lod=True,
                sample_index=index,output_path=str(Path(folder)/(name+'.png'))))
    return result


def inspect_stats(path,asset_id,expected_lod,triangles):
    with Path(path).open(encoding='utf-8-sig',newline='') as stream:rows=list(csv.DictReader(stream))
    matches=[row for row in rows if row.get('ResourceName','').split('.')[-1].split('/')[-1]=='SM_'+asset_id
             and 'BasePass' in row.get('Pass','') and int(row.get('VisibleInstances',0))>0]
    if not matches:raise RuntimeError('No original mesh BasePass draw command in renderer CSV')
    observed={int(row['LODIndex']) for row in matches}
    if len(observed)!=1:raise RuntimeError('Ambiguous renderer LODs: '+str(sorted(observed)))
    sections={}
    for row in matches:
        segment=int(row.get('SegmentIndex',0))
        if segment in sections:raise RuntimeError('Ambiguous BasePass draws for the same mesh section')
        sections[segment]=int(row['PrimitiveCount'])
    total=sum(sections.values())
    lod=next(iter(observed))
    if lod!=expected_lod or total!=triangles[expected_lod]:
        raise RuntimeError(f'Renderer LOD mismatch: expected {expected_lod}/{triangles[expected_lod]} tris, got {lod}/{total}')
    return {'observed_lod':lod,'observed_triangles':total,'actual_lod_verified':True,'renderer_draws':matches}


def advance_stats(report,row,state,camera):
    """Request one real renderer frame, then wait for its GPU readback CSV."""
    import unreal as u
    # Hidden/idle editor viewports must keep drawing until GPU readback completes.
    u.get_editor_subsystem(u.LevelEditorSubsystem).editor_invalidate_viewports()
    folder=Path(u.Paths.project_saved_dir()).resolve()/'Profiling'
    if 'stats_category' not in state:
        folder.mkdir(parents=True,exist_ok=True)
        category=f'APP_{report["run_id"][:8]}_{report["assets"].index(row):03d}'
        state['stats_category']=category
        world=u.get_editor_subsystem(u.UnrealEditorSubsystem).get_editor_world()
        u.SystemLibrary.execute_console_command(world,'r.MeshDrawCommands.DumpStats '+category)
        return False
    files=list(folder.glob('MeshDrawCommandStats-'+state['stats_category']+'-*.csv'))
    if not files:return False
    if len(files)!=1:raise RuntimeError('Ambiguous renderer CSV files')
    path=files[0]
    if 'stats_file_seen' not in state:state['stats_file_seen']=str(path);return False
    check=next(a for a in report['source_asset_checks'] if a['id']==row['asset_id'])
    result=inspect_stats(path,row['asset_id'],row['expected_lod'],check['triangles'])
    target=Path(report['output_directory'])/(row['id']+'.csv');shutil.copy2(path,target)
    row.update(result,renderer_csv=str(target))
    state.pop('stats_category');state.pop('stats_file_seen')
    return True


def restore(state):
    if 'original_view_mode' in state:
        import unreal as u
        u.AutomationLibrary.set_editor_active_viewport_view_mode(state.pop('original_view_mode'))


def write_review(report):
    folder=Path(report['output_directory']);cells=[]
    for row in report['assets']:
        if not row.get('automatic_lod'):continue
        name=html.escape(Path(row['output_path']).name,quote=True)
        image=('<a href="'+name+'"><img loading="lazy" src="'+name+'"></a>') if row['status']=='passed' else html.escape(row['status']+': '+row.get('error',''))
        stats=('<a href="'+html.escape(Path(row['renderer_csv']).name,quote=True)+'">CSV</a>') if row.get('renderer_csv') else 'unverified'
        cells.append('<tr><td>'+html.escape(row['asset_id'])+'<br>LOD'+str(row['boundary_lod'])+' '+row['side']+
            '<br>'+str(round(row.get('camera',{}).get('distance',0)/100,2))+' m</td><td>'+str(row['expected_lod'])+
            '</td><td>'+str(row.get('observed_lod','unverified'))+'<br>'+str(row.get('observed_triangles','?'))+' tris<br>'+stats+'</td><td>'+image+'</td></tr>')
    (folder/'review.json').write_text(json.dumps({'run_id':report['run_id'],'status':report['status'],
        'rows':report['assets'],'evidence_method':'original_mesh_draw_command_csv','publication_ready':False},indent=2),encoding='utf-8')
    page='<!doctype html><meta charset="utf-8"><title>Automatic LOD review</title><style>body{background:#171a20;color:#eee;font:15px system-ui;margin:24px}table{width:100%;border-collapse:collapse}td,th{border:1px solid #454d5a;padding:8px}img{width:100%;max-width:800px}a{color:#8ec7ff}</style><h1>Automatic LOD boundary review</h1><p>Camera FOV 90°, 1280×720. Each boundary is sampled at screen size ±10%. Expected LOD is calculated. Observed LOD and triangles come directly from original-mesh BasePass draw commands recorded by r.MeshDrawCommands.DumpStats. Automatic samples use forced_lod_model=0. Five initial forced-LOD frames validate the renderer counters. No diagnostic geometry copy or material replacement is used. Click PNG/CSV links for evidence. This tests discrete positions, not continuous transition animation or artist approval.</p><p>Status: '+html.escape(report['status'])+'</p><table><tr><th>Model / boundary / distance</th><th>Expected LOD</th><th>Renderer LOD / triangles</th><th>Original mesh / Lit</th></tr>'+''.join(cells)+'</table>'
    path=folder/'review.html';path.write_text(page,encoding='utf-8');return str(path)
