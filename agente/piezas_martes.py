from PIL import Image, ImageDraw, ImageFont, ImageOps, ImageFilter
U='/mnt/user-data/uploads/arepalandia/'
F='/usr/share/fonts/opentype/inter/InterDisplay-'
AZUL=(150,22,38); AMA=(250,190,20); ROJO=(28,42,110); BLANCO=(255,255,255)
def f(w,s): return ImageFont.truetype(F+w+'.otf', s)
logo=Image.open('/home/user/arepalandia/marca/logo.png').convert('RGB')
logo=logo  # recorta margen
def insignia(w):
    l=logo.resize((w, int(w*logo.height/logo.width)), Image.LANCZOS)
    pad=int(w*0.06); b=Image.new('RGBA',(l.width+2*pad,l.height+2*pad),(0,0,0,0))
    m=Image.new('L',b.size,0); ImageDraw.Draw(m).rounded_rectangle((0,0,*b.size),radius=pad*2,fill=255)
    fondo=Image.new('RGBA',b.size,BLANCO+(255,)); b.paste(fondo,(0,0),m); b.paste(l,(pad,pad)); return b
def franja(d,y,W,h=14):
    d.rectangle((0,y,W,y+h),fill=AMA); d.rectangle((0,y+h,W,y+2*h),fill=ROJO)
def centrado(d,W,y,txt,font,fill):
    w=d.textlength(txt,font=font); d.text(((W-w)/2,y),txt,font=font,fill=fill)
def pastilla(d,W,y,txt,font,bg,fg,padx=44,pady=22):
    w=d.textlength(txt,font=font); a=font.getbbox(txt); h=a[3]-a[1]
    x=(W-w)/2; d.rounded_rectangle((x-padx,y,x+w+padx,y+h+2*pady),radius=(h+2*pady)//2,fill=bg)
    d.text((x,y+pady-a[1]),txt,font=font,fill=fg); return y+h+2*pady

# ---------- Pieza 1: estado de WhatsApp 1080x1920, arepa mechada ----------
W,H=1080,1920
foto=Image.open(U+'WhatsApp Image 2026-11-02 at 16.51.29.jpeg').convert('RGB')
foto=ImageOps.fit(foto,(W,1080),Image.LANCZOS,centering=(0.42,0.5))
c=Image.new('RGB',(W,H),AZUL); c.paste(foto,(0,0))
d=ImageDraw.Draw(c)
franja(d,1080,W,12)
ins=insignia(400); c.paste(ins,(40,150),ins)
y=1140
centrado(d,W,y,'Arepa rellena',f('Black',118),BLANCO); y+=150
centrado(d,W,y,'Carne, pollo, cerdo o jamón',f('SemiBold',50),(255,225,228)); y+=64
centrado(d,W,y,'siempre con queso',f('SemiBold',50),(255,225,228)); y+=90
y=pastilla(d,W,y,'$170',f('Black',96),AMA,AZUL,padx=60,pady=18)+50
centrado(d,W,y,'Pedí por WhatsApp 📲'.replace(' 📲',''),f('Bold',46),BLANCO); y+=62
centrado(d,W,y,'091 507 257',f('Black',72),AMA)
c.save('/home/user/arepalandia/piezas/2026-11-03-a.jpg',quality=90)

# ---------- Pieza 2: Instagram 1080x1350, salchipapa ----------
W,H=1080,1350
foto=Image.open(U+'WhatsApp Image 2026-11-02 at 17.06.08.jpeg').convert('RGB')
foto=foto.crop((400,0,1640,920))
foto=ImageOps.fit(foto,(W,800),Image.LANCZOS,centering=(0.5,0.5))
c=Image.new('RGB',(W,H),AZUL); c.paste(foto,(0,0))
d=ImageDraw.Draw(c)
franja(d,800,W,12)
ins=insignia(330); c.paste(ins,(W-ins.width-30,30),ins)
# etiqueta "esta noche"
pastilla(d,W,40-0,'ESTA NOCHE',f('Black',40),ROJO,BLANCO,padx=30,pady=14) if False else None
d.rounded_rectangle((34,40,34+330,40+72),radius=36,fill=ROJO); d.text((34+36,52),'ESTA NOCHE',font=f('Black',40),fill=BLANCO)
y=870
centrado(d,W,y,'Salchipapas',f('Black',120),BLANCO); y+=160
centrado(d,W,y,'Para compartir · con huevo y cheddar',f('SemiBold',44),(255,225,228)); y+=100
pastilla(d,W,y,'Pedí por WhatsApp · 091 507 257',f('Black',50),AMA,AZUL,padx=46,pady=26)
c.save('/home/user/arepalandia/piezas/2026-11-03-b.jpg',quality=90)
