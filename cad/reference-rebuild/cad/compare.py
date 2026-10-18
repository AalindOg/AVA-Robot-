#!/usr/bin/env python3
"""Original reference and current CAD renders side by side, matched by height."""
from PIL import Image,ImageOps,ImageDraw,ImageFont,ImageChops
from pathlib import Path
root=Path(__file__).resolve().parents[1]
board=Image.new('RGB',(1700,1120),'#f3f4f9'); d=ImageDraw.Draw(board)
font=ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',23)
panels=[('APPROVED / FRONT',root/'references/front.jpg'),
        ('NEW CAD / FRONT',root/'images/front.png'),
        ('APPROVED / ANGLE',root/'references/angle.jpg'),
        ('NEW CAD / ANGLE',root/'images/three-quarter.png')]
for i,(label,path) in enumerate(panels):
    im=Image.open(path).convert('RGB'); bg=Image.new('RGB',im.size,im.getpixel((0,0)))
    diff=ImageChops.difference(im,bg).convert('L').point(lambda x:255 if x>34 else 0)
    bb=diff.getbbox(); im=im.crop(bb) if bb else im
    im=ImageOps.contain(im,(390,960))
    board.paste(im,(i*425+(425-im.width)//2,85+(960-im.height)//2))
    d.text((i*425+15,25),label,font=font,fill='#242133')
d.text((25,1070),'Image-based reconstruction. Physical scale, hidden geometry and hardware fit remain assumptions.',font=font,fill='#4d4a60')
board.save(root/'images/reference-comparison.jpg',quality=94)
print(root/'images/reference-comparison.jpg')
