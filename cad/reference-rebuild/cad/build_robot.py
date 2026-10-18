#!/usr/bin/env python3
"""AVA reference reconstruction — fresh exterior CAD, not a hardware-fit design.
All lengths in mm. +Z up, -Y front, X wheel axle. No legacy CAD imports.
Run from any directory: python cad/build_robot.py
"""
from pathlib import Path
import json, math, time
import cadquery as cq

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'exports'
PARAMS = dict(head_width=190., head_depth=120., head_height=132., head_z=304.,
              body_bottom=20., body_top=238., wall=3., wheel_diameter=132.,
              wheel_width=28., wheel_x=102., wheel_z=66., wheel_y=4.,
              caster_radius=18., split_gap=.35, scale_status='assumed; image proportions only')
PURPLE = (0.205, .185, .43)
TRIM = (.105, .11, .15)
RUBBER = (.035, .043, .055)
HUB = (.13, .145, .175)
TEAL = (.035, .255, .285)
SILVER = (.46, .49, .54)
PARTS = []


def rr(w, h, r, plane='XY', origin=(0,0,0)):
    """True line/arc rounded rectangle, no faceted superellipse."""
    x, y = w/2, h/2
    k = math.sqrt(.5)
    return (cq.Workplane(plane, origin=origin).moveTo(-x+r,-y).lineTo(x-r,-y)
        .threePointArc((x-r+r*k,-y+r-r*k),(x,-y+r)).lineTo(x,y-r)
        .threePointArc((x-r+r*k,y-r+r*k),(x-r,y)).lineTo(-x+r,y)
        .threePointArc((-x+r-r*k,y-r+r*k),(-x,y-r)).lineTo(-x,-y+r)
        .threePointArc((-x+r-r*k,-y+r-r*k),(-x+r,-y)).close())


def rounded_box(w,d,h,r,center):
    return cq.Workplane('XY').box(w,d,h).edges().fillet(r).translate(center)


def box(w,d,h,center):
    return cq.Workplane('XY').box(w,d,h).translate(center)


def cyl(r,length,origin,direction):
    return cq.Workplane(obj=cq.Solid.makeCylinder(r,length,cq.Vector(*origin),cq.Vector(*direction)))


def compound(shapes):
    return cq.Compound.makeCompound([s.val() if isinstance(s,cq.Workplane) else s for s in shapes])


def add(name, shape, color, note='', group=None):
    solid = shape.val() if isinstance(shape,cq.Workplane) else shape
    if not solid.isValid():
        solid = solid.fix()
    if not solid.isValid() or solid.Volume() <= 0:
        raise ValueError(f'Invalid geometry: {name}')
    PARTS.append(dict(name=name,shape=solid,color=color,note=note,group=group or name))
    print(f'{name}: {len(solid.Solids())} solids, {solid.Volume()/1000:.2f} cm3',flush=True)
    return shape


def spline_section(z,w,d,n=2.7):
    points=[]
    for i in range(64):
        t=2*math.pi*i/64
        points.append((w/2*math.copysign(abs(math.cos(t))**(2/n),math.cos(t)),
                       d/2*math.copysign(abs(math.sin(t))**(2/n),math.sin(t))))
    return cq.Workplane('XY',origin=(0,0,z)).spline(points,periodic=True).wire().val()


BODY_PROFILE=[(20,96,66),(25,126,88),(34,154,112),(55,181,135),(88,188,145),
              (132,186,142),(168,177,130),(203,159,112),(227,149,101),(238,148,98)]


def body_loft(inset=0):
    return cq.Workplane(obj=cq.Solid.makeLoft([spline_section(z,w-2*inset,d-2*inset)
                                            for z,w,d in BODY_PROFILE]))


