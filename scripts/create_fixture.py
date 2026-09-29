"""Create clearly labeled generated images in the project runtime folder, never scan outside it."""
from pathlib import Path
import math
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from PIL import Image,ImageDraw,ImageFont

ROOT=Path(__file__).resolve().parents[1]
DEST=ROOT/'.runtime'/'合成 测试图库'


def create():
    DEST.mkdir(parents=True,exist_ok=True)
    colors=[('#264c44','#83a493','#d7b889'),('#345663','#aec2c5','#d3a45e'),('#5a6245','#c3c5a0','#dfc5a2'),('#7b6661','#d9b6a4','#6e9b8d'),('#414b68','#a5b6c6','#d7c58b'),('#4e6653','#a7b48f','#cdbb90')]
    for i in range(30):
        palette=colors[i%len(colors)]
        image=Image.new('RGB',(1000,700),palette[0]);d=ImageDraw.Draw(image)
        # Intentionally graphic test cards, never pretend these are real photographs.
        d.rectangle((0,0,1000,350),fill=palette[1])
        d.ellipse((630,65,825,260),fill=palette[2])
        for layer in range(3):
            y=320+layer*95
            points=[(0,700),(0,y)]+[(x,y+int(70*math.sin(x/160+i+layer))) for x in range(0,1001,20)]+[(1000,700)]
            d.polygon(points,fill=[palette[0],'#426757','#214539'][layer])
        d.rounded_rectangle((40,43,350,88),radius=8,fill='#183326')
        try:font=ImageFont.truetype('arial.ttf',20)
        except OSError:font=ImageFont.load_default()
        d.text((55,52),f'SYNTHETIC FIXTURE {i+1:02}',font=font,fill='#e2e8d4')
        d.text((45,645),'GENERATED TEST ART / NOT A CAMERA PHOTO',font=font,fill='#d2dcc4')
        exif=Image.Exif();tags={}
        if i%7:exif[272]=['Synthetic Camera A','Synthetic Camera B','Synthetic Camera C'][i%3]
        if i%5:tags[42036]=['Test Lens 24-70','Test Lens 35','Test Lens 85'][i%3]
        tags[37386]=[24,35,50,70,85][i%5]
        if i%4:tags[41989]=[36,50,75,105,128][i%5]
        if i%6:tags[36867]=f'202{4+i//18}:{i%12+1:02}:15 12:30:00'
        tags.update({33437:[1.8,2.8,4,5.6][i%4],33434:1/[60,125,250,500][i%4],34855:[100,200,400,800][i%4]})
        exif[34665]=tags
        image.save(DEST/f'合成样例 {i+1:02}.jpg',quality=86,exif=exif)
    (DEST/'README.txt').write_text('All files here are synthetic fixtures generated for software verification. No real camera RAW samples.',encoding='utf-8')
    (DEST/'未知类型.fixture').write_text('synthetic unknown type')
    (DEST/'损坏 RAW 样例.cr3').write_bytes(b'INTENTIONALLY INVALID SYNTHETIC RAW FIXTURE')
    print(str(DEST))


if __name__=='__main__':create()
