"""Single background status request; Tk reads only an in-memory snapshot."""
import threading
import time
from .custom_client import RemoteAPI

class SnapshotAPI:
    def __init__(self,config,transport=None):
        self.remote=transport or RemoteAPI(config)
        self.lock=threading.Lock()
        self.stop_event=threading.Event()
        self.data={'ready':{'active_run':None,'guided_running':False},'guided':None,'report':None,'connected':False}
        self.watched=None
        self.requests=0

    def start(self):
        self.worker=threading.Thread(target=self._work,daemon=True)
        self.worker.start()

    def close(self):self.stop_event.set()

    def watch(self,run):
        with self.lock:self.watched=run

    def snapshot(self):
        with self.lock:return self.data

    def _work(self):
        while not self.stop_event.is_set():
            with self.lock:run=self.watched
            try:
                started=time.monotonic()
                value=self.remote.call('ui_snapshot',run)
                value.update(connected=True,request_seconds=time.monotonic()-started)
                self.requests+=1
            except Exception as error:
                with self.lock:value=dict(self.data)
                value.update(connected=False,error=str(error))
            with self.lock:self.data=value
            ready=value.get('ready',{})
            active=bool(ready.get('active_run') or ready.get('guided_running'))
            if self.stop_event.wait(.5 if active else 2):break

    def readiness(self):return self.snapshot()['ready']
    def guided_status(self):return self.snapshot().get('guided')
    def status(self,run):
        report=self.snapshot().get('report')
        if report and report.get('run_id')==run:return report
        return self.remote.call('status',run)

    def __getattr__(self,name):
        if name.startswith('_'):raise AttributeError(name)
        return getattr(self.remote,name)
