"""Conventional material controls; never substitutes for learned-method admission."""
from __future__ import annotations
import math
import random
import numpy as np
from PIL import Image, ImageDraw, ImageEnhance, ImageChops, ImageFont

SOURCE_HASH='bde1c7e0910941f8ca3bce06e8c2ddb3a31da4335b544fd041d84e97d1060225'
TITLES=['Unfolded room','Five changing territories','Sender / channel / receiver','Opposing-angle duplex','Face / body / world','Travelling attention','Temporal accumulation','Architecture of vacancy','Surface / screen-fixed control','Movement / image-change control','Light / authored exposure','Acoustic rooms / authored IR','The discarded film / DSP residue','Observation-led / scripted control','Interpretation-led / scripted control','Directing / bounded enumeration','Source-mixture / provisional joins']
COLORS=['#ecb95d','#9fd9d1','#d86a64','#b0b9e5','#e4dfd1']

def residual(source,processed):
    x,y=np.asarray(source,dtype=np.float64),np.asarray(processed,dtype=np.float64)
    if x.shape!=y.shape or not np.isfinite(x).all() or not np.isfinite(y).all():
        raise ValueError('Residual requires aligned finite arrays')
    return x-y

def schedule(seed,frames):
    if type(frames) is not int or not 1<=frames<=9000:raise ValueError('Bounded frame count required')
    rng=random.Random(seed); events=[]; clock=0
    while clock<frames:
        n=min(rng.choice([30,45,60,75]),frames-clock)
        # Same B shot: unverified arbitrary mixture slices, no phrase guarantee.
        start=rng.randrange(600,1500-n)*2
        events.append(dict(source_start_frame=start,source_end_frame=start+2*n,
                           output_start_frame=clock,output_frames=n))
        clock+=n
    return events

def intensity(i,n):
    t=i/n
    if t<.125 or t>=.875:return 0.
    if t<.5:return 1.
    return max(0.,1-(t-.5)/.375)

