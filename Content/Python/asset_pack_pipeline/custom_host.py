"""Standalone desktop mainloop. This process never imports unreal."""
import json
import os
import sys
import uuid
from pathlib import Path
from .custom_client import RemoteAPI
from .window import PipelineWindow


class CustomWindow(PipelineWindow):
    def __init__(self,config):
        self.config=config
        self.focus_serial=0
        super().__init__(parent_to_unreal=False,pump=False,api_adapter=RemoteAPI(config),saved_directory=config['saved'])
        self.root.title('Asset Pack Pipeline · Custom UI · '+Path(config['saved']).parents[1].name)
        self.root.after(250,self.external_poll)

    def external_poll(self):
        if self.closed:return
        try:
            self.ai_settings_poll();self.ai_poll()
            self._poll()
            remote=self.api.guided_status()
            if remote:self.state_label.configure(text=remote['stage'])
            ready=self.api.readiness()
            serial=ready.get('custom_focus',0)
            if serial!=self.focus_serial:
                self.focus_serial=serial;self.root.deiconify();self.root.lift()
        except Exception as error:
            self.state_label.configure(text=str(error))
        if not self.closed:self.root.after(750,self.external_poll)

    def open_reports(self):
        folder=self.report_path.parent if self.report_path else self.saved/'Runs'
        folder.mkdir(parents=True,exist_ok=True)
        os.startfile(str(folder))

    def guide_run(self,start,raise_errors=False):
        try:
            ready=self.api.readiness()
            if ready['active_run'] or ready.get('guided_running'):raise RuntimeError('Дождитесь текущей задачи.')
            profiles,steps=self.guide_plan()
            folder=self.saved/'UI'/'Custom'/uuid.uuid4().hex
            folder.mkdir(parents=True)
            paths={}
            for variant,profile in profiles.items():
                path=folder/(variant+'.json')
                path.write_text(json.dumps(profile,ensure_ascii=False,indent=2),encoding='utf-8')
                paths[variant]=str(path)
                plan=self.api.plan(str(path))
                if not plan['ready']:raise RuntimeError(str(plan['conflicts']))
                self._log(f"{variant}: {len(plan['assets'])} моделей")
            if start:self.api.start_guided(paths,steps)
            return {'status':'started' if start else 'sources_checked','completed':False}
        except Exception as error:
            self._callback_error(type(error),error,error.__traceback__)
            if raise_errors:raise

    def final_only(self):
        try:
            if self.mode.get()=='Профессиональный':
                paths={'Profile':self._snapshot()}
                companion=self.variables['combined_profile_path'].get().strip()
                if companion:paths['Companion']=companion
            else:
                profiles,_=self.guide_plan()
                folder=self.saved/'UI'/'CustomFinal'/uuid.uuid4().hex
                folder.mkdir(parents=True)
                paths={}
                for name,profile in profiles.items():
                    path=folder/(name+'.json');path.write_text(json.dumps(profile,ensure_ascii=False,indent=2),encoding='utf-8');paths[name]=str(path)
            first=next(iter(paths))
            self.api.start_guided(paths,[(first,op) for op in ('delivery','verify_delivery','package')])
        except Exception as error:self._callback_error(type(error),error,error.__traceback__)

    def cancel(self):
        self.ai_cancel()
        self.api.cancel_guided()
        self.state_label.configure(text='Запрошена остановка после текущей операции…')


def main():
    config=json.loads(sys.stdin.readline(65536))
    assert 'unreal' not in sys.modules,'Custom UI must run outside Unreal'
    window=CustomWindow(config)
    readiness=window.api.readiness()
    probe_started=False
    if config.get('probe_plan'):
        plan=config['probe_plan']
        window.api.start_guided(plan['paths'],plan['steps'])
        probe_started=True
    marker=Path(config['directory'])/'client-status.json'
    marker.write_text(json.dumps({'pid':os.getpid(),'tkinter_loaded':'tkinter' in sys.modules,'unreal_loaded':'unreal' in sys.modules,'rpc_connected':bool(readiness.get('engine_version')),'probe_started':probe_started}),encoding='utf-8')
    window.root.mainloop()

if __name__=='__main__':main()
