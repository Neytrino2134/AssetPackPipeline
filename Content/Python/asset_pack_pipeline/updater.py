"""Git-free GitHub Release updates. Network work runs outside the UI thread."""
import hashlib
import json
import os
import re
import shutil
import subprocess
import threading
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from . import __version__
from .update_installer import version,write_json,unpack,validate_target

REPOSITORY='Neytrino2134/AssetPackPipeline'
MANIFEST='AssetPackPipeline-update.json'
_started=False

def plugin_root():return Path(__file__).resolve().parents[3]

def settings_path():return Path(os.environ.get('LOCALAPPDATA',str(Path.home())))/'AssetPackPipeline/update-settings.json'

def settings():
    try:value=json.loads(settings_path().read_text(encoding='utf-8'))
    except (OSError,ValueError):value={}
    return {'repository':value.get('repository',REPOSITORY),'auto_check':bool(value.get('auto_check',True))}

def save_settings(repository,auto_check):
    validate_repository(repository)
    path=settings_path();path.parent.mkdir(parents=True,exist_ok=True)
    write_json(path,{'repository':repository,'auto_check':bool(auto_check)})

def validate_repository(repo):
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*/[A-Za-z0-9][A-Za-z0-9_.-]*',repo):raise ValueError('Repository must be owner/name')

def release_url(url,repo):
    if not url.startswith('https://github.com/'+repo+'/releases/download/'):
        raise ValueError('Download must belong to the configured GitHub repository')
    return url

def read_url(url,limit=1024*1024):
    request=urllib.request.Request(url,headers={'User-Agent':'MESHFLOW-AssetPackPipeline/'+__version__,'Accept':'application/vnd.github+json'})
    with urllib.request.urlopen(request,timeout=20) as response:
        if not response.geturl().startswith('https://'):raise ValueError('HTTPS is required')
        data=response.read(limit+1)
    if len(data)>limit:raise ValueError('Server response too large')
    return data

def check(context,repo=None):
    repo=repo or settings()['repository'];validate_repository(repo)
    try:release=json.loads(read_url('https://api.github.com/repos/'+repo+'/releases/latest'))
    except urllib.error.HTTPError as error:
        if error.code==404:return {'status':'no_release','message':'Опубликованных Releases пока нет. Исходный код на GitHub не является установочным обновлением.'}
        raise
    remote=release['tag_name'].lstrip('v');version(remote)
    if release.get('draft') or release.get('prerelease'):raise ValueError('Only published stable releases are supported')
    if version(remote)<=version(__version__):return {'status':'current','message':'Установлена актуальная версия '+__version__}
    assets={a['name']:a for a in release.get('assets',[])}
    if MANIFEST not in assets:return {'status':'unavailable','message':'Версия '+remote+' опубликована без манифеста установочного обновления.'}
    metadata=json.loads(read_url(release_url(assets[MANIFEST]['browser_download_url'],repo),65536))
    if metadata.get('schema_version')!=1 or version(metadata['version'])!=version(remote):raise ValueError('Invalid update manifest version')
    if metadata.get('platform')!='Win64' or metadata.get('engine_version')!=context['engine_version'] or metadata.get('build_id')!=context['build_id']:
        return {'status':'incompatible','message':'Доступна '+remote+', но требуется другая сборка Unreal. Обновление не устанавливается.'}
    if not re.fullmatch('[a-f0-9]{64}',metadata.get('sha256','')):raise ValueError('Update hash missing')
    asset=assets.get(metadata['archive'])
    if not asset or not 0<asset['size']<=512*1024**2:raise ValueError('Invalid update archive asset')
    return {'status':'available','message':'Доступно обновление '+__version__+' → '+remote,
            'manifest':metadata,'url':release_url(asset['browser_download_url'],repo),'size':asset['size'],'repository':repo}

def cache_path(context):return Path(context['saved'])/'Updates/status.json'

def cached(context):
    try:return json.loads(cache_path(context).read_text(encoding='utf-8'))
    except (OSError,ValueError):return {}

def checked(context,repo=None):
    try:result=check(context,repo)
    except Exception as error:result={'status':'error','message':str(error)}
    path=cache_path(context);path.parent.mkdir(parents=True,exist_ok=True)
    write_json(path,result)
    return result

def prepare(context,release):
    target=validate_target(context['target']).resolve()
    # Fetch a fresh manifest instead of trusting a stale editable cache/UI value.
    fresh=check(context,release['repository'])
    if fresh['status']!='available' or fresh['manifest']!=release['manifest']:raise ValueError('Release changed; check updates again')
    root=target.parent.parent/'Saved/AssetPackPipeline/Updates/jobs'/uuid.uuid4().hex
    root.mkdir(parents=True)
    archive=root/'update.zip'
    request=urllib.request.Request(fresh['url'],headers={'User-Agent':'MESHFLOW-AssetPackPipeline/'+__version__})
    total=0
    with urllib.request.urlopen(request,timeout=30) as response,archive.open('xb') as stream:
        if not response.geturl().startswith('https://'):raise ValueError('HTTPS is required')
        while True:
            chunk=response.read(1024*1024)
            if not chunk:break
            total+=len(chunk)
            if total>fresh['size']:raise ValueError('Download exceeds declared size')
            stream.write(chunk)
    if total!=fresh['size']:raise ValueError('Incomplete download')
    # Validate the entire package before asking the user to close Unreal.
    unpack(archive,root/'validation',fresh['manifest'])
    helper=root/'install_update.py';shutil.copyfile(Path(__file__).with_name('update_installer.py'),helper)
    job={'directory':str(root),'target':str(target),'engine_pid':context['engine_pid'],'manifest':fresh['manifest']}
    write_json(root/'job.json',job)
    flags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0
    subprocess.Popen([context['python'],str(helper),str(root/'job.json')],stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,creationflags=flags)
    return {'directory':str(root),'message':'Скачано и проверено. Закройте Unreal. Дождитесь установки, затем откройте проект.'}

def engine_context():
    import unreal
    engine=Path(unreal.Paths.engine_dir()).resolve()
    modules=json.loads((engine/'Binaries/Win64/UnrealEditor.modules').read_text(encoding='utf-8-sig'))
    return {'target':str(plugin_root()),'saved':str(Path(unreal.Paths.project_saved_dir()).resolve()/'AssetPackPipeline'),
            'python':str(engine/'Binaries/ThirdParty/Python3/Win64/python.exe'),'engine_pid':os.getpid(),
            'engine_version':unreal.SystemLibrary.get_engine_version().split('-')[0],'build_id':modules['BuildId']}

def launch(context=None):
    context=context or engine_context()
    env=os.environ.copy();env['PYTHONPATH']=str(Path(__file__).resolve().parents[1])
    process=subprocess.Popen([context['python'],'-m','asset_pack_pipeline.update_host'],stdin=subprocess.PIPE,env=env,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
    process.stdin.write((json.dumps(context)+'\n').encode());process.stdin.close()

def startup():
    global _started
    if _started:return
    _started=True
    if settings()['auto_check']:
        context=engine_context()
        done=threading.Event()
        def work():
            try:checked(context)
            finally:done.set()
        threading.Thread(target=work,daemon=True).start()
        import unreal
        def poll(delta):
            if not done.is_set():return
            unreal.unregister_slate_post_tick_callback(handle)
            result=cached(context)
            if result.get('status')=='available':
                unreal.log_warning('MESHFLOW: '+result['message']+' · Инструменты → Asset Pack Pipeline → Обновления')
                from . import ui
                ui.register()
        handle=unreal.register_slate_post_tick_callback(poll)
