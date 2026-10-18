# AVA — reference-image exterior rebuild

A fresh procedural CAD reconstruction of the purple robot shown in Aalind’s selected reference images. This project **does not import the rejected legacy STL or STEP model**.

![Actual CAD renders](images/preview.jpg)

## Open the model

- `exports/AVA-reference-rebuild.step`: named, coloured solid assembly for CAD editors such as FreeCAD, Fusion or Onshape.
- `exports/AVA-reference-rebuild.stl`: complete exterior assembly in assembly coordinates. It contains separate components; **not a single fused, ready-to-print toy**.
- `exports/parts/*.stl`: individual exterior component instances, in assembly coordinates.
- `exports/AVA-reference-rebuild.glb`: portable coloured 3D model for compatible viewers.
- `exports/AVA-reference-rebuild.gltf`: alternate coloured scene export.
- `cad/build_robot.py`: editable CadQuery source, with named parameters and procedural geometry.
- `exports/inventory.json`: component inventory, dimensions, volumes and notes.
- `exports/validation.json`: actual BREP validation and pairwise-intersection results.

STEP is editable solid geometry but does not contain a native feature-history tree. The Python source preserves the procedural construction.

## What is reconstructed

- Closed rounded indigo head, wide teal screen and thick bezel.
- Circular side grilles with perforations, flat paddle antennas and a top sensor puck.
- Smooth pear-shaped body with dark vertical trim and separate front/rear shell sections.
- Two large treaded wheels with swept-spoke hubs.
- Small twin-wheel central caster, short side pods and a circular chest feature.

## What this is **not**

This is a **visual design prototype**, not a mechanically finished robot or a verified printing package. The reference images do not establish real dimensions, hidden shapes or exact hardware. Scale and obscured geometry are explicit design assumptions.

- No verified motor mounts, bearing fits, battery tray, cable routing, ventilation analysis or electronics clearances.
- No verified shell fasteners, snap-fits, hinges, caster swivel or wheel-shaft engagement.
- Screen, sensor lenses, axles and other hardware-looking solids are **visual placeholders**, not fabricated electronics.
- Rear details are reconstructed where the supplied views leave gaps.
- Fit tolerances, stability, strength, motion and printing have not been tested.
- This work is not represented as a pixel-exact recovery of the unknown original CAD.

The approved reference sheet combines exterior images and earlier cutaways. The assembled exterior is authoritative for appearance; no claim is made that the differing exposed electronics layouts can be combined into a working build.

## Rebuild locally

Python 3.12 with CadQuery 2.8.0, VTK 9.6.x, Pillow and trimesh:

```sh
python -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python cad/build_robot.py
.venv/bin/python cad/render_robot.py
.venv/bin/python cad/validate_meshes.py
.venv/bin/python cad/compare.py
.venv/bin/python cad/package.py
```

For an environment with an unrelated global `PYTHONPATH`, prefix each command with `env -u PYTHONPATH`. VTK renders offscreen; `xvfb-run` is an alternative if EGL rendering fails.

## Reference provenance

The surviving files in `references/` were copied from the existing robot-reel project folders. Those projects' asset scripts map them to older Telegram image-cache names; the original cache files are no longer present, so byte-for-byte equality with the expired originals cannot be independently rechecked.

See [references/provenance.json](references/provenance.json) for the source notes and view descriptions. Sampled frames from all six surviving source clips were examined for silhouette and caster geometry. Reference rights are not inferred from their presence; project licensing does not relicense the supplied images.

## Half Life

This is a disclosed, AI-assisted exterior-CAD iteration. No new work-hour claims, eligibility determination or platform submission are made by publishing these files. See [DESIGN-NOTES.md](DESIGN-NOTES.md) for current limitations and [PRINTING.md](PRINTING.md) before attempting a physical prototype. The platform-managed journal and funding tracker remain at the repository root.
