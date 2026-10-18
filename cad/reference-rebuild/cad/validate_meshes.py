#!/usr/bin/env python3
"""Check every exported mesh, STEP roundtrip and render-scene GLB conversion."""
from pathlib import Path
import json
import trimesh
import numpy as np
import cadquery as cq
ROOT=Path(__file__).resolve().parents[1]; OUT=ROOT/'exports'
inv=json.loads((OUT/'inventory.json').read_text())
results=[]
scene=trimesh.Scene()
for p in inv['parts']:
    path=OUT/'parts'/(p['name']+'.stl')
    mesh=trimesh.load_mesh(path)
    result=dict(name=p['name'],vertices=len(mesh.vertices),faces=len(mesh.faces),
                watertight=bool(mesh.is_watertight),winding_consistent=bool(mesh.is_winding_consistent),
                finite=bool(np.isfinite(mesh.vertices).all()),positive_volume=bool(mesh.volume>0),
                connected_components=len(mesh.split(only_watertight=False)))
    result['passed']=all(result[k] for k in ['watertight','winding_consistent','finite','positive_volume'])
    results.append(result)
    mesh.visual=trimesh.visual.ColorVisuals(mesh,face_colors=[round(c*255) for c in p['color']]+[255])
    scene.add_geometry(mesh,node_name=p['name'],geom_name=p['name'])
step=cq.importers.importStep(str(OUT/'AVA-reference-rebuild.step')).val()
expected=sum(p['solids'] for p in inv['parts'])
roundtrip=dict(valid=step.isValid(),solid_count=len(step.Solids()),expected_solid_count=expected,
               solid_count_matches=len(step.Solids())==expected,
               volume_mm3=sum(s.Volume(1e-7) for s in step.Solids()),expected_volume_mm3=sum(p['volume_mm3'] for p in inv['parts']))
roundtrip['volume_relative_error']=abs(roundtrip['volume_mm3']-roundtrip['expected_volume_mm3'])/roundtrip['expected_volume_mm3']
roundtrip['passed']=bool(roundtrip['valid'] and roundtrip['solid_count_matches'] and roundtrip['volume_relative_error']<1e-5)
# glTF 2.0 uses metres and +Y up. Source CAD is millimetres and +Z up.
scene.apply_transform(trimesh.transformations.rotation_matrix(-np.pi/2,[1,0,0]))
scene.apply_scale(.001)
(OUT/'AVA-reference-rebuild.glb').write_bytes(scene.export(file_type='glb'))
reload=trimesh.load(OUT/'AVA-reference-rebuild.glb',force='scene')
report=dict(count=len(results),all_mesh_checks_pass=all(p['passed'] for p in results),
            step_roundtrip=roundtrip,glb_geometry_count=len(reload.geometry),parts=results)
(OUT/'mesh-validation.json').write_text(json.dumps(report,indent=2))
print(json.dumps({k:v for k,v in report.items() if k!='parts'},indent=2))
for p in results:
    if not p['passed']:print('FAILED',p)
assert report['all_mesh_checks_pass']
assert roundtrip['valid'] and roundtrip['solid_count_matches'] and roundtrip['volume_relative_error']<1e-5
assert report['glb_geometry_count']==len(results)
