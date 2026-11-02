"""Unreal editor-thread RPC server and isolated Custom UI launcher; no Tk imports."""
import json
import os
import secrets
import subprocess
import time
import uuid
from pathlib import Path
import unreal
from . import api, custom_protocol as protocol

METHODS=frozenset(('readiness','plan','start','status','list_runs','resume','cancel','start_settings',
 'validate','create_review_candidate','create_review_bundle','analyze_sources','start_diagnostics',
 'create_overview','open_overview','validate_overview','start_previews','start_media','start_flythrough',
 'open_flythrough','plan_cleanup','cleanup_staging','plan_delivery','create_delivery','create_combined_delivery',
 'start_delivery_verification','package_delivery','start_cook'))
READ_ONLY=frozenset(('readiness','status','list_runs','guided_status','content_folders','ui_snapshot'))
_handle=None
_token=''
_session=''
_process=None
_busy=False
_focus=0
_seen={}

def directory():
    path=Path(unreal.Paths.project_saved_dir()).resolve()/'AssetPackPipeline/CustomIPC'
    path.mkdir(parents=True,exist_ok=True)
    return path

def active_guided():
    from . import native_bridge
    return native_bridge._session if native_bridge._session and not native_bridge._session.done else None

def dispatch(method,args,kwargs):
    if method not in METHODS and method not in ('ui_snapshot','guided_status','cancel_guided','start_guided','content_folders','plan_imported_cleanup','execute_imported_cleanup'):
        raise ValueError('RPC command not permitted')
    from . import native_bridge
    if method=='ui_snapshot':
        ready=api.readiness()
        job=native_bridge._session
        ready.update(custom_focus=_focus,guided_running=bool(active_guided()))
        run=ready['active_run'] or (args[0] if args else None)
        report=api.status(run) if run else None
        return {'ready':ready,'guided':{'stage':job.label,'done':job.done,'error':job.error,'result':job.result} if job else None,'report':report}
    if method not in READ_ONLY and method not in ('cancel_guided','cancel') and active_guided():
        raise RuntimeError('Уже выполняется последовательность подготовки. Дождитесь её завершения.')
    if method=='readiness':
        result=api.readiness()
        result.update(custom_focus=_focus,guided_running=bool(active_guided()))
        return result
    if method=='guided_status':
        job=native_bridge._session
        return {'stage':job.label,'done':job.done,'error':job.error,'result':job.result} if job else None
    if method=='cancel_guided':
        job=active_guided()
        if job:job.cancel()
        run=api.readiness()['active_run']
        if run:api.cancel(run)
        return {'cancel_requested':True}
    if method=='start_guided':
        if api.readiness()['active_run']:raise RuntimeError('Unreal уже выполняет задачу.')
        paths,steps=args
        allowed={'import','settings','validate','overview','preview','media','delivery','verify_delivery','package','export_renders'}
        if not paths or any(k not in paths or op not in allowed for k,op in steps):raise ValueError('Invalid guided plan')
        from . import guided
        previous=native_bridge._session
        native_bridge._session=guided.Session(api,paths,steps)
        if previous and all(op in ('delivery','verify_delivery','package') for _,op in steps):
            from .discovery import read_json
            old={(read_json(p)['pack_id'],read_json(p)['destination_root']) for p in previous.paths.values()}
            new={(read_json(p)['pack_id'],read_json(p)['destination_root']) for p in paths.values()}
            if old==new:native_bridge._session.render_runs=list(previous.render_runs)
        native_bridge.ensure_tick()
        return {'started':True}
    if method=='content_folders':
        from collections import Counter
        return dict(Counter('/'.join(str(p).split('.')[0].split('/')[:3]) for p in unreal.EditorAssetLibrary.list_assets('/Game',recursive=True,include_folder=False) if len(str(p).split('/'))>3))
    if method in ('plan_imported_cleanup','execute_imported_cleanup'):
        from . import cleanup
        if api.readiness()['active_run']:raise RuntimeError('Задача выполняется.')
        manifest=args[0]
        if method=='plan_imported_cleanup':return cleanup.plan(manifest,imported=True,folder_scope=kwargs.get('folder_scope',False))
        backup=Path(args[1]).resolve()
        allowed=(Path(unreal.Paths.project_saved_dir()).resolve()/'AssetPackPipeline/ImportedCleanup').resolve()
        if not backup.is_relative_to(allowed):raise ValueError('Backup must stay under ImportedCleanup')
        return cleanup.execute(manifest,backup,imported=True,expected=kwargs.get('expected'),folder_scope=kwargs.get('folder_scope',False))
    if method not in METHODS:raise ValueError('RPC command not permitted')
    return getattr(api,method)(*args,**kwargs)

def serve(delta):
    global _busy,_handle
    if _busy:return
    _busy=True
    try:
        if _process is not None and _process.poll() is not None and not any(directory().glob('*.request.json')):
            if _handle is not None:unreal.unregister_slate_post_tick_callback(_handle)
            _handle=None
            return
        for path in list(directory().glob('*.request.json'))[:4]:
            try:
                if path.stat().st_size>protocol.MAX_BYTES:
                    path.unlink();continue
                request=protocol.decode(path.read_text(encoding='utf-8'),_token)
                path.unlink()
                if request['session']!=_session or not isinstance(request['id'],str) or len(request['id'])!=32:
                    continue
                uuid.UUID(hex=request['id'])
                now=time.time()
                for key in [key for key,stamp in _seen.items() if stamp<now-300]:_seen.pop(key,None)
                if abs(now-float(request['created']))>300:continue
                if request['id'] in _seen:
                    protocol.write(directory()/(request['id']+'.response.json'),{'id':request['id'],'ok':False,'error':'Команда уже обработана. Проверьте очередь.'},_token)
                    continue
                _seen[request['id']]=now
                try:
                    result=dispatch(request['method'],request['args'],request['kwargs'])
                    response={'id':request['id'],'ok':True,'result':result}
                except Exception as error:response={'id':request['id'],'ok':False,'error':str(error)}
                target=directory()/(request['id']+'.response.json')
                try:protocol.write(target,response,_token)
                except (TypeError,ValueError):protocol.write(target,{'id':request['id'],'ok':False,'error':'Ответ слишком большой или не сериализуется; откройте сохранённый отчёт.'},_token)
            except (ValueError,KeyError,TypeError,OSError):
                if path.exists():path.unlink()
    finally:_busy=False

