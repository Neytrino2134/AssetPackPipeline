"""Offline visual review of completed Unreal renders; never certifies publication."""
import html
import json
from pathlib import Path


def write(report):
    folder=Path(report['output_directory']).resolve()
    frames=[]
    for row in report['assets']:
        if row['status']!='passed':continue
        path=Path(row['output_path']).resolve()
        if path.parent!=folder or not path.is_file():raise ValueError('Review image must be inside output directory')
        frames.append({key:row.get(key) for key in ('asset_id','yaw','lod_index','representation','diagnostic','sha256','width','height')}
                      | {'file':path.name,'render_view':row.get('render_view','lit')})
    data={'run_id':report['run_id'],'status':report['status'],'frames':frames,'publication_ready':False}
    (folder/'review.json').write_text(json.dumps(data,indent=2),encoding='utf-8')
    cards=''.join('<figure><a target="_blank" href="'+html.escape(f['file'],quote=True)+'"><img loading="lazy" src="'+html.escape(f['file'],quote=True)+'"></a><figcaption>'+
                  html.escape(f['asset_id'])+' / '+('Nanite' if f['representation']=='Nanite' else 'LOD '+str(f['lod_index']))+' / '+str(f['yaw'])+'° / '+html.escape(f['render_view'])+
                  (' / DIAGNOSTIC' if f['diagnostic'] else '')+'</figcaption></figure>' for f in frames)
    content='''<!doctype html><meta charset="utf-8"><title>Asset Pack — visual review</title>
<style>body{margin:24px;background:#171a20;color:#e7e9ed;font:15px system-ui}select,button,textarea{background:#2b303a;color:inherit;border:1px solid #657080;padding:8px;margin:6px}label{display:inline-block}#stage{position:relative;max-width:1400px;aspect-ratio:16/9;background:#262d38}#stage img{position:absolute;width:100%;height:100%;object-fit:contain}#top{clip-path:inset(0 50% 0 0)}input{width:min(80vw,900px)}textarea{display:block;width:min(85vw,1200px);height:90px}main{display:grid;grid-template-columns:repeat(3,1fr);gap:12px}figure{margin:0}figure img{width:100%}figcaption{padding:5px}p{max-width:1100px}a{color:#8ec7ff}</style>
<h1>Asset Pack — visual review</h1><p>Same camera and lighting for every LOD. Check silhouette, shading, UV seams, normal details and low LOD readability. Slider reveals the chosen LOD over the reference. Machine checks do not approve appearance or publication.</p>
<label>Model <select id="asset"></select></label><label>View <select id="view"></select></label><label>Reference <select id="base"></select></label><label>Compare <select id="compare"></select></label><p id="caption"></p>
<div id="stage"><img id="bottom"><img id="top"></div><a id="fullbase" target="_blank">Reference PNG</a> · <a id="fullcompare" target="_blank">Compare PNG</a><br><label>Reveal comparison <input type="range" id="wipe" min="0" max="100" value="50"></label>
<label>Render <select id="render"></select></label>
<label>Decision <select id="decision"><option value="pending">Pending</option><option value="accept">Accept appearance</option><option value="revise">Needs revision</option></select></label><textarea id="notes" placeholder="Review notes for this model and view"></textarea><button id="export">Export review decisions JSON</button><p>Decisions stay in this browser until exported. Export is a local file; it does not update Unreal reports. Inspect automatic transitions in Unreal separately: these images use forced LOD.</p>
<h2>All completed frames</h2><main>__CARDS__</main>
<script>const data=__DATA__;
const $=id=>document.getElementById(id);let notes={};const storage='APP-review-'+data.run_id;try{notes=JSON.parse(localStorage.getItem(storage)||'{}')}catch(e){}
const unique=a=>[...new Set(a)];function options(id,values){$(id).replaceChildren(...values.map(v=>{let o=document.createElement('option');o.value=v;o.textContent=v;return o}))}
function key(){return $('asset').value+'/'+$('view').value+'/'+$('render').value}function save(){notes[key()]={decision:$('decision').value,notes:$('notes').value};try{localStorage.setItem(storage,JSON.stringify(notes))}catch(e){}}
function rows(){return data.frames.filter(f=>f.asset_id===$('asset').value&&String(f.yaw)===$('view').value&&f.render_view===$('render').value)}
function images(){let a=rows().find(f=>String(f.lod_index)===$('base').value),b=rows().find(f=>String(f.lod_index)===$('compare').value);if(!a||!b)return;$('bottom').src=a.file;$('top').src=b.file;$('fullbase').href=a.file;$('fullcompare').href=b.file;$('stage').style.aspectRatio=a.width+'/'+a.height;$('stage').style.width=`min(100%,${58*a.width/a.height}vh)`;$('caption').textContent=`${a.asset_id} / ${a.yaw}° / reference LOD${a.lod_index} / compare LOD${b.lod_index}`+(a.diagnostic?' / DIAGNOSTIC':'')}
function lods(){options('base',rows().map(f=>f.lod_index));options('compare',rows().map(f=>f.lod_index));$('compare').selectedIndex=Math.max(0,$('compare').options.length-1);const n=notes[key()]||{};$('decision').value=n.decision||'pending';$('notes').value=n.notes||'';images()}
function renderModes(){options('render',unique(data.frames.filter(f=>f.asset_id===$('asset').value&&String(f.yaw)===$('view').value).map(f=>f.render_view)));lods()}
function views(){options('view',unique(data.frames.filter(f=>f.asset_id===$('asset').value).map(f=>f.yaw)));renderModes()}
options('asset',unique(data.frames.map(f=>f.asset_id)));$('asset').onchange=views;$('view').onchange=renderModes;$('render').onchange=lods;$('base').onchange=images;$('compare').onchange=images;$('wipe').oninput=()=>$('top').style.clipPath=`inset(0 ${100-$('wipe').value}% 0 0)`;$('decision').onchange=save;$('notes').oninput=save;
$('export').onclick=()=>{save();let a=document.createElement('a');a.href=URL.createObjectURL(new Blob([JSON.stringify({run_id:data.run_id,reviewed_at:new Date().toISOString(),decisions:notes,publication_ready:false},null,2)],{type:'application/json'}));a.download='review-decisions-'+data.run_id+'.json';a.click();setTimeout(()=>URL.revokeObjectURL(a.href),1000)};views();</script>'''
    content=content.replace('__CARDS__',cards).replace('__DATA__',json.dumps(data).replace('</','<\\/'))
    path=folder/'review.html';path.write_text(content,encoding='utf-8')
    return str(path)
