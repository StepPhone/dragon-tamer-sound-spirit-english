"""Translate the reported battle UI and redraw native indexed text assets."""
import struct
from PIL import Image, ImageDraw, ImageFont
from repack_script import install_file


def pac_entries(data):
    for i in range(struct.unpack_from('<I', data, 4)[0]):
        a,n,x,y=struct.unpack_from('<4I',data,16+16*i)
        yield i,bytearray(data[a:a+n]),x,y


def pack(entries):
    out=bytearray(b'PK\0\1'+struct.pack('<III',len(entries),0,0))+bytearray(16*len(entries))
    for i,t,x,y in entries:
        struct.pack_into('<4I',out,16+16*i,len(out),len(t),x,y)
        out+=t
    struct.pack_into('<I',out,8,len(out))
    return out


def textmask(w,h,text,size):
    im=Image.new('L',(w,h));d=ImageDraw.Draw(im)
    f=ImageFont.truetype('C:/Windows/Fonts/arialbd.ttf',size)
    a,b,c,e=d.textbbox((0,0),text,font=f)
    assert c-a<=w-2 and e-b<=h-2,(text,w,h)
    d.text(((w-(c-a))//2-a,(h-(e-b))//2-b),text,font=f,fill=255)
    return im


def decode(t):
    w,h=struct.unpack_from('<HH',t,2)
    size,at,ms,ma=struct.unpack_from('<4I',t,16)
    pixels=[]
    for y in range(h):
        for x in range(w):
            tile=(y//8)*(w//8)+x//8
            m=struct.unpack_from('<H',t,ma+2*tile)[0] if ms else tile
            xx=7-x%8 if ms and m&1024 else x%8
            yy=7-y%8 if ms and m&2048 else y%8
            k=((m&1023) if ms else tile)*64+yy*8+xx
            pixels.append((t[at+k//2]>>(4*(k%2)))&15)
    im=Image.new('L',(w,h));im.putdata(pixels)
    return im


def encode(t,im):
    w,h=im.size;size,at,ms,ma=struct.unpack_from('<4I',t,16)
    tiles=[];index={};mapping=[]
    for y in range(0,h,8):
        for x in range(0,w,8):
            p=list(im.crop((x,y,x+8,y+8)).getdata())
            raw=bytes(p[i]|p[i+1]<<4 for i in range(0,64,2))
            if ms:
                if raw not in index:index[raw]=len(tiles);tiles.append(raw)
                old=struct.unpack_from('<H',t,ma+2*((y//8)*(w//8)+x//8))[0]
                mapping.append((old&0xf000)|index[raw])
            else:tiles.append(raw)
    if not ms:
        assert len(tiles)*32==size
        t[at:at+size]=b''.join(tiles)
        return t
    assert len(tiles)<=1024
    out=t[:at]+b''.join(tiles)
    struct.pack_into('<H',out,12,len(tiles))
    struct.pack_into('<I',out,16,len(tiles)*32)
    struct.pack_into('<I',out,28,len(out))
    out+=struct.pack('<'+'H'*len(mapping),*mapping)
    assert decode(out).tobytes()==im.tobytes()
    return out


def install(rom,files,project):
    arm,_,_,size=struct.unpack_from('<4I',rom,0x20)
    prompts={
        'ドラゴンに指示を':'Give dragons',
        '　出してください':'their orders.',
        'ターゲットを':'Select your',
        '　選んでください':'target.',
        '指示していない':'Some dragons',
        '　ドラゴンがいます':'need orders.',
        '前列にドラゴンが':'The front row',
        '　いなくなります':'will be empty.',
        '前列に戦闘可能な':'No ready dragons',
        'ドラゴンがいません':'in the front row.',
        'このドラゴンは':'This dragon',
        '　行動できません':'cannot act.',
        '相手を待っています':'Waiting for foe...',
    }
    for ja,en in prompts.items():
        old=ja.encode('shift_jis')+b'\0';new=en.encode()+b'\0'
        area=bytes(rom[arm:arm+size]);assert area.count(old)==1,(ja,area.count(old))
        assert len(new)<=len(old),(ja,en)
        p=arm+area.index(old);rom[p:p+len(old)]=new.ljust(len(old),b'\0')
    # Change display-name fields only; all species stats and model IDs stay intact.
    name='data/dragon_base.csv';a,n=files[name];raw=bytes(rom[a:a+n])
    lines=raw.decode('shift_jis').splitlines(keepends=True);count=0
    names={'フレアソード':'Flare Sword','リンドブルム':'Lindwurm'}
    for i,line in enumerate(lines):
        cols=line.split(',')
        if len(cols)>13 and cols[0].isdigit() and cols[13] in names:
            cols[13]=names[cols[13]];lines[i]=','.join(cols);count+=1
    assert count==2,count
    data=''.join(lines).encode('shift_jis')
    install_file(rom,files,name,data)
    # Back icon is shared by title settings and battle commands.
    name='data/commonicn_cim.pac';a,n=files[name]
    entries=list(pac_entries(bytes(rom[a:a+n])))
    i,t,x,y=entries[9];im=decode(t)
    pal=struct.unpack_from('<16H',t,48)
    colors=[tuple(((v>>s)&31)*255//31 for s in (0,5,10)) for v in pal]
    dark=min(range(1,16),key=lambda j:sum(colors[j]));white=max(range(1,16),key=lambda j:sum(colors[j]))
    mask=textmask(32,16,'BACK',9)
    for py in range(18):
        for px in range(32):
            if im.getpixel((px,py)):im.putpixel((px,py),dark)
            if py<16 and mask.getpixel((px,py))>=128:im.putpixel((px,py),white)
    entries[9]=(i,encode(t,im),x,y)
    install_file(rom,files,name,pack(entries))
    # Tile-mapped Start/Flee buttons, including their alternate copies/states.
    name='data/btl2cim.pac';a,n=files[name]
    entries=list(pac_entries(bytes(rom[a:a+n])))
    for asset in (14,15):
        i,t,x,y=entries[asset];im=decode(t)
        for px,py,w,label in [(120,160,64,'START'),(192,160,56,'FLEE' if asset==14 else 'QUIT'),
                             (0,232,64,'START'),(64,232,64,'START'),
                             (128,232,56,'FLEE' if asset==14 else 'QUIT'),
                             (184,232,56,'FLEE' if asset==14 else 'QUIT')]:
            mask=textmask(w-8,16,label,11)
            for dy in range(16):
                for dx in range(w-8):im.putpixel((px+4+dx,py+4+dy),1 if mask.getpixel((dx,dy))>=128 else 15)
        entries[asset]=(i,encode(t,im),x,y)
    install_file(rom,files,name,pack(entries))
    print('Battle readability: 13 prompts, 2 dragon names, Back, Start/Flee and bold command labels')
