"""Standalone post-editor installer. Standard library only; copied outside plugin."""
import ctypes
import hashlib
import json
import os
import re
import shutil
import stat
import sys
import time
import uuid
from pathlib import Path, PurePosixPath
from zipfile import ZipFile

def version(value):
    if not re.fullmatch(r'v?\d+\.\d+\.\d+',value):raise ValueError('Invalid stable version')
    return tuple(map(int,value.lstrip('v').split('.')))

def write_json(path,data):
    path=Path(path);temporary=path.with_name(path.name+'.'+uuid.uuid4().hex+'.tmp')
    temporary.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
    os.replace(temporary,path)

def validate_target(target):
    target=Path(target)
    if target.name!='AssetPackPipeline' or target.parent.name!='Plugins' or target.is_symlink():
        raise ValueError('Only a project Plugins/AssetPackPipeline installation can be updated')
    if not any(target.parent.parent.glob('*.uproject')):
        raise ValueError('Install updates in a project Plugins folder, not the Engine plugins directory')
    if (target/'.git').exists():raise ValueError('Рабочая копия Git: используйте GitHub Desktop / Pull origin.')
    if not (target/'AssetPackPipeline.uplugin').is_file():raise ValueError('Plugin descriptor missing')
    return target

def unpack(archive,folder,manifest):
    archive=Path(archive);folder=Path(folder)
    if hashlib.sha256(archive.read_bytes()).hexdigest()!=manifest['sha256']:raise ValueError('Update SHA256 mismatch')
    with ZipFile(archive) as stream:
        entries=stream.infolist();seen=set()
        if len(entries)>20000 or sum(i.file_size for i in entries)>2*1024**3:raise ValueError('Update archive too large')
        for item in entries:
            path=PurePosixPath(item.filename)
            if (not path.parts or path.parts[0]!='AssetPackPipeline' or path.is_absolute()
                or '\\' in item.filename or any(p.casefold() in ('.','..','.git','saved','intermediate') or any(c in p for c in ':<>"|?*') or p.endswith((' ','.'))
                    or p.split('.')[0].upper() in ('CON','PRN','AUX','NUL',*[f'COM{i}' for i in range(1,10)],*[f'LPT{i}' for i in range(1,10)]) for p in path.parts)
                or any(p.casefold().startswith('.env') for p in path.parts) or stat.S_ISLNK(item.external_attr>>16)):
                raise ValueError('Unsafe update archive entry: '+item.filename)
            key=path.as_posix().casefold()
            if key in seen:raise ValueError('Duplicate update archive entry')
            seen.add(key)
        descriptor=json.loads(stream.read('AssetPackPipeline/AssetPackPipeline.uplugin').decode('utf-8-sig'))
        if version(descriptor['VersionName'])!=version(manifest['version']):raise ValueError('Descriptor version mismatch')
        modules=json.loads(stream.read('AssetPackPipeline/Binaries/Win64/UnrealEditor.modules'))
        if modules['BuildId']!=manifest['build_id']:raise ValueError('Binary BuildId mismatch')
        dll=modules['Modules']['AssetPackPipelineEditor']
        if Path(dll).name!=dll or not dll.endswith('.dll'):raise ValueError('Invalid module filename')
        if 'AssetPackPipeline/Binaries/Win64/'+dll not in stream.namelist():raise ValueError('Compiled editor module missing')
        stream.extractall(folder)
    return folder/'AssetPackPipeline'

def install(job):
    target=validate_target(job['target']).resolve()
    root=Path(job['directory']).resolve()
    allowed=target.parent.parent/'Saved/AssetPackPipeline/Updates/jobs'
    if not root.is_relative_to(allowed) or root==allowed:raise ValueError('Invalid update job location')
    if version(job['manifest']['version'])<=version(json.loads((target/'AssetPackPipeline.uplugin').read_text(encoding='utf-8-sig'))['VersionName']):
        raise ValueError('Installed version is already current or newer')
    payload=root/'payload'
    if payload.exists():raise ValueError('Update payload already exists; prepare a new update')
    staged=unpack(root/'update.zip',payload,job['manifest'])
    backup=root/'backup'
    if backup.exists():raise ValueError('Backup already exists')
    target.rename(backup)
    try:staged.rename(target)
    except BaseException:
        backup.rename(target)
        raise
    return {'status':'installed','version':job['manifest']['version'],'backup':str(backup),
            'message':'Обновление установлено. Можно открыть проект Unreal.'}

def wait_for_editor(pid,timeout=7200):
    if os.name!='nt':raise RuntimeError('Post-exit installation currently supports Windows only')
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.OpenProcess.argtypes=[ctypes.c_uint32,ctypes.c_int,ctypes.c_uint32];kernel.OpenProcess.restype=ctypes.c_void_p
    handle=kernel.OpenProcess(0x100000,False,int(pid))
    if not handle:
        if ctypes.get_last_error()==87:return
        raise OSError(ctypes.get_last_error(),'Cannot watch Unreal process')
    kernel.WaitForSingleObject.argtypes=[ctypes.c_void_p,ctypes.c_uint32]
    kernel.CloseHandle.argtypes=[ctypes.c_void_p]
    try:
        if kernel.WaitForSingleObject(handle,int(timeout*1000))!=0:raise TimeoutError('Editor did not close within 2 hours')
    finally:kernel.CloseHandle(handle)

def main(job_path):
    job_path=Path(job_path).resolve();job=json.loads(job_path.read_text(encoding='utf-8'))
    if Path(job['directory']).resolve()!=job_path.parent:raise ValueError('Job path mismatch')
    result_path=job_path.parent/'result.json'
    try:
        validate_target(job['target'])
        write_json(result_path,{'status':'waiting','message':'Обновление готово. Закройте Unreal; дождитесь завершения установки перед запуском проекта.'})
        wait_for_editor(job['engine_pid'])
        write_json(result_path,install(job))
    except Exception as error:
        write_json(result_path,{'status':'failed','message':str(error)})

if __name__=='__main__':main(sys.argv[1])
