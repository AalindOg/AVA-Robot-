# Printing and fabrication status

**This package is a visual exterior model, not a released printable robot kit.** No parts have been printed, no slicer simulation has been accepted, and no hardware fit has been measured. Do not order hardware or print every full-size part from these files assuming they will assemble.

## Files and orientation

`exports/parts/*.stl` preserves assembly coordinates, not bed orientation. Import one component at a time and use your slicer's lay-on-face and drop-to-bed tools. Separate screen, lens, trim and axle solids are visualization components; their presence is not an instruction to print electronics.

The complete `AVA-reference-rebuild.stl` is a multi-component visualization assembly. It is **not** fused into one connected object, and unsupported components may float if printed as-is. Use STEP for CAD work or GLB for viewing.

## Sensible first physical test

After selecting actual hardware and engineering joins, print a small clearance coupon or a single shell section, not the entire robot. PLA and a 0.4 mm nozzle are reasonable prototype starting choices; 0.2 mm layers and three walls are starting settings only. Support needs depend on orientation and remain unchecked. Do not rely on the old project's support-free claims.

## Explicit remaining mechanical tasks

1. Measure the selected display, motors, wheels/tires, battery and controller boards.
2. Resize parameters and add PCB mounts, motor mounts, bearings, cable passages and battery retention.
3. Add actual shell fasteners or qualified snap-fits, plus captive hardware access.
4. Resolve whether the central support is a swivel twin-wheel caster; add its actual mounting and clearance sweep.
5. Choose and test tire material, shaft interfaces and balance/stability with real masses.
6. Verify heat dissipation, charger/battery safety and wiring protection separately.
7. Slice, check every layer, print fit samples, and update the dimensional tolerances from measurements.

## Counts and estimates

The verified component-instance count is recorded in `exports/validation.json`; per-instance volumes and bounding boxes are in `exports/inventory.json`. Duplicate instances such as left/right wheels are intentionally separate for the assembly. No filament/time estimate is supplied because material, supports, orientation and infill have not been validated.
