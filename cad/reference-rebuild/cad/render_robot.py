#!/usr/bin/env python3
"""Offscreen VTK renders of actual exported STL parts, no generated imagery."""
import json, math, os
from pathlib import Path
import vtk
from PIL import Image, ImageDraw, ImageFont, ImageOps

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'exports'; IMAGES=ROOT/'images'; IMAGES.mkdir(exist_ok=True)
INV=json.loads((OUT/'inventory.json').read_text())
W,H=1400,1550
ren=vtk.vtkRenderer(); ren.SetBackground(.945,.95,.975)
win=vtk.vtkRenderWindow(); win.SetOffScreenRendering(1); win.SetSize(W,H)
win.SetMultiSamples(8); win.AddRenderer(ren)
ren.SetUseDepthPeeling(True); win.SetAlphaBitPlanes(1)
ren.SetMaximumNumberOfPeels(100); ren.SetOcclusionRatio(.1)
actors=[]
for p in INV['parts']:
    reader=vtk.vtkSTLReader(); reader.SetFileName(str(OUT/'parts'/(p['name']+'.stl'))); reader.Update()
    normals=vtk.vtkPolyDataNormals(); normals.SetInputConnection(reader.GetOutputPort())
    normals.SetFeatureAngle(48); normals.ConsistencyOn(); normals.AutoOrientNormalsOn(); normals.SplittingOn()
    mapper=vtk.vtkPolyDataMapper(); mapper.SetInputConnection(normals.GetOutputPort())
    actor=vtk.vtkActor(); actor.SetMapper(mapper)
    prop=actor.GetProperty(); prop.SetColor(*p['color']); prop.SetInterpolationToPhong()
    prop.SetAmbient(.30); prop.SetDiffuse(.72); prop.SetSpecular(.3); prop.SetSpecularPower(35)
    if 'screen' in p['name'] or 'glass' in p['name']:
        prop.SetSpecular(.55); prop.SetSpecularPower(65)
    if 'tire' in p['name'] or 'caster-wheel' in p['name']:
        prop.SetSpecular(.12); prop.SetSpecularPower(12)
    ren.AddActor(actor); actors.append(actor)
# Soft three-light setup; no shadows hiding contour details.
ren.AutomaticLightCreationOff()
for pos,intensity in [((-400,-650,800),.9),((500,-100,500),.5),((80,550,650),.65)]:
    light=vtk.vtkLight(); light.SetLightTypeToSceneLight(); light.SetPosition(*pos)
    light.SetFocalPoint(0,0,210); light.SetIntensity(intensity); ren.AddLight(light)
cam=ren.GetActiveCamera(); cam.ParallelProjectionOn(); cam.SetViewUp(0,0,1)
views={'front':(0,-1000,200),'three-quarter':(650,-1100,610),
       'rear':(-650,1050,570),'side':(1100,0,300),'top':(400,-650,1100)}
for name,pos in views.items():
    cam.SetPosition(*pos); cam.SetFocalPoint(0,0,197); cam.SetParallelScale(232)
    ren.ResetCameraClippingRange(); win.Render()
    grab=vtk.vtkWindowToImageFilter(); grab.SetInput(win); grab.SetInputBufferTypeToRGB(); grab.ReadFrontBufferOff(); grab.Update()
    writer=vtk.vtkPNGWriter(); writer.SetFileName(str(IMAGES/(name+'.png'))); writer.SetInputConnection(grab.GetOutputPort()); writer.Write()
    print('Rendered',name,flush=True)
# Export standard scene format, if VTK build supports it.
exporter=vtk.vtkGLTFExporter(); exporter.SetRenderWindow(win); exporter.InlineDataOn()
exporter.SetFileName(str(OUT/'AVA-reference-rebuild.gltf')); exporter.Write()
font_path='/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'
font=ImageFont.truetype(font_path,30); small=ImageFont.truetype(font_path,21)
board=Image.new('RGB',(2100,1330),'#f1f2f8'); d=ImageDraw.Draw(board)
d.text((45,28),'AVA / REFERENCE REBUILD',font=ImageFont.truetype(font_path,40),fill='#29233f')
d.text((45,86),'Fresh exterior CAD from the approved images — assumed scale, not hardware-fit validated',font=small,fill='#5e6070')
for i,(name,label) in enumerate([('three-quarter','01  THREE-QUARTER'),('front','02  FRONT'),('rear','03  REAR')]):
    im=Image.open(IMAGES/(name+'.png')).convert('RGB'); im=ImageOps.contain(im,(680,1040))
    board.paste(im,(i*700+(700-im.width)//2,145))
    d.text((i*700+40,1210),label,font=font,fill='#29233f')
d.text((45,1270),'Actual model renders. Screen, sensors and wheel components are visual placeholders.',font=small,fill='#5e6070')
board.save(IMAGES/'preview.jpg',quality=94)
print('Saved preview.jpg and glTF',flush=True)