def fit(im,size):
    w,h=size;s=min(w/im.width,h/im.height)
    r=im.resize((max(1,round(im.width*s)),max(1,round(im.height*s))),Image.Resampling.BILINEAR)
    c=Image.new('RGB',size,'#0a0b0d');c.paste(r,((w-r.width)//2,(h-r.height)//2));return c

def compose(source,history,i,mode,portrait=False,amount=1.):
    if mode not in range(1,18):raise ValueError('Unknown study')
    w,h=(540,960) if portrait else (960,540)
    canvas=Image.new('RGB',(w,h),'#0a0b0d')
    anchor=(14,0,512,288) if portrait else (0,0,384,216)
    stage=(0,326,540,634) if portrait else (400,0,560,540)
    sx,sy,sw,sh=stage; a=Image.new('RGB',(sw,sh),'#0d1014');d=ImageDraw.Draw(a)
    # Fixed rectangular source fields are explicit; these are not actor mattes.
    fields=[source.crop((int(k*source.width/5),0,int((k+1)*source.width/5),source.height)) for k in range(5)]
    t=i/15
    if mode==1:
        for k,f in enumerate(fields):
            pw=int(sw*(.16+.035*math.sin(t*.6+k)))
            ph=int(sh*(.45+.18*math.sin(t*.4+k)))
            x=int((k/5)*sw+20*math.sin(t+k));y=int((sh-ph)/2+sh*.1*math.sin(t*.7+k))
            a.paste(fit(f,(pw,ph)),(x,y));d.rectangle((x,y,x+pw-1,y+ph-1),outline=COLORS[k],width=2)
    elif mode in (2,3,16,17):
        weights=np.array([1+.7*math.sin(t*.7+k*1.2) for k in range(5)]);weights/=weights.sum();x=0
        for k,f in enumerate(fields):
            pw=sw-x if k==4 else max(1,int(sw*weights[k]));a.paste(fit(f,(pw,sh)),(x,0));d.line((x,0,x,sh),fill=COLORS[k],width=3);x+=pw
        if mode==3:
            x=int((t%4)/4*sw);d.rectangle((x-18,sh//2-14,x+18,sh//2+14),fill='#f2cc65')
            d.text((8,8),'AUTHORED ROUTING PULSE',fill='white')
    elif mode==4:
        a.paste(fit(history[-1],(sw,sh//2)),(0,0));a.paste(fit(source,(sw,sh//2)),(0,sh//2))
        d.text((8,8),'ASYNCHRONOUS SOURCE',fill='white');d.text((8,sh//2+8),'B: CURRENT SOURCE',fill='white')
    elif mode==5:
        n=int(t//2)%3
        crop=source if n==2 else source.crop((int(source.width*.6),int(source.height*(.0 if n==0 else .2)),source.width,int(source.height*(.55 if n==0 else 1))))
        a=fit(crop,(sw,sh))
    elif mode==6:
        a=ImageEnhance.Brightness(fit(source,(sw,sh))).enhance(.18)
        cx=int((.5+.34*math.sin(t*.8))*source.width);box=(max(0,cx-65),0,min(source.width,cx+65),source.height)
        win=fit(source.crop(box),(int(sw*.35),int(sh*.8)));a.paste(win,(int((.5+.3*math.sin(t*.8))*sw)-win.width//2,(sh-win.height)//2))
    elif mode==7:
        count=min(7,2+int(t//3));tw,th=sw//3,sh//3
        for k in range(count):a.paste(fit(history[k%len(history)],(tw,th)),((k%3)*tw,(k//3)*th))
    elif mode==8:
        a=fit(source,(sw,sh));plate=source.crop((int(source.width*.45),0,int(source.width*.56),int(source.height*.2)))
        vacancy=fit(plate,(sw//3,sh));a.paste(vacancy,(int((.5+.25*math.sin(t*.4))*sw)-sw//6,0));ImageDraw.Draw(a).text((8,8),'AUTHORED VACANCY / ROOM SAMPLE',fill='white')
    elif mode==9:
        a=fit(source,(sw,sh));d=ImageDraw.Draw(a)
        for k in range(-sh,sw,24):d.line((k,sh*.55,k+sh*.3,sh*.95),fill=COLORS[0],width=3)
        d.text((8,8),'SCREEN-FIXED TEXTURE / UNTRACKED',fill='white')
    elif mode==10:
        a=ImageEnhance.Brightness(fit(source,(sw,sh))).enhance(.22);d=ImageDraw.Draw(a)
        diff=np.asarray(ImageChops.difference(source,history[0]).resize((40,24))).mean(axis=2)/255
        for row in range(24):
            vals=diff[row];pts=[(int(k*sw/39),int((row+.5)*sh/24+v*100)) for k,v in enumerate(vals)]
            d.line(pts,fill=COLORS[row%5],width=2)
    elif mode==11:
        a=fit(source,(sw,sh));overlay=Image.new('RGB',a.size,COLORS[int(t//6)%3]);a=Image.blend(a,overlay,.28)
        a=ImageEnhance.Contrast(a).enhance(1.2)
        small=fit(history[2],(sw//3,sh//3)).transpose(Image.Transpose.FLIP_LEFT_RIGHT)
        a.paste(small,(sw-sw//3,sh-sh//3));ImageDraw.Draw(a).text((8,8),'AUTHORED LIGHT + DELAYED MIRROR',fill='white')
    elif mode==12:
        a=fit(source,(sw,sh));d=ImageDraw.Draw(a)
        for k in range(12):
            inset=int((k*14+t*8)%max(1,min(sw,sh)//2));d.rectangle((inset,inset,sw-inset,sh-inset),outline=COLORS[int(t//8)%3])
        d.text((8,8),['ORIGINAL ROOM CONTROL','AUTHORED HARD ROOM','AUTHORED ABSORBENT ROOM'][min(2,int(t//8))],fill='white')
    elif mode==13:
        diff=ImageChops.difference(source,history[0]);a=fit(ImageEnhance.Contrast(diff).enhance(5),(sw,sh))
        if int(t//4)%2==0:a=Image.blend(a,fit(source,(sw,sh)),.4)
        ImageDraw.Draw(a).text((8,8),'TEMPORAL IMAGE DIFFERENCE / DSP SOUND',fill='white')
    elif mode in (14,15):
        order=([0,1,3,2,4] if mode==14 else [4,2,0,3,1]);idx=order[int(t//4)%5]
        a=fit(fields[idx],(sw,sh));ImageDraw.Draw(a).text((8,8),('OBSERVATION' if mode==14 else 'INTERPRETATION')+' / SCRIPTED ROUTING',fill='white')
    # All authored interventions have a true visual bypass.
    a=Image.blend(fit(source,(sw,sh)),a,float(amount))
    canvas.paste(a,(sx,sy))
    ax,ay,aw,ah=anchor;canvas.paste(source.resize((aw,ah),Image.Resampling.BILINEAR),(ax,ay))
    d=ImageDraw.Draw(canvas)
    font=ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',16)
    lines=[TITLES[mode-1],'CONVENTIONAL STUDY',f'{t:05.1f}s  |  wet {amount:.2f}','Complete source frame above','Source audio remains a mixture']
    for k,line in enumerate(lines):d.text((14,294+k*0 if portrait else 235+k*24),line if not portrait or k==0 else '',font=font,fill=COLORS[0] if k==0 else '#d7d7d7')
    return canvas,anchor


def history_index(index,delay):
    """15 fps proxy history reset at composition's exact registered camera cuts."""
    boundaries=[0,76,501,719,799,1324,1425,1608]
    return max(max(x for x in boundaries if x<=index),index-delay)
