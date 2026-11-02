import subprocess, os
from PIL import Image, ImageDraw, ImageFont
R=os.path.dirname(os.path.abspath(__file__)); U='/mnt/user-data/uploads/arepalandia/'
F='/usr/share/fonts/opentype/inter/InterDisplay-'
AZUL=(150,22,38); AMA=(250,190,20); ROJO=(28,42,110)
def f(w,s): return ImageFont.truetype(F+w+'.otf',s)
def nom(n): return U+open(f'{R}/n{n}').read().strip()
W,H=1080,1920
# (clip, inicio, duración, texto)
tomas=[(67,2.0,2.8,'Hechas en el momento'),(62,8.0,2.2,'Rellenos caseros'),(22,3.5,2.7,'Arepas bien rellenas'),
       (17,5.0,3.0,'Tequeños recién fritos'),(10,28.0,2.6,'Directo a tu casa')]
def cartel(txt,path):
    im=Image.new('RGBA',(W,H),(0,0,0,0)); d=ImageDraw.Draw(im); fo=f('Black',84)
    w=d.textlength(txt,font=fo); x=(W-w)/2; y=300
    d.rounded_rectangle((x-40,y-18,x+w+40,y+110),radius=28,fill=AMA+(255,))
    d.text((x,y),txt,font=fo,fill=AZUL); im.save(path)
partes=[]
for i,(n,ss,dur,txt) in enumerate(tomas):
    png=f'{R}/t{i}.png'; cartel(txt,png); out=f'{R}/p{i}.mp4'
    z=1.18 if n==22 else 1.0  # el clip 22 trae la marca de CapCut arriba a la derecha: lo acercamos y recortamos de abajo
    zw,zh=int(W*z)//2*2,int(H*z)//2*2
    vf=(f"[0:v]scale={zw}:{zh}:force_original_aspect_ratio=increase,crop={W}:{H}:(in_w-{W})/2:in_h-{H},setsar=1,fps=30,"
        f"eq=saturation=1.15:contrast=1.04[v];[1:v]format=rgba{'' if i==0 else ',fade=in:st=0.15:d=0.25:alpha=1'}[t];[v][t]overlay=0:0,"
        f"{'' if i==0 else 'fade=in:st=0:d=0.15,'}fade=out:st={dur-0.15}:d=0.15[o]")
    subprocess.run(['ffmpeg','-v','error','-y','-ss',str(ss),'-t',str(dur),'-i',nom(n),'-loop','1','-t',str(dur),'-i',png,
        '-filter_complex',vf,'-map','[o]','-an','-c:v','libx264','-pix_fmt','yuv420p','-r','30',out],check=True)
    partes.append(out)
# cierre
logo=Image.open('/home/user/arepalandia/marca/logo.png').convert('RGB')
c=Image.new('RGB',(W,H),AZUL); d=ImageDraw.Draw(c)
lw=820; l=logo.resize((lw,int(lw*logo.height/logo.width))); pad=40
d.rounded_rectangle(((W-lw)//2-pad,330-pad,(W+lw)//2+pad,330+l.height+pad),radius=60,fill=(255,255,255)); c.paste(l,((W-lw)//2,330))
def cen(y,t,fo,fill):
    w=d.textlength(t,font=fo); d.text(((W-w)/2,y),t,font=fo,fill=fill)
y=330+l.height+120
cen(y,'Comida venezolana',f('Black',76),(255,255,255)); y+=96
cen(y,'en Mercedes',f('Black',76),(255,255,255)); y+=150
cen(y,'Pedí por WhatsApp',f('Bold',52),(255,225,228)); y+=72
cen(y,'091 507 257',f('Black',100),AMA); y+=150
cen(y,'Rodó 920 · Mercado de Mercedes',f('SemiBold',46),(255,225,228))
d.rectangle((0,H-40,W,H-20),fill=AMA); d.rectangle((0,H-20,W,H),fill=ROJO)
c.save(f'{R}/cierre.png')
subprocess.run(['ffmpeg','-v','error','-y','-loop','1','-t','3.2','-i',f'{R}/cierre.png','-vf','fps=30,zoompan=z=\'min(1.0+0.0015*on,1.05)\':d=96:s=1080x1920:fps=30,fade=in:st=0:d=0.3,format=yuv420p',
    '-an','-c:v','libx264','-r','30',f'{R}/p9.mp4'],check=True)
partes.append(f'{R}/p9.mp4')
open(f'{R}/lista.txt','w').write(''.join(f"file '{p}'\n" for p in partes))
os.makedirs('/home/user/arepalandia/piezas',exist_ok=True)
subprocess.run(['ffmpeg','-v','error','-y','-f','concat','-safe','0','-i',f'{R}/lista.txt','-f','lavfi','-t','16.5','-i','anullsrc=r=44100:cl=stereo',
    '-shortest','-c:v','libx264','-crf','23','-preset','medium','-pix_fmt','yuv420p','-c:a','aac','-movflags','+faststart','/home/user/arepalandia/piezas/reel-muestra.mp4'],check=True)
