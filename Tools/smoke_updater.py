"""Install real local release archives after a disposable process exits."""
import json
import shutil
import subprocess
import sys
import time
import uuid
from pathlib import Path
from zipfile import ZipFile
plugin=Path(__file__).resolve().parents[1];project=plugin.parents[1]
sys.path.insert(0,str(plugin/'Content/Python'))
from asset_pack_pipeline import update_installer as installer
root=project/'Saved/UpdaterProcessSmoke'/uuid.uuid4().hex
host=root/'HostProject';target=host/'Plugins/AssetPackPipeline'
target.parent.mkdir(parents=True)
(host/'HostProject.uproject').write_text('{}')
with ZipFile(project/'Releases/AssetPackPipeline-0.25.3.zip') as archive:archive.extractall(target.parent)
(host/'Content').mkdir();(host/'Content/UserData.txt').write_text('untouched')
job_root=host/'Saved/AssetPackPipeline/Updates/jobs/smoke';job_root.mkdir(parents=True)
metadata=json.loads((project/'Releases/AssetPackPipeline-update.json').read_text())
shutil.copy2(project/'Releases'/metadata['archive'],job_root/'update.zip')
helper=job_root/'install_update.py';shutil.copy2(plugin/'Content/Python/asset_pack_pipeline/update_installer.py',helper)
editor=subprocess.Popen([sys.executable,'-c','import time; time.sleep(3)'],creationflags=subprocess.CREATE_NO_WINDOW)
job={'target':str(target),'directory':str(job_root),'manifest':metadata,'engine_pid':editor.pid}
installer.write_json(job_root/'job.json',job)
process=subprocess.Popen([sys.executable,str(helper),str(job_root/'job.json')],creationflags=subprocess.CREATE_NO_WINDOW)
deadline=time.monotonic()+2
while not (job_root/'result.json').is_file() and time.monotonic()<deadline:time.sleep(.02)
assert json.loads((job_root/'result.json').read_text(encoding='utf-8'))['status']=='waiting'
assert json.loads((target/'AssetPackPipeline.uplugin').read_text())['VersionName']=='0.25.3'
editor.wait(timeout=10);process.wait(timeout=30)
result=json.loads((job_root/'result.json').read_text(encoding='utf-8'))
assert result['status']=='installed',result
assert json.loads((target/'AssetPackPipeline.uplugin').read_text())['VersionName']==metadata['version']
assert json.loads((Path(result['backup'])/'AssetPackPipeline.uplugin').read_text())['VersionName']=='0.25.3'
assert (host/'Content/UserData.txt').read_text()=='untouched'
result.update(passed=True,waited_for_process_exit=True,real_package=True,simulated_editor_process=True,project_content_untouched=True)
(project/'Saved/UpdaterProcessSmoke/result.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
print(json.dumps(result,indent=2))
