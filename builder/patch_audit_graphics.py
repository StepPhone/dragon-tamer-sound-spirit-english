"""Localize audit findings in their native palettes and OBJ layouts."""
import struct,json
import numpy as np
import cv2
from PIL import Image,ImageDraw,ImageFont
from patch_battle_readability import pac_entries,pack,decode,encode
from repack_script import install_file
from pixel_ui import mask
from patch_nest_graphics import ink_text
from patch_audit_text import SCORES

def logical(t):
    w,h=struct.unpack_from('<HH',t,2);depth=t[6];size,at,ms,ma=struct.unpack_from('<4I',t,16)
    if ms:
        assert depth==4
        return decode(t),lambda im:encode(bytearray(t),im)
    cw,ch=struct.unpack_from('<HH',t,32) if t[:2]==b'CX' else (w,h)
    assert cw and ch and w%cw==0 and h%ch==0,(w,h,cw,ch)
    yy,xx=np.indices((h,w));chunk=(yy//ch)*(w//cw)+xx//cw
    k=chunk*cw*ch+((yy%ch)//8*(cw//8)+(xx%cw)//8)*64+(yy%8)*8+xx%8
    b=np.frombuffer(t,dtype=np.uint8)
    ix=b[at+k] if depth==8 else (b[at+k//2]>>((k%2)*4))&15
    im=Image.fromarray(ix.astype(np.uint8),'L')
    def save(im):
        values=np.array(im).flatten();order=k.flatten();raw=np.zeros(w*h,np.uint8);raw[order]=values
        payload=raw.tobytes() if depth==8 else (raw[::2]|(raw[1::2]<<4)).tobytes()
        out=bytearray(t);assert len(payload)==size;out[at:at+size]=payload
        assert logical(out)[0].tobytes()==im.tobytes()
        return out
    return im,save

def palette(t,es):
    if not t[7]:
        t=next(e[1] for e in es if e[1][7] and struct.unpack_from('<HH',e[1],2)==(0,0))
    return list(struct.unpack_from('<'+'H'*(t[7]*16),t,struct.unpack_from('<I',t,8)[0]))

def put(im,pal,box,text,style='sprite',size=12):
    x,y,w,h=box;lum=[sum((v>>s)&31 for s in (0,5,10)) for v in pal]
    fg=max(range(1,len(pal)),key=lambda i:lum[i])
    if style=='paper':return ink_text(im,pal,box,text)
    if style in ('red','stamp'):
        fg=max(range(1,len(pal)),key=lambda i:(pal[i]&31)-((pal[i]>>5)&31)-((pal[i]>>10)&31))
    if style=='stamp':
        a=np.array(im);yy,xx=np.indices(a.shape);a[(xx-31.5)**2+(yy-31.5)**2<27**2]=0;im=Image.fromarray(a,'L')
    if style=='score':
        im.paste(0,(x,y,x+w,y+h));h=40

    if style=='banner':
        for yy in range(y,y+h):
            for xx in range(x,x+w):im.putpixel((xx,yy),im.getpixel((8,yy)))
    elif style in ('light','story','warm'):
        # Only pale lettering is removed; original colored emblems remain.
        a=np.array(im);rgb=np.array([[((v>>s)&31)*255//31 for s in (0,5,10)] for v in pal],np.uint8)
        src=rgb[a];roi=np.zeros(a.shape,np.uint8);roi[y:y+h,x:x+w]=255
        strokes=(((src.max(axis=2).astype(int)-src.min(axis=2))<14)&(src.max(axis=2)>18)).astype(np.uint8)*255
        if style=='light':strokes=(src.min(axis=2)>115).astype(np.uint8)*255
        if style=='warm':
            strokes=((src.max(axis=2).astype(int)-src.min(axis=2)<60)|(src.mean(axis=2)<40)).astype(np.uint8)*255
            fg=min(range(1,len(pal)),key=lambda i:lum[i])
        strokes=cv2.dilate(strokes,np.ones((3,3),np.uint8));strokes&=roi
        repaired=cv2.inpaint(src,strokes,2,cv2.INPAINT_TELEA)
        ys,xs=np.where(strokes>0)
        if len(ys):
            ds=((repaired[ys,xs].astype(np.int32)[:,None,:]-rgb.astype(np.int32)[None,:,:])**2).sum(axis=2)
            if style=='warm':
                orange=(rgb[:,0].astype(int)-rgb[:,1]>25)&(rgb[:,1].astype(int)-rgb[:,2]>15)
                if orange.any():ds[:,~orange]=10**9
            a[ys,xs]=ds.argmin(axis=1)
        im=Image.fromarray(a,'L')
    elif style!='stamp':im.paste(0,(x,y,x+w,y+h))
    # Native pixel lettering for compact labels; larger cards use a readable font.
    if size==7:m=mask(w,h,text)
    else:
        m=Image.new('L',(w,h));d=ImageDraw.Draw(m)
        while True:
            font=ImageFont.truetype('C:/Windows/Fonts/arialbd.ttf',size)
            bb=d.multiline_textbbox((0,0),text,font=font,spacing=2,align='center')
            if bb[2]-bb[0]<=w-2 and bb[3]-bb[1]<=h-2:break
            size-=1;assert size>=8,(text,box)
        d.multiline_text(((w-bb[2]+bb[0])/2-bb[0],(h-bb[3]+bb[1])/2-bb[1]),text,font=font,fill=255,spacing=2,align='center')
        m=m.point(lambda v:255 if v>=110 else 0)
    im.paste(fg,(x,y,x+w,y+h),m)
    return im

def install(rom,files,project):
    changes=[];previews=[]
    def edit(fn,k,labels):
        from build import file_table
        current_files=file_table(rom)
        a,n=current_files['data/'+fn];es=list(pac_entries(bytes(rom[a:a+n])))
        i,t,x,y=es[k];im,save=logical(t);pal=palette(t,es);before=im.copy()
        for box,label,style,size in labels:im=put(im,pal,box,label,style,size)
        es[k]=i,save(im),x,y;install_file(rom,current_files,'data/'+fn,pack(es))
        changes.append({'file':fn,'entry':k,'labels':[v[1] for v in labels]})
        rgb=[tuple(((v>>s)&31)*255//31 for s in (0,5,10)) for v in pal];rgb[0]=(30,30,40)
        for label,pic in [('before',before),('after',im)]:
            out=Image.new('RGB',pic.size);out.putdata([rgb[v] for v in pic.getdata()]);previews.append((fn+' '+str(k)+' '+label,out))
    edit('wlcim.pac',3,[((4,r*24+3,86,17),s,'paper',7) for r,s in enumerate(['Host Battle','Join Battle','Start Battle','Rematch','Edit Team','Main Menu','Title Screen'])])
    edit('nest_cim.pac',0,[((3,2,26,10),'SORT','warm',7)])
    edit('nest_cim.pac',1,[((2,1,42,12),'GOLD','paper',7)])
    edit('nest_cim.pac',3,[((42,1,84,14),'ACTIVE TEAM','banner',7)])
    edit('nest_cim.pac',6,[((16,36,22,16),'FRT','light',7)])
    edit('dragontbl_cim.pac',20,[((0,1,96,14),'DRAGON SCORE','paper',7)])
    edit('dragontbl_cim.pac',21,[((0,1,96,14),'MYSTIC SCORE','paper',7)])
    edit('battle_u.pac',10,[((0,0,160,32),'Burning Edge Breath','sprite',16)])
    edit('battle_u.pac',0,[((0,(25+j)*16,16,16),label,'sprite',7) for j,label in enumerate(['CU','RE','FA','IL','PA','SS'])])
    edit('btl2cim.pac',0,[((0,0,32,16),'FX','light',7)])
    edit('gauge.pac',5,[((0,0,32,8),'FX','light',7)])
    edit('btl2cim.pac',16,[((85,26,82,14),'CRYSTAL CAGE','light',7),((62,148,132,16),'PLEASE SELECT','light',7)])
    edit('btl2cim.pac',24,[((0,0,56,26),'CANCEL','light',7)])
    edit('ht_melocim.pac',10,[((72,46,112,34),'FAILED','sprite',22)])
    edit('evtitle_cim.pac',10,[((0,0,32,16),'END','sprite',7)])
    edit('evoped_cim.pac',14,[((0,0,32,32),'END','sprite',14)])
    edit('evillust_cim.pac',0,[((0,0,64,32),'DEFEAT','red',16)])
    names=['Leviathan','Ouroboros','Yinglong','Quetzalcoatl','Tiamat','Fafnir','Orochi']
    for k,name in enumerate(names,1):edit('evillust_cim.pac',k,[((48,24,170,44),'Sage Dragon\n'+name,'story',14)])
    for k,name in enumerate(names,8):edit('evillust_cim.pac',k,[((70,13,116,32),'Dragon Trial','story',16),((66,57,126,26),name,'story',13)])
    edit('evillust_cim.pac',26,[((0,0,256,32),'This story is fiction.\nIt is unrelated to real people or places.','sprite',11)])
    edit('evillust_cim.pac',27,[((0,0,64,64),'BUT...','sprite',20)])
    edit('evillust_cim.pac',28,[((0,0,256,32),'What follows is even more fictional.\nIt has nothing to do with any real anything...','sprite',11)])
    edit('evillust_cim.pac',29,[((0,0,64,16),'...Probably.','sprite',10)])
    edit('evillust_cim.pac',30,[((9,16,46,32),'DRAGON\nTAMER','stamp',7)])
    edit('dttitle_cim.pac',28,[((38,84,164,12),'DRAGON TAMER: SOUND SPIRIT','sprite',9)])
    # Entry 25 already says ROCK NEVER STOPS in English.
    for k,name in enumerate(['Shanghai','Irkutsk','Berlin','New York','Baghdad','Liverpool'],138):
        edit('evillust_cim.pac',k,[((0,0,64,32),'REAL WORLD\n'+name,'sprite',10)])
    # Score title atlas order is the score-position column, not item order.
    import csv,io
    raw=(project/'extracted_rom/nitrofs/data/archives.csv').read_bytes().decode('cp932')
    active=[r for r in csv.reader(io.StringIO(raw)) if len(r)>2 and r[0].isdigit()][:23]
    order={int(r[1]):SCORES[j] for j,r in enumerate(active)};assert set(order)==set(range(23))
    for k,start,count in [(69,0,17),(70,17,6)]:
        edit('melosele_cim.pac',k,[((0,r*64,64,64),order[start+r]+'\nScore','score',11) for r in range(count)])
    from build import file_table
    for fn,labels in [('btl_panel5.cim',[((22,94,204,59),'SOUND WAVE','paper',7)]),
                      ('btl_panel.cim',[((96+j*24,192,22,21),label,'light',7) for j,label in enumerate(['HLD','ATK','DEF','DF','FP','SWP'])])]:
        current=file_table(rom);a,n=current['data/'+fn];t=bytearray(rom[a:a+n]);im,save=logical(t);pal=palette(t,[])
        before=im.copy()
        ms,ma=struct.unpack_from('<II',t,24)
        if ms and t[6]==4:
            w,h=im.size
            banks=np.array([struct.unpack_from('<H',t,ma+2*((y//8)*(w//8)+x//8))[0]>>12 for y in range(h) for x in range(w)]).reshape(h,w)
            combined=np.array(im)
            for bank in np.unique(banks):
                candidate=im.copy()
                for box,label,style,size in labels:candidate=put(candidate,pal[int(bank)*16:int(bank)*16+16],box,label,style,size)
                candidate=np.array(candidate);combined[banks==bank]=candidate[banks==bank]
            im=Image.fromarray(combined,'L')
        else:
            for box,label,style,size in labels:im=put(im,pal,box,label,style,size)
        install_file(rom,current,'data/'+fn,save(im));changes.append({'file':fn,'labels':[v[1] for v in labels]})
        rgb=[tuple(((v>>s)&31)*255//31 for s in (0,5,10)) for v in pal]
        for label,pic in [('before',before),('after',im)]:
            values=np.array(pic).astype(int)
            if ms and t[6]==4:values+=banks*16
            out=Image.new('RGB',pic.size);out.putdata([rgb[v] for v in values.flatten()]);previews.append((fn+' '+label,out))
    out=project/'qa/full_audit/translated_graphics';out.mkdir(exist_ok=True)
    for page in range(0,len(previews),16):
        sheet=Image.new('RGB',(1100,1160),(45,45,55));d=ImageDraw.Draw(sheet)
        for j,(name,im) in enumerate(previews[page:page+16]):
            x=j%4*275;y=j//4*290;d.text((x,y),name,fill='white');im.thumbnail((270,260));sheet.paste(im,(x,y+22))
        sheet.save(out/f'page_{page//16:02}.png')
    (out/'manifest.json').write_text(json.dumps(changes,indent=2),encoding='utf8')
    print('Localized',len(changes),'additional graphics')

