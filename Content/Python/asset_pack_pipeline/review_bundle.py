"""Complete-model LOD/Nanite review board from verified render jobs."""
import html
import json
import shutil
from pathlib import Path
from . import discovery


def build(reports, folder):
    if not reports: raise ValueError('Select at least one completed media job')
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=False)
    frames=[];models={};packs=set()
    for report in reports:
        if report.get('kind')!='individual_previews' or report.get('status')!='passed':
            raise ValueError('Review bundle requires completed individual preview jobs')
        manifest=report['manifest'];packs.add(manifest['profile']['pack_id'])
        mode='Nanite' if manifest['profile'].get('nanite_enabled') else 'LOD'
        expected={a['id'] for a in manifest['assets']}
        if not expected:raise ValueError('Review bundle requires catalog models')
        completed={r['asset_id'] for r in report['assets'] if r['status']=='passed'}
        if expected!=completed:raise ValueError('Media job does not cover every catalog model')
        for check in report['source_asset_checks']:
            item=models.setdefault(check['id'],{'id':check['id'],'checks':[]})
            item['checks'].append({'mode':mode,'strict_passed':check.get('strict_passed',check['passed']),
                'warnings':check.get('warnings',[]),'expected_triangles':check['expected_triangles'],
                'source_triangles':check.get('source_triangles',check['triangles'])})
        source=Path(report['output_directory']).resolve()
        target=folder/report['run_id'];target.mkdir()
        for row in report['assets']:
            path=Path(row['output_path']).resolve()
            if row['status']!='passed' or path.parent!=source or not path.is_file() or discovery.digest(path)!=row['sha256']:
                raise ValueError('Missing, changed or foreign review image')
            output=target/path.name;shutil.copy2(path,output)
            if discovery.digest(output)!=row['sha256']:raise RuntimeError('Image changed while copying')
            frames.append({'asset_id':row['asset_id'],'mode':mode,'lod_index':row['lod_index'],'yaw':row['yaw'],
                'file':output.relative_to(folder).as_posix(),'sha256':row['sha256']})
    if len(packs)!=1:raise ValueError('Review jobs must belong to one pack')
    # A representation may not silently omit models that another contains.
    sets=[{c['id'] for c in report['source_asset_checks']} for report in reports]
    if any(ids!=sets[0] for ids in sets):raise ValueError('Every representation must contain the same models')
    data={'pack_id':next(iter(packs)),'models':list(models.values()),'frames':frames,
          'publication_ready':False,'review_status':'pending'}
    (folder/'review.json').write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
    content='''<!doctype html><meta charset="utf-8"><title>Complete asset pack review</title>
<style>body{background:#171a20;color:#edf0f5;font:15px system-ui;margin:24px}select,button,textarea{background:#303744;color:inherit;border:1px solid #66738a;padding:8px;margin:5px}label{display:inline-block}#images{display:grid;grid-template-columns:1fr 1fr;gap:12px}img{width:100%;background:#252b36}pre{white-space:pre-wrap;background:#242a34;padding:12px;max-height:320px;overflow:auto}textarea{width:90%;height:80px}p{max-width:1200px}.warning{color:#ffca7a}</style>
<h1>__PACK__ — all models</h1><p>Every model remains in preparation. Geometry/catalog warnings are listed below and do not remove the model. Compare silhouette, normals, UV details and material appearance. Technical preparation and artistic approval are separate.</p>
<label>Model <select id="model"></select></label><label>View <select id="view"></select></label><label>Reference <select id="a"></select></label><label>Compare <select id="b"></select></label>
<div id="images"><div><p id="al"></p><img id="ai"></div><div><p id="bl"></p><img id="bi"></div></div>
<p class="warning" id="quality"></p><details><summary>Technical checks and warnings</summary><pre id="issues"></pre></details>
<label>Appearance <select id="decision"><option value="pending">Pending</option><option value="accept">Accept appearance</option><option value="revise">Needs revision</option></select></label><textarea id="notes" placeholder="Notes for this model"></textarea><button id="export">Export decisions JSON</button><p>Decisions are saved in this browser until exported. Export does not update Unreal or certify publication.</p>
<script>const data=__DATA__;const $=id=>document.getElementById(id);const key='APP-full-review-'+data.pack_id+'-'+data.frames[0].sha256;let notes={};try{notes=JSON.parse(localStorage.getItem(key)||'{}')}catch(e){}
const unique=a=>[...new Set(a)];const label=f=>f.mode==='Nanite'?'Nanite':`LOD${f.lod_index}`;function options(id,values){$(id).replaceChildren(...values.map(v=>{let o=document.createElement('option');o.value=v;o.textContent=v;return o}))}
function rows(){return data.frames.filter(f=>f.asset_id===$('model').value&&String(f.yaw)===$('view').value)}function images(){for(let side of ['a','b']){let f=rows().find(f=>label(f)===$(side).value);if(f){$(side+'i').src=f.file;$(side+'l').textContent=label(f)+' / '+f.yaw+'°'}}}
function views(){options('view',unique(data.frames.filter(f=>f.asset_id===$('model').value).map(f=>f.yaw)));variants();let m=data.models.find(m=>m.id===$('model').value);$('issues').textContent=JSON.stringify(m.checks,null,2);$('quality').textContent=m.checks.some(c=>!c.strict_passed)?'Prepared with quality warnings — model retained':'Technical checks passed; appearance review pending';let n=notes[m.id]||{};$('decision').value=n.decision||'pending';$('notes').value=n.notes||''}
function variants(){let values=unique(rows().map(label));options('a',values);options('b',values);$('b').selectedIndex=values.length-1;images()}
function save(){notes[$('model').value]={decision:$('decision').value,notes:$('notes').value};try{localStorage.setItem(key,JSON.stringify(notes))}catch(e){}}
options('model',data.models.map(m=>m.id));$('model').onchange=views;$('view').onchange=variants;$('a').onchange=images;$('b').onchange=images;$('decision').onchange=save;$('notes').oninput=save;
$('export').onclick=()=>{save();let a=document.createElement('a');a.href=URL.createObjectURL(new Blob([JSON.stringify({pack_id:data.pack_id,decisions:notes,publication_ready:false},null,2)],{type:'application/json'}));a.download='all-models-review-decisions.json';a.click();setTimeout(()=>URL.revokeObjectURL(a.href),1000)};views();</script>'''
    content=content.replace('__PACK__',html.escape(data['pack_id'])).replace('__DATA__',json.dumps(data,ensure_ascii=False).replace('</','<\\/'))
    (folder/'review.html').write_text(content,encoding='utf-8')
    return {'review_page':str(folder/'review.html'),'model_count':len(models),'frame_count':len(frames),
            'models_with_warnings':[m['id'] for m in models.values() if any(not c['strict_passed'] for c in m['checks'])],
            'publication_ready':False}