def make_wheels():
    # Wheel local axle is Z, later rotated to world X. Rounded tire + independent hub.
    tire=(cq.Workplane('XY').circle(PARAMS['wheel_diameter']/2).extrude(28).edges('%Circle').fillet(5)
          .cut(cq.Workplane('XY').circle(51.6).extrude(28)))
    grooves=[]
    for i in range(48):
        grooves.append(box(2,1.25,24,(65.6,0,14)).rotate((0,0,0),(0,0,1),i*7.5))
    tire=tire.cut(cq.Workplane(obj=compound(grooves)))
    rim=cq.Workplane('XY').circle(51.4).circle(47).extrude(22).translate((0,0,3))
    hub=cq.Workplane('XY').circle(15.5).circle(4).extrude(22).translate((0,0,3))
    for i in range(7):
        pts=[]
        for radius,angle in [(13,-.23),(25,-.12),(48,.30),(48,.48),(25,.14),(13,.23)]:
            pts.append((radius*math.cos(angle),radius*math.sin(angle)))
        spoke=cq.Workplane('XY').polyline(pts).close().extrude(13).translate((0,0,7))
        hub=hub.union(spoke.rotate((0,0,0),(0,0,1),i*360/7))
    hub=hub.union(rim)
    cap=cq.Workplane('XY').circle(9).extrude(2).edges('>Z').fillet(.8).translate((0,0,25))
    for side,sign in [('right',1),('left',-1)]:
        def place(s):
            return (s.translate((0,0,-14)).rotate((0,0,0),(0,1,0),90*sign)
                    .translate((PARAMS['wheel_x']*sign,PARAMS['wheel_y'],PARAMS['wheel_z'])))
        add('tire-'+side,place(tire),RUBBER,'Visual tire; material and traction not tested',group='tire')
        add('hub-'+side,place(hub),HUB,'No motor-shaft fit specified',group='hub')
        add('hub-cap-'+side,place(cap),TRIM,group='hub-cap')


def make_head():
    # Rounded rectangular extrusion: head roof is genuinely closed.
    outer=rr(PARAMS['head_width'],PARAMS['head_height'],28,'XZ',(0,60,PARAMS['head_z'])).extrude(PARAMS['head_depth'])
    outer=outer.faces('>Y or <Y').edges().fillet(8)
    inner=rr(184,126,25,'XZ',(0,57,304)).extrude(114)
    inner=inner.faces('>Y or <Y').edges().fillet(5)
    head=outer.cut(inner)
    # Screen window through front; screen is a separate inset solid.
    window=rr(158,101,18,'XZ',(0,-49,304)).extrude(20)
    head=head.cut(window)
    screen=rr(157.5,100.5,17.75,'XZ',(0,-57.8,304)).extrude(2)
    # Speaker openings and separate flush rim/disk.
    for sign in [-1,1]:
        head=head.cut(cyl(29,16,(sign*85,3,305),(sign,0,0)))
    # Paddles are authored at root, rotated outwards. The dark inserts are separate.
    for side,sign in [('left',-1),('right',1)]:
        antenna=rr(14,35,6.8,'XZ',(0,2.5,17.5)).extrude(5)
        insert=rr(9,24,4.4,'XZ',(0,-1.7,19)).extrude(.9)
        antenna=antenna.cut(insert)
        def place(s):
            return s.rotate((0,0,0),(0,1,0),sign*12).translate((sign*78,2,360))
        ant=place(antenna); dark=place(insert)
        head=head.cut(ant).cut(dark)
        add('antenna-'+side,ant,PURPLE,'Cosmetic paddle; no RF design',group='antenna')
        add('antenna-inlay-'+side,dark,TRIM,group='antenna-inlay')
    # Slice along depth for a removable face component; visible seam = real separation.
    front=head.intersect(box(250,100,200,(0,-90.175,304)))
    back=head.intersect(box(250,150,200,(0,35.175,304)))
    add('head-front-bezel',front,PURPLE,'Open at back; fasteners/latches not designed')
    add('head-rear-shell',back,PURPLE,'Closed roof and rear; no internal electronics mounts')
    add('screen-placeholder',screen,TEAL,'Visual solid only, not a selected display')
    grill=(cq.Workplane('XY').circle(27.7).extrude(1.5))
    holes=[]
    for ix in range(-8,9):
        for iy in range(-8,9):
            x,y=ix*3.4,iy*3.4
            if x*x+y*y < 25.8**2:
                holes.append((x,y))
    grill=grill.faces('>Z').workplane().pushPoints(holes).hole(1.8)
    ring=cq.Workplane('XY').circle(34).circle(28.2).extrude(5).edges('%Circle').fillet(.8)
    backing=cq.Workplane('XY').circle(27.7).extrude(1)
    for side,sign in [('right',1),('left',-1)]:
        def place(s,x):
            return s.rotate((0,0,0),(0,1,0),90*sign).translate((sign*x,3,305))
        add('speaker-ring-'+side,place(ring,95),TRIM,group='speaker-ring')
        add('speaker-grille-'+side,place(grill,96),HUB,'Perforated cosmetic grille, not acoustic engineering',group='speaker-grille')
        add('speaker-backing-'+side,place(backing,93.5),RUBBER,group='speaker-backing')
    puck=cq.Workplane('XY').circle(25).extrude(12).edges('%Circle').fillet(1.4).translate((24,0,370))
    for name,x,r,col in [('sensor-small',15,2.5,(.26,.12,.045)),('sensor-lens',32,4.2,(.13,.16,.42))]:
        lens=cyl(r,5,(x,-26,376),(0,1,0))
        puck=puck.cut(lens)
        add(name,lens,col,'Unspecified visual sensor aperture')
    add('top-sensor-puck',puck,TRIM,'Cosmetic sensor housing; board and connector not selected')


