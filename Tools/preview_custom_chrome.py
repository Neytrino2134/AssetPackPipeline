"""Offline visual preview, no Unreal or paid API calls; closes after 5 minutes."""
import sys
from pathlib import Path
plugin=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(plugin/'Content/Python'))
from asset_pack_pipeline import custom_host
from asset_pack_pipeline.custom_snapshot import SnapshotAPI

class PreviewTransport:
    def call(self,method,*args,**kwargs):
        if method!='ui_snapshot':raise RuntimeError('Visual preview: commands disabled')
        return {'ready':{'active_run':None,'guided_running':False},'guided':None,'report':None}

def create_window():
    custom_host.SnapshotAPI=lambda config:SnapshotAPI(config,transport=PreviewTransport())
    saved=plugin.parents[1]/'Saved/ChromePreview/AssetPackPipeline'
    saved.mkdir(parents=True,exist_ok=True)
    return custom_host.CustomWindow({'saved':str(saved)})

if __name__=='__main__':
    window=create_window()
    window.root.after(300000,lambda:window.close(prompt=False))
    window.root.mainloop()
