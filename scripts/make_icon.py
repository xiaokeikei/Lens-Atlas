from pathlib import Path
from PIL import Image, ImageDraw
import math

root=Path(__file__).resolve().parents[1]
(root/'assets').mkdir(exist_ok=True)
im=Image.new('RGBA',(256,256),(0,0,0,0))
d=ImageDraw.Draw(im)
d.rounded_rectangle((4,4,252,252),radius=52,fill='#203f32')
d.ellipse((49,49,207,207),outline='#c9d4ac',width=7)
for i in range(6):
    a=i*math.pi/3
    p=(128+42*math.cos(a),128+42*math.sin(a))
    q=(128+78*math.cos(a+.55),128+78*math.sin(a+.55))
    r=(128+42*math.cos(a+math.pi/3),128+42*math.sin(a+math.pi/3))
    d.polygon([p,q,r],fill='#c9d4ac')
im.save(root/'assets'/'lens-atlas.png')
im.save(root/'assets'/'lens-atlas.ico',sizes=[(16,16),(24,24),(32,32),(48,48),(64,64),(128,128),(256,256)])