def stripe_cutter(sign,width):
    # Smooth X/Z guide follows shoulder and lower lobe, extruded across depth.
    guide=[(48,30),(59,52),(63,91),(63,132),(59,169),(49,207),(42,239)]
    left=[(sign*x-width/2,z) for x,z in guide]
    right=[(sign*x+width/2,z) for x,z in reversed(guide)]
    return (cq.Workplane('XZ',origin=(0,10,0)).moveTo(*left[0]).spline(left[1:],includeCurrent=True)
            .lineTo(*right[0]).spline(right[1:],includeCurrent=True).close().extrude(110))


def make_body():
    outer=body_loft()
    inner=body_loft(3)
    shell=outer.cut(inner)
    # Outer/inner loft have shared end planes; add intentional top and bottom skin.
    bottom=outer.intersect(box(250,220,3,(0,0,21.5)))
    top=outer.intersect(box(250,220,3,(0,0,236.5)))
    shell=shell.union(bottom).union(top)
    for sign in [-1,1]:
        shell=shell.cut(cyl(68,50,(sign*87,4,PARAMS['wheel_z']),(sign,0,0)))
        axle=cyl(3.8,37,(sign*65,4,PARAMS['wheel_z']),(sign,0,0))
        shell=shell.cut(axle)
        # A visual axle bridges the shell and wheel without claiming a motor fit.
        add('drive-axle-'+('right' if sign>0 else 'left'),axle,SILVER,
            'Conceptual axle only; motor and bearing interfaces are not designed',group='drive-axle')
    # Central wheeled caster cutout, not a ball socket.
    shell=shell.cut(box(44,55,50,(0,-51,24)))
    chest=cyl(11.5,9,(0,-69,180),(0,1,0)).cut(cyl(8,10,(0,-70,180),(0,1,0)))
    glass=cyl(7.7,1.5,(0,-69.3,180),(0,1,0))
    backing=cyl(7.7,1,(0,-61.5,180),(0,1,0))
    light=cyl(2,4,(23,-66.5,180),(0,1,0))
    shell=shell.cut(chest).cut(glass).cut(backing).cut(light)
    add('chest-sensor-ring',chest,TRIM)
    add('chest-sensor-glass',glass,TEAL,'Visual part, camera model not selected')
    add('chest-sensor-backing',backing,TRIM)
    add('status-indicator',light,(.76,.82,.77))
    for side,sign in [('left',-1),('right',1)]:
        # Extruded capsule avoids degenerate corner triangles from 3D fillets.
        pod=rr(30,16,7.5,'XZ',(sign*99,12,167)).extrude(18)
        shell=shell.cut(pod)
        add('side-pod-'+side,pod,TRIM,'Exterior appendage only',group='side-pod')
    # Inlaid vertical dark bands. Geometry is subtracted from purple shell.
    for side,sign in [('left',-1),('right',1)]:
        trim=shell.intersect(stripe_cutter(sign,5.0))
        shell=shell.cut(stripe_cutter(sign,5.35))
        add('body-trim-'+side,trim,TRIM,'Separate styling strip',group='body-trim')
    # Shell halves (not a tested snap-fit); seam kept clear.
    front=shell.intersect(box(250,130,260,(0,-65.175,130)),tol=1e-5)
    back=shell.intersect(box(250,130,260,(0,65.175,130)),tol=1e-5)
    add('body-front-shell',front,PURPLE,'Exterior shell with no verified internal packaging')
    add('body-rear-shell',back,PURPLE,'Removable-style back; attachment still to be engineered')


