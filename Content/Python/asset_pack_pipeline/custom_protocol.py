"""Signed local spool protocol. No sockets, executable payloads or credentials on disk."""
import hashlib
import hmac
import json
import uuid
from pathlib import Path

MAX_BYTES=16*1024*1024

def encode(value,token):
    data=json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'))
    return json.dumps({'data':data,'mac':hmac.new(token.encode(),data.encode(),hashlib.sha256).hexdigest()},ensure_ascii=False)

def decode(text,token):
    if len(text.encode())>MAX_BYTES: raise ValueError('IPC message too large')
    envelope=json.loads(text)
    data=envelope['data']
    expected=hmac.new(token.encode(),data.encode(),hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected,envelope['mac']): raise ValueError('IPC authentication failed')
    return json.loads(data)

def write(path,value,token):
    path=Path(path)
    temporary=path.with_name(path.name+'.'+uuid.uuid4().hex+'.tmp')
    text=encode(value,token)
    if len(text.encode())>MAX_BYTES:raise ValueError('IPC result too large; use saved reports')
    temporary.write_text(text,encoding='utf-8')
    temporary.replace(path)
