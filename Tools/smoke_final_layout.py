"""Repackage existing real delivery files in the new layout; never touch source."""
import argparse
import json
import shutil
import sys
from pathlib import Path
plugin=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(plugin/'Content/Python'))
from asset_pack_pipeline import delivery,final_output

parser=argparse.ArgumentParser()
parser.add_argument('--report',type=Path)
parser.add_argument('--renders',type=Path)
parser.add_argument('--output',type=Path,required=True)
parser.add_argument('--finish',action='store_true')
args=parser.parse_args()
args.output=args.output.resolve()
state=args.output/'smoke.json'
if args.finish:
    data=json.loads(state.read_text())
    verification=json.loads((args.output/'Verifier/verification.json').read_text())
    assert verification['passed'],verification
    report=data['report'];report['fresh_project_verification']='passed'
    data.update(result=delivery.package(report),verified_meshes=len(verification['assets']),passed=True)
    state.write_text(json.dumps(data,indent=2),encoding='utf-8')
else:
    report=json.loads(args.report.read_text(encoding='utf-8'))
    delivery.verify_files(report)
    name=Path(report['project_path']).stem
    root=final_output.export_root(args.output)
    project=root/(name+'_Project')
    for relative in report['file_hashes']:
        target=project/relative;target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(Path(report['project_directory'])/relative,target)
    report.update(project_directory=str(project),project_path=str(project/(name+'.uproject')),fresh_project_verification='pending')
    delivery.verify_files(report)
    render_report={'status':'passed','run_id':'layoutsmoke','output_directory':str(args.renders),
        'assets':[{'status':'passed','output_path':str(p)} for p in sorted(args.renders.rglob('*.png'))]}
    renders=final_output.export_renders([render_report],root,name)
    verifier=args.output/'Verifier';verifier.mkdir()
    (verifier/'spec.json').write_text(json.dumps(report['verification_spec']),encoding='utf-8')
    script=(plugin/'Content/Python/asset_pack_pipeline/delivery_verify.py').read_text(encoding='utf-8')
    (verifier/'verify_project.py').write_text(script+'\nu.SystemLibrary.quit_editor()\n',encoding='utf-8')
    state.write_text(json.dumps({'report':report,'renders':renders,'passed':False},indent=2),encoding='utf-8')
print(state)
