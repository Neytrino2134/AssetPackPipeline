"""Custom GUI client; intentionally has no Unreal dependency."""
import json
import time
import uuid
import os
from pathlib import Path
from . import custom_protocol as protocol

class RemoteAPI:
    def __init__(self,config):
        self.config=config
        self.root=Path(config['directory'])
        self.token=config['token']

    def call(self,method,*args,**kwargs):
        session=json.loads((self.root/'session.json').read_text())
        if session['session']!=self.config['session']:
            raise RuntimeError('Unreal перезапущен. Откройте Custom UI заново из меню Unreal.')
        request_id=uuid.uuid4().hex
        request=self.root/(request_id+'.request.json')
        response=self.root/(request_id+'.response.json')
        protocol.write(request,{'id':request_id,'session':self.config['session'],'created':time.time(),'method':method,'args':args,'kwargs':kwargs},self.token)
        deadline=time.monotonic()+120
        next_check=0
        while time.monotonic()<deadline:
            if os.name=='nt' and time.monotonic()>next_check and self.config.get('engine_pid'):
                next_check=time.monotonic()+1
                import ctypes
                kernel=ctypes.WinDLL('kernel32')
                kernel.OpenProcess.argtypes=[ctypes.c_uint32,ctypes.c_int,ctypes.c_uint32]
                kernel.OpenProcess.restype=ctypes.c_void_p
                kernel.CloseHandle.argtypes=[ctypes.c_void_p]
                handle=kernel.OpenProcess(0x1000,False,self.config['engine_pid'])
                if not handle:raise RuntimeError('Unreal закрыт. Откройте проект и Custom UI заново.')
                code=ctypes.c_uint32()
                kernel.GetExitCodeProcess.argtypes=[ctypes.c_void_p,ctypes.POINTER(ctypes.c_uint32)]
                kernel.GetExitCodeProcess(handle,ctypes.byref(code));kernel.CloseHandle(handle)
                if code.value!=259:raise RuntimeError('Unreal закрыт. Откройте проект и Custom UI заново.')
            if response.is_file():
                value=protocol.decode(response.read_text(encoding='utf-8'),self.token)
                response.unlink()
                if value.get('id')!=request_id: raise RuntimeError('IPC response mismatch')
                if not value['ok']: raise RuntimeError(value['error'])
                return value['result']
            if not (self.root/'session.json').is_file(): break
            time.sleep(.025)
        raise RuntimeError('Нет ответа Unreal. Операция могла начаться; проверьте очередь перед повторным запуском.')

    def __getattr__(self,name):
        if name.startswith('_'): raise AttributeError(name)
        return lambda *a,**k:self.call(name,*a,**k)
