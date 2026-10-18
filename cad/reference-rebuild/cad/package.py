#!/usr/bin/env python3
"""Package only this reference reconstruction; never legacy CAD or private data."""
from pathlib import Path
import csv, hashlib, json, zipfile
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'exports'
validation=json.loads((OUT/'validation.json').read_text())
meshes=json.loads((OUT/'mesh-validation.json').read_text())
assert validation['all_brep_valid'] and not validation['collisions'] and not validation['errors']
assert meshes['all_mesh_checks_pass'] and meshes['step_roundtrip']['passed']
inv=json.loads((OUT/'inventory.json').read_text())
assert len(inv['parts'])==validation['part_instances']==meshes['count']
assert len(list((OUT/'parts').glob('*.stl')))==len(inv['parts'])
with (ROOT/'bom.csv').open('w',newline='') as f:
    w=csv.writer(f);w.writerow(['component_instance','quantity','category','notes'])
    for p in inv['parts']:
        w.writerow([p['name'],1,'visual CAD component; NOT purchase BOM',p['note']])
# Bound the archive to known clean project paths. No refs to servers, keys or legacy meshes.
files=[]
for folder in ['cad','exports','images','references']:
    for p in (ROOT/folder).rglob('*'):
        if p.is_file() and '__pycache__' not in p.parts and p.suffix not in ['.pyc']:
            files.append(p)
for name in ['README.md','DESIGN-NOTES.md','PRINTING.md','requirements.txt','bom.csv']:
    files.append(ROOT/name)
files=sorted(set(files))
manifest={str(p.relative_to(ROOT)):dict(bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in files}
(ROOT/'MANIFEST.json').write_text(json.dumps(manifest,indent=2))
files.append(ROOT/'MANIFEST.json')
archive=ROOT.parent/'AVA-purple-reference-rebuild.zip'
with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
    for p in files:z.write(p,'AVA-reference-rebuild/'+str(p.relative_to(ROOT)))
with zipfile.ZipFile(archive) as z:
    assert z.testzip() is None
    assert len(z.namelist())==len(files)
    for name,entry in manifest.items():
        data=z.read('AVA-reference-rebuild/'+name)
        assert hashlib.sha256(data).hexdigest()==entry['sha256']
print(json.dumps(dict(archive=str(archive),archive_bytes=archive.stat().st_size,files=len(files),
                     component_instances=len(inv['parts']),mesh_checks='PASS',
                     brep_clashes=len(validation['collisions']),step_roundtrip='PASS'),indent=2))
