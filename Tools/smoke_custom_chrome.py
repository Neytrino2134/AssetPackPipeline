"""Real Tk title bar lifecycle, no injected desktop input or Unreal content."""
import json
import traceback
from preview_custom_chrome import create_window
window=create_window()
root=window.root
result={'passed':False,'steps':[]}
output=window.saved/'ChromeSmoke.json'

def record(expected):
    assert root.state()==expected,(root.state(),expected)
    ctypes,w,user,hwnd=window.chrome._windows()
    user.GetWindowLongW.argtypes=[w.HWND,ctypes.c_int];user.GetWindowLongW.restype=ctypes.c_long
    style=user.GetWindowLongW(hwnd,-16)
    assert not style & 0x00c00000,'Native caption returned'
    assert style & 0x00040000,'Lost native resize frame'
    assert style & 0x00080000,'Lost system menu'
    from asset_pack_pipeline.custom_chrome import TITLE
    assert root.title()==TITLE
    from asset_pack_pipeline.custom_chrome import HEIGHT
    assert window.chrome.bar.winfo_height()==HEIGHT
    result['steps'].append({'state':expected,'style':hex(style),'title':root.title()})

def finish():
    output.write_text(json.dumps(result,indent=2),encoding='utf-8')
    window.close(prompt=False)

def advance(index=0):
    try:
        expected=['normal','zoomed','normal','iconic','normal'][index]
        record(expected)
        if index==4:
            result['passed']=True;finish();return
        [window.chrome.toggle_maximize,window.chrome.toggle_maximize,
         window.chrome.minimize,root.deiconify][index]()
        root.after(250,lambda:advance(index+1))
    except Exception:
        result['error']=traceback.format_exc();finish()
root.after(300,advance)
root.mainloop()
print(output)
if not result['passed']:raise RuntimeError(result['error'])
