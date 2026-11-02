"""Real external Tk settings lifecycle with a simulated release response."""
import json
import sys
from pathlib import Path
plugin=Path(__file__).resolve().parents[1];project=plugin.parents[1]
sys.path.insert(0,str(plugin/'Content/Python'))
from asset_pack_pipeline import update_host,updater
import tkinter as tk
folder=project/'Saved/UpdaterProcessSmoke'
context=json.loads((folder/'UnrealResult.json').read_text(encoding='utf-8'))['context']
updater.settings_path=lambda:folder/'UI-test-settings.json'
updater.checked=lambda *args:{'status':'available','message':'Доступно обновление 9.0.0',
    'repository':updater.REPOSITORY,'manifest':{'version':'9.0.0'}}
original=tk.Tk
def create(*args,**kwargs):
    root=original(*args,**kwargs)
    def finish():
        buttons=[w for frame in root.winfo_children() for w in frame.winfo_children() if isinstance(w,tk.Button)]
        install=next(w for w in buttons if 'установить' in w.cget('text'))
        result={'passed':install.cget('state')=='normal','buttons':len(buttons),'unreal_loaded':'unreal' in sys.modules,
                'simulated_release':True,'width':root.winfo_width(),'height':root.winfo_height()}
        (folder/'UIResult.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
        root.destroy()
    root.after(2500,finish)
    return root
tk.Tk=create
update_host.main(context)
