"""Localize shared icons and every location strip in the world-map archive."""
import struct
import json
from pathlib import Path
import numpy as np
import cv2
from PIL import Image
from patch_battle_readability import pac_entries,pack,decode,encode
from repack_script import install_file
from pixel_ui import label,mask


def colors(t):
    at=struct.unpack_from('<I',t,8)[0]
    pal=struct.unpack_from('<16H',t,at)
    lum=[sum((v>>s)&31 for s in (0,5,10)) for v in pal]
    return min(range(1,16),key=lambda i:lum[i]),max(range(1,16),key=lambda i:lum[i])


def strip(t,width,chunk_w,chunk_h):
    w,h=struct.unpack_from('<HH',t,2)
    working=bytearray(t)
    struct.pack_into('<HH',working,2,chunk_w,w*h//chunk_w)
    raw=decode(working);im=Image.new('L',(width,w*h//width))
    columns=width//chunk_w
    for row in range(im.height//chunk_h):
        for col in range(columns):
            top=(row*columns+col)*chunk_h
            im.paste(raw.crop((0,top,chunk_w,top+chunk_h)),(col*chunk_w,row*chunk_h))
    def save(im):
        for row in range(im.height//chunk_h):
            for col in range(columns):
                raw.paste(im.crop((col*chunk_w,row*chunk_h,(col+1)*chunk_w,(row+1)*chunk_h)),(0,(row*columns+col)*chunk_h))
        out=encode(working,raw)
        struct.pack_into('<HH',out,2,w,h)
        # Independently decode the exact encoded strip and check its pixels.
        check=bytearray(out);struct.pack_into('<HH',check,2,chunk_w,w*h//chunk_w)
        assert decode(check).tobytes()==raw.tobytes()
        return out
    return im,save


def icon(t,text):
    im=decode(t);dark,light=colors(t)
    # Remove only the old lettering, reconstructing its background from the
    # surrounding original artwork. Keep the original palette and alpha mask.
    height=20 if text in ('BACK','CAN\nCEL','NEXT','MENU','READ') else 30
    im=erase_lettering(t,im,(0,0,32,height))
    text_height=32 if text=='ENTER' else 16
    m=mask(32,text_height,text)
    from PIL import ImageFilter
    outline=m.filter(ImageFilter.MaxFilter(3))
    for y in range(text_height):
        for x in range(32):
            if outline.getpixel((x,y)):im.putpixel((x,y),dark)
            if m.getpixel((x,y)):im.putpixel((x,y),light)
    return encode(t,im)


def erase_lettering(t,im,box):
    """Palette-constrained retouch; all pixels outside box remain byte-exact."""
    at=struct.unpack_from('<I',t,8)[0]
    palette=struct.unpack_from('<16H',t,at)
    rgb=np.array([[((v>>s)&31)*255//31 for s in (0,5,10)] for v in palette],dtype=np.uint8)
    ix=np.array(im);source=rgb[ix];lum=source.mean(axis=2)
    x,y,w,h=box;roi=np.zeros(ix.shape,np.uint8);roi[y:y+h,x:x+w]=255
    strokes=((lum>205)|(lum<45)).astype(np.uint8)*255
    strokes=cv2.dilate(strokes,np.ones((3,3),np.uint8))
    strokes&=roi;strokes[ix==0]=0
    repaired=cv2.inpaint(source,strokes,3,cv2.INPAINT_TELEA)
    distances=((repaired.astype(np.int32)[:,:,None,:]-rgb.astype(np.int32)[None,None,:,:])**2).sum(axis=3)
    distances[:,:,0]=10**9
    nearest=distances.argmin(axis=2).astype(np.uint8)
    result=ix.copy();result[strokes>0]=nearest[strokes>0]
    assert np.array_equal(result[roi==0],ix[roi==0])
    assert np.array_equal(result==0,ix==0)
    return Image.fromarray(result,'L')


def install(rom,files,project):
    previews=[];records=[]
    def read(name):
        a,n=files['data/'+name]
        return list(pac_entries(bytes(rom[a:a+n])))
    def save(name,es):install_file(rom,files,'data/'+name,pack(es))
    def record(fn,i,t):
        previews.append((fn+' '+str(i),bytearray(t)))
        records.append(dict(file='data/'+fn,entry=i,status='translated; decoded graphics reviewed'))

    fn='commonicn_cim.pac';es=read(fn)
    for k,text in [(1,'OK'),(2,'NO'),(3,'YES')]:
        i,t,x,y=es[k];im=decode(t);dark,light=colors(t)
        im.paste(light,(4,3,60,21))
        m=mask(28,9,text).resize((56,18),Image.Resampling.NEAREST)
        im.paste(dark,(4,3,60,21),m)
        es[k]=i,encode(t,im),x,y;record(fn,k,es[k][1])
    for k,text in [(9,'BACK'),(10,'CANCEL'),(11,'NEXT'),(12,'MENU')]:
        # CANCEL needs two lines in this 32px icon.
        if text=='CANCEL':text='CAN\nCEL'
        i,t,x,y=es[k]
        # Earlier passes changed Back; always start from pristine source art.
        original=list(pac_entries((project/'extracted_rom/nitrofs/data'/fn).read_bytes()))[k][1]
        es[k]=i,icon(original,text),x,y;record(fn,k,es[k][1])
    save(fn,es)

    fn='town_cim.pac';es=read(fn)
    i,t,x,y=es[18];es[18]=i,icon(t,'AREA\nMAP'),x,y;record(fn,18,es[18][1])
    towns=[('Dragon Arena',''),('Hamana City','Hinoto'),('Azuma Capital','Hinoto'),('Yokyo','Sun Country'),
           ('Goratos Verochka','Sverochka'),('Sarik City','Sarikas'),('Queensland\nCastle Town','Queensland'),
           ('Ark City','Westia'),('Landing Base','Muurye')]
    for k,(title,region) in enumerate(towns,19):
        i,t,x,y=es[k];im,writer=strip(t,128,64,32);dark,light=colors(t)
        label(im,(4,0,112,16),title,dark,light)
        if region:label(im,(24,18,80,10),region,light,dark)
        else:im.paste(dark,(24,18,104,28))
        es[k]=i,writer(im),x,y;record(fn,k,es[k][1])
    save(fn,es)

    fn='wmap_cim.pac';es=read(fn)
    names={
      64:['Hamana City','Drifting Cave','Windy Plains','Yonama Sea','West Yonama Sea','Muerai Ruins'],
      65:['Azuma Capital','Homura Cave','Kiyora Cave','Hidden Forest','Mount Haste','Cursed Dungeon 1','Cursed Dungeon 2'],
      66:['Yokyo','Shirohane Valley','Soon Plateau','Sacred Laozal','Amano Pillar','Cursed Dungeon 3','Cursed Dungeon 4'],
      67:['Goratos Verochka','Shirazuba Forest','Starui Snowfield','Ice Chasm','Cursed Dungeon 5','Cursed Dungeon 6'],
      68:['Sarik City','Queensland Castle Town','Guerrilla Village','Guerrilla Forest','Moonlit Plains','Minos Palace','Cursed Dungeon 7','Cursed Dungeon 8'],
      69:['Ark City','Igu Tunnel','Zhivago Fort','Mount Kuan','Kuan Summit','Cursed Dungeon 9','Cursed Dungeon 10','Cursed Dungeon 11'],
      70:['Queensland Fleet','Muurye Coast','Wedge Shrine','Inner Wedge Shrine','Seven Origin Shrines','Cursed Dungeon 12','Cursed Dungeon 13','Cursed Dungeon 14'],
      84:['South Hinoto','North Hinoto','Sun Country','Sverochka','Sarikas / Queensland','Westia','Muurye','Dragon Arena'],
    }
    # Short map captions retain full names in the translated description panel.
    compact={'Queensland Castle Town':'Queensland','Inner Wedge Shrine':'Inner Wedge','Seven Origin Shrines':'7 Origins',
             'Sarikas / Queensland':'Sarikas /\nQueensland'}
    for k,labels in names.items():
        i,t,x,y=es[k];im,writer=strip(t,64,32,16);dark,light=colors(t)
        assert im.height==len(labels)*16
        for row,text in enumerate(labels):
            text=compact.get(text,text)
            # Keep a readable two-line caption inside every original hit area.
            label(im,(2,row*16,60,16),text,dark,light)
        es[k]=i,writer(im),x,y;record(fn,k,es[k][1])
    for k,text in [(71,'ENTER'),(72,'WORLD\nMAP')]:
        i,t,x,y=es[k];es[k]=i,icon(t,text),x,y;record(fn,k,es[k][1])
    save(fn,es)

    fn='btl2cim.pac';es=read(fn)
    for k in (14,15):
        i,t,x,y=es[k];im=decode(t)
        # Shared atlas badges. Preserve borders, palette banks, DF/FP and arrows.
        for column,text in [(0,'HLD'),(1,'ATK'),(2,'DEF'),(6,'DRK'),(7,'LUR'),(8,'RUN')]:
            label(im,(column*24+3,195,18,18),text,15,1)
        es[k]=i,encode(t,im),x,y;record(fn,k,es[k][1])
    save(fn,es)
    (project/'map_icon_graphics_review.json').write_text(json.dumps(records,indent=2)+'\n')
    print('Translated shared prompts/icons, town headings, 58 map captions and battle badges')
