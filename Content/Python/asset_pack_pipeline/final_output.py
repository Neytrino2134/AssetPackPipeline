"""Copy only completed PNG outputs, alongside the separately verified UE ZIP."""
import hashlib
import json
import shutil
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED


def export_renders(reports, destination):
    files = []
    for report in reports:
        if report['status'] != 'passed':
            raise ValueError('Render run did not pass')
        root = Path(report['output_directory']).resolve()
        run = report['run_id']
        if not run.isalnum():
            raise ValueError('Invalid render run ID')
        for asset in report['assets']:
            path = Path(asset['output_path']).resolve()
            if asset['status'] != 'passed' or path.suffix.lower() != '.png' or not path.is_relative_to(root) or not path.is_file():
                raise ValueError('Missing, incomplete or unexpected render output')
            files.append((run+'/'+path.name, path))
    if not files:
        return {'count': 0, 'status': 'not_requested'}
    folder = Path(destination)/'Renders'
    folder.mkdir(exist_ok=False)
    hashes = {}
    for relative, source in files:
        target = folder/relative
        target.parent.mkdir(exist_ok=True)
        shutil.copy2(source, target)
        hashes[relative] = hashlib.sha256(target.read_bytes()).hexdigest()
    (folder/'manifest.json').write_text(json.dumps(hashes, indent=2), encoding='utf-8')
    archive = folder.with_suffix('.zip')
    with ZipFile(archive, 'x', ZIP_DEFLATED) as stream:
        for file in sorted(folder.rglob('*')):
            if file.is_file():
                stream.write(file, 'Renders/'+file.relative_to(folder).as_posix())
    with ZipFile(archive) as stream:
        if stream.testzip():
            raise RuntimeError('Render ZIP failed integrity check')
    return {'count':len(files), 'directory':str(folder), 'zip_path':str(archive)}
