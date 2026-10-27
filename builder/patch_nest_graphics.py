"""Translate Nest graphics while retaining textured native button artwork."""
import struct
import numpy as np
import cv2
from PIL import Image
from pixel_ui import mask
from patch_battle_readability import pac_entries,pack,decode,encode
from patch_map_icons import strip
from repack_script import install_file


def retouch(im,palette,box):
    ix=np.array(im);rgb=np.array([[((v>>s)&31)*255//31 for s in (0,5,10)] for v in palette],np.uint8)
    source=rgb[ix];x,y,w,h=box
    roi=np.zeros(ix.shape,np.uint8);roi[y:y+h,x:x+w]=255
    # On parchment buttons, Japanese ink is much darker than the artwork.
    ink=(source.mean(axis=2)<115).astype(np.uint8)*255
    ink=cv2.dilate(ink,np.ones((3,3),np.uint8));ink&=roi;ink[ix==0]=0
    result=cv2.inpaint(source,ink,3,cv2.INPAINT_TELEA)
    distances=((result.astype(np.int32)[:,:,None,:]-rgb.astype(np.int32)[None,None,:,:])**2).sum(axis=3)
    distances[:,:,0]=10**9
    # Do not borrow dark border/ink colors when reconstructing parchment.
    distances[:,:,rgb.mean(axis=1)<145]=10**9
    nearest=distances.argmin(axis=2).astype(np.uint8)
    out=ix.copy();out[ink>0]=nearest[ink>0]
    assert np.array_equal(out[roi==0],ix[roi==0])
    assert np.array_equal(out==0,ix==0)
    return Image.fromarray(out,'L')


def ink_text(im,palette,box,text):
    im=retouch(im,palette,box)
    x,y,w,h=box;m=mask(w,h,text)
    dark=min(range(1,len(palette)),key=lambda i:sum((palette[i]>>s)&31 for s in (0,5,10)))
    im.paste(dark,(x,y,x+w,y+h),m)
    return im


def install(rom,files,project):
    root=project/'extracted_rom/nitrofs/data'
    reports=[]
    for fn,labels,pal_entry in [
      ('nest_cim.pac',{12:'Add Dragon',13:'Dragon List',14:'Team List',15:'Release',16:'Element',17:'Egg',18:'Species',19:'Level',20:'Name',
                       21:'Hatch with Sound',22:'Trade Medals',23:'Edit Team',24:'Release Dragon',25:'Hatch from Score',
                       27:'Add to Team',28:'Name Dragon',29:'Edit Team',30:'Change Position',31:'Remove from Team',32:'Name Team'},26),
      ('melosele_cim.pac',{36:'Hatch with This Sound',37:'Check Sound',38:'Countdown',39:'None',40:'3 Sec',41:'6 Sec',42:'Dragon Data',
                          43:'USE A SOUND\nTONTO HAS\nRECORDED',45:'PLAY A SOUND\nFOR TONTO\nL / R BUTTON',46:'Play Sound',47:'Cancel',48:'Try Again'},44)]:
        a,n=files['data/'+fn];es=list(pac_entries(bytes(rom[a:a+n])))
        originals=list(pac_entries((root/fn).read_bytes()))
        shared=struct.unpack_from('<16H',originals[pal_entry][1],48)
        for k,text in labels.items():
            i,t,x,y=es[k];t=originals[k][1];w,h=struct.unpack_from('<HH',t,2)
            im,writer=strip(t,w,32 if w==96 else min(w,64),h)
            palette=struct.unpack_from('<16H',t,48) if t[7] else shared
            bbox=im.point(lambda p:255 if p else 0).getbbox();left,top,right,bottom=bbox
            box=(left+4,top+3,right-left-8,bottom-top-7)
            im=ink_text(im,palette,box,text)
            es[k]=i,writer(im),x,y;reports.append((fn,k,text))
        if fn=='melosele_cim.pac':
            for k,text in enumerate(['ANCIENT','FRAT EGG','MEZOPI EGG','ACT EGG','FORTE EGG','GOLD EGG'],29):
                i,t,x,y=es[k];im=decode(t);pal=struct.unpack_from('<16H',t,48)
                im=ink_text(im,pal,(2,1,60,11),text)
                es[k]=i,encode(t,im),x,y;reports.append((fn,k,text))
        install_file(rom,files,'data/'+fn,pack(es))

    # Area headings are baked into each 8-bit map background as well as the
    # separate world-map label strips. Translate both copies.
    fn='wmap_cim.pac';a,n=files['data/'+fn];es=list(pac_entries(bytes(rom[a:a+n])))
    for k,text in enumerate(['SOUTH HINOTO','NORTH HINOTO','SUN COUNTRY','SVEROCHKA','SARIKAS/QUEENSLAND','WESTIA','MUURYE']):
        i,t,x,y=es[k];w,h=struct.unpack_from('<HH',t,2);size,at,ms,ma=struct.unpack_from('<4I',t,16)
        assert t[6]==8 and all(struct.unpack_from('<H',t,ma+2*j)[0]==j for j in range(ms//2))
        # Only the 128x32 corner containing the title needs decoding/retouching.
        im=Image.new('L',(128,32));im.putdata([t[at+((yy//8)*(w//8)+xx//8)*64+(yy%8)*8+xx%8] for yy in range(32) for xx in range(128)])
        pal=struct.unpack_from('<'+'H'*(t[7]*16),t,48)
        im=ink_text(im,pal,(11,11,108,12),text)
        for yy in range(32):
            for xx in range(128):t[at+((yy//8)*(w//8)+xx//8)*64+(yy%8)*8+xx%8]=im.getpixel((xx,yy))
        es[k]=i,t,x,y;reports.append((fn,k,text))
    install_file(rom,files,'data/'+fn,pack(es))
    import json
    (project/'nest_graphics_translated.json').write_text(json.dumps(reports,indent=2)+'\n')
    print('Translated',len(reports),'Nest/egg buttons and baked map headings, preserving artwork')