def make_caster():
    wheel=(cq.Workplane('XY').circle(18).circle(3.2).extrude(6)
           .edges('%Circle').fillet(1.1))
    for side,x in [('left',-9.5),('right',3.5)]:
        wp=wheel.rotate((0,0,0),(0,1,0),90).translate((x,-51,18))
        add('caster-wheel-'+side,wp,RUBBER,'Twin support wheel; bearing fits not specified',group='caster-wheel')
    fork=box(30,12,5,(0,-51,46.5))
    for x in [-13,13]:
        arm=rr(12,30,4,'YZ',(x-2,-51,32)).extrude(4)
        fork=fork.union(arm)
    bore=cyl(3.2,40,(-20,-51,18),(1,0,0))
    fork=fork.cut(bore)
    add('caster-fork',fork,PURPLE,'Geometric fork only, swivel and attachment not engineered')
    add('caster-axle-placeholder',cyl(3,30,(-15,-51,18),(1,0,0)),SILVER,'Placeholder pin, not a hardware specification')


def export():
    OUT.mkdir(exist_ok=True,parents=True)
    for p in ['parts','meshes']:
        (OUT/p).mkdir(exist_ok=True)
    assy=cq.Assembly(name='AVA-Reference-Rebuild')
    inventory=[]
    for part in PARTS:
        n,s=part['name'],part['shape']; b=s.BoundingBox()
        assy.add(s,name=n,color=cq.Color(*part['color']))
        cq.exporters.export(s,str(OUT/'parts'/f'{n}.stl'),tolerance=.08,angularTolerance=.13)
        # Each file is also a render cache, in assembly coordinates.
        inventory.append(dict(name=n,color=part['color'],group=part['group'],note=part['note'],
                              solids=len(s.Solids()),valid=s.isValid(),volume_mm3=s.Volume(1e-7),
                              bounds=[b.xmin,b.xmax,b.ymin,b.ymax,b.zmin,b.zmax]))
    assy.export(str(OUT/'AVA-reference-rebuild.step'))
    cq.exporters.export(compound([p['shape'] for p in PARTS]),str(OUT/'AVA-reference-rebuild.stl'),
                        tolerance=.08,angularTolerance=.13)
    (OUT/'inventory.json').write_text(json.dumps(dict(parameters=PARAMS,parts=inventory),indent=2))
    # Exact BREP intersections; broad-phase bounds pruning. Errors fail the check.
    collisions=[]; errors=[]; tested=0
    for i,a in enumerate(PARTS):
        ba=a['shape'].BoundingBox()
        for b in PARTS[i+1:]:
            bb=b['shape'].BoundingBox()
            if any(min(getattr(ba,ax+'max'),getattr(bb,ax+'max'))-
                   max(getattr(ba,ax+'min'),getattr(bb,ax+'min')) < .001 for ax in 'xyz'):
                continue
            tested+=1
            try:
                v=a['shape'].intersect(b['shape']).Volume()
                if v>.5:
                    collisions.append(dict(a=a['name'],b=b['name'],volume_mm3=v))
            except Exception as e:
                errors.append(dict(a=a['name'],b=b['name'],error=str(e)))
    assembly=compound([p['shape'] for p in PARTS]); bb=assembly.BoundingBox()
    report=dict(part_instances=len(PARTS),all_brep_valid=all(p['shape'].isValid() for p in PARTS),
                assembly_dimensions_mm=[bb.xlen,bb.ylen,bb.zlen],
                collision_threshold_mm3=.5,tested_pairs=tested,collisions=collisions,errors=errors,
                status='exterior reconstruction; NOT PRINT OR HARDWARE FIT VALIDATED')
    (OUT/'validation.json').write_text(json.dumps(report,indent=2))
    print(json.dumps(report,indent=2),flush=True)
    if collisions or errors:
        raise RuntimeError('Assembly validation failed; see exports/validation.json')


if __name__=='__main__':
    t=time.time()
    make_wheels(); make_head(); make_body(); make_caster(); export()
    print(f'Done in {time.time()-t:.1f}s',flush=True)
