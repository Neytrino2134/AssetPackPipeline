"""Standalone desktop mainloop. This process never imports unreal."""
import json
import os
import sys
import uuid
import time
from pathlib import Path
from .custom_snapshot import SnapshotAPI
from .window import PipelineWindow


class CustomWindow(PipelineWindow):
    def __init__(self,config):
        self.config=config
        self.focus_serial=0
        self.started=time.monotonic()
        self.heartbeat_last=self.started
        self.heartbeat_gaps=[]
        super().__init__(parent_to_unreal=False,pump=False,api_adapter=SnapshotAPI(config),saved_directory=config['saved'])
        self.widget_seconds=time.monotonic()-self.started
        self.root.title('Asset Pack Pipeline · Custom UI · '+Path(config['saved']).parents[1].name)
        self.state_label.configure(text='Окно готово. Подключение к Unreal…')
        self.api.start()
        self.root.after(50,self.external_poll)
        self.root.after(20,self.heartbeat)

    def heartbeat(self):
        if self.closed:return
        now=time.monotonic()
        self.heartbeat_gaps.append(now-self.heartbeat_last)
        self.heartbeat_last=now
        del self.heartbeat_gaps[:-3000]
        self.root.after(20,self.heartbeat)

    def _poll(self,force=False):
        snapshot=self.api.snapshot()
        if snapshot is getattr(self,'_applied_snapshot',None) and not force:return
        self._applied_snapshot=snapshot
        ready=snapshot['ready']
        self._buttons(not snapshot['connected'] or bool(ready.get('active_run') or ready.get('guided_running')))
        if ready.get('active_run'):self.run_id=ready['active_run']
        self.api.watch(self.run_id)
        report=snapshot.get('report')
        if snapshot['connected'] and report and report.get('run_id')==self.run_id:
            self._display_report(report)

    def _buttons(self,running):
        if running==getattr(self,'_button_state',None):return
        self._button_state=running
        super()._buttons(running)

    def external_poll(self):
        if self.closed:return
        try:
            self.ai_settings_poll();self.ai_poll()
            snapshot=self.api.snapshot()
            self._poll()
            remote=snapshot.get('guided')
            ready=snapshot['ready']
            label=(snapshot.get('error','Подключение к Unreal…') if not snapshot['connected'] else
                   remote['stage'] if remote else 'Готово к настройке' if not self.run_id else None)
            if label and label!=getattr(self,'_status_text',None):
                self.state_label.configure(text=label);self._status_text=label
            serial=ready.get('custom_focus',0)
            if serial!=self.focus_serial:
                self.focus_serial=serial;self.root.deiconify();self.root.lift()
        except Exception as error:
            self.state_label.configure(text=str(error))
        if not self.closed:self.root.after(100,self.external_poll)

    def close(self,prompt=True):
        super().close(prompt)
        if self.closed:self.api.close()

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
    marker=Path(config['directory'])/'client-status.json'
    probe_started=False
    def connected():
        nonlocal probe_started
        if window.closed:return
        snapshot=window.api.snapshot()
        if snapshot['connected']:
            if config.get('probe_plan') and not probe_started:
                plan=config['probe_plan'];window.api.start_guided(plan['paths'],plan['steps']);probe_started=True
            gaps=sorted(window.heartbeat_gaps)
            marker.write_text(json.dumps({'pid':os.getpid(),'tkinter_loaded':'tkinter' in sys.modules,'unreal_loaded':'unreal' in sys.modules,
                'rpc_connected':True,'probe_started':probe_started,'widget_seconds':window.widget_seconds,
                'elapsed_seconds':time.monotonic()-window.started,'heartbeat_samples':len(gaps),
                'heartbeat_p95_seconds':gaps[int(.95*(len(gaps)-1))] if gaps else None,
                'heartbeat_max_after_start_seconds':max(window.heartbeat_gaps[1:],default=0),
                'rpc_seconds':snapshot.get('request_seconds'),
                'rpc_requests':window.api.requests}),encoding='utf-8')
        window.root.after(500,connected)
    window.root.after(100,connected)
    window.root.mainloop()

if __name__=='__main__':main()