def start():
    global _handle,_token,_session
    if _handle is None:
        _token=secrets.token_hex(32);_session=uuid.uuid4().hex
        (directory()/'session.json').write_text(json.dumps({'session':_session,'pid':os.getpid()}))
        _handle=unreal.register_slate_post_tick_callback(serve)
    return {'directory':str(directory()),'session':_session,'token':_token,'engine_pid':os.getpid(),
            'saved':str(Path(unreal.Paths.project_saved_dir()).resolve()/'AssetPackPipeline')}

def _activate(pid):
    """Bring the client's main window forward. Unreal holds the foreground when its
    menu is used, so it may hand focus over; the Tk process itself may not."""
    if os.name!='nt':return False
    import ctypes
    from ctypes import wintypes
    user=ctypes.WinDLL('user32')
    for name in ('IsWindowVisible','IsIconic','SetForegroundWindow'):getattr(user,name).argtypes=[wintypes.HWND]
    user.GetWindowThreadProcessId.argtypes=[wintypes.HWND,ctypes.POINTER(wintypes.DWORD)]
    user.GetWindowTextW.argtypes=[wintypes.HWND,wintypes.LPWSTR,ctypes.c_int]
    user.ShowWindow.argtypes=[wintypes.HWND,ctypes.c_int]
    found=[]
    def visit(hwnd,_):
        owner=wintypes.DWORD()
        user.GetWindowThreadProcessId(hwnd,ctypes.byref(owner))
        if owner.value==pid and (user.IsWindowVisible(hwnd) or user.IsIconic(hwnd)):
            text=ctypes.create_unicode_buffer(256);user.GetWindowTextW(hwnd,text,256)
            found.append((text.value!='MESHFLOW Asset Pack Pipeline',hwnd))
        return True
    user.EnumWindows(ctypes.WINFUNCTYPE(wintypes.BOOL,wintypes.HWND,wintypes.LPARAM)(visit),0)
    if not found:return False
    hwnd=min(found)[1]
    user.ShowWindow(hwnd,9 if user.IsIconic(hwnd) else 5) # SW_RESTORE / SW_SHOW
    user.SetForegroundWindow(hwnd)
    return True

def _close_orphan():
    """A client from an earlier editor session holds a dead token; close it."""
    marker=directory()/'client.pid'
    try:pid=int(marker.read_text())
    except (OSError,ValueError):return
    marker.unlink(missing_ok=True)
    if os.name!='nt' or pid==os.getpid():return
    import ctypes
    kernel=ctypes.WinDLL('kernel32')
    kernel.OpenProcess.restype=ctypes.c_void_p
    handle=kernel.OpenProcess(0x1001,False,pid) # TERMINATE | QUERY_LIMITED_INFORMATION
    if not handle:return
    try:
        name=ctypes.create_unicode_buffer(1024);size=ctypes.c_uint32(1024)
        kernel.QueryFullProcessImageNameW.argtypes=[ctypes.c_void_p,ctypes.c_uint32,ctypes.c_wchar_p,ctypes.POINTER(ctypes.c_uint32)]
        engine_python=Path(unreal.Paths.engine_dir()).resolve()/'Binaries/ThirdParty/Python3/Win64/python.exe'
        if kernel.QueryFullProcessImageNameW(handle,0,name,ctypes.byref(size)) and Path(name.value).resolve()==engine_python:
            kernel.TerminateProcess.argtypes=[ctypes.c_void_p,ctypes.c_uint32]
            kernel.TerminateProcess(handle,0)
    finally:
        kernel.CloseHandle.argtypes=[ctypes.c_void_p];kernel.CloseHandle(handle)

def launch(test_plan=None):
    global _process,_focus
    if _process is not None and _process.poll() is None:
        _focus+=1
        _activate(_process.pid)
        return {'already_open':True,'pid':_process.pid}
    _close_orphan()
    config=start()
    from . import updater
    config['update_context']=updater.engine_context()
    (directory()/'client-status.json').unlink(missing_ok=True)
    if test_plan:config['probe_plan']=test_plan
    python=Path(unreal.Paths.engine_dir()).resolve()/'Binaries/ThirdParty/Python3/Win64/python.exe'
    env=os.environ.copy()
    env['PYTHONPATH']=str(Path(__file__).resolve().parents[1])+os.pathsep+env.get('PYTHONPATH','')
    from . import ai_settings
    key=ai_settings.get_key()
    if key:env['OPENAI_API_KEY']=key
    log=directory()/'custom-ui.log'
    with log.open('ab') as stream:
        _process=subprocess.Popen([str(python),'-u','-m','asset_pack_pipeline.custom_host'],stdin=subprocess.PIPE,
            stdout=stream,stderr=stream,env=env,creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
    _process.stdin.write((json.dumps(config)+'\n').encode());_process.stdin.close()
    (directory()/'client.pid').write_text(str(_process.pid))
    return {'pid':_process.pid,'log':str(log)}
