"""Localize executable intro prompts and every animated Read-button frame."""
import struct
from PIL import Image
from patch_battle_readability import decode
from patch_map_icons import icon


def install(rom,files,project):
    arm,_,_,size=struct.unpack_from('<4I',rom,0x20)
    prompts=[('       ＜スピリット＞を…','       <Spirit>...'),
             ('    お前の＜スピリット＞を…','    Your <Spirit>...'),
             ('お前の＜スピリット＞を示せ……！','Show your <Spirit>...!')]
    for ja,en in prompts:
        old=ja.encode('shift_jis')+b'\0';new=en.encode('ascii')+b'\0'
        assert len(new)<=len(old)
        area=bytes(rom[arm:arm+size]);assert area.count(old)==1
        offset=arm+area.index(old)
        rom[offset:offset+len(old)]=new.ljust(len(old),b'\0')
    start,size=files['data/commonicn_cim.pac'];source=bytes(rom[start:start+size])
    pal_at,pal_size=struct.unpack_from('<II',source,16+25*16)
    palette=struct.unpack_from('<16H',source,pal_at+48)
    colors=[tuple(((c>>s)&31)*255//31 for s in (0,5,10)) for c in palette]
    previews=Image.new('RGB',(384,12*96),(40,40,40))
    for row,asset in enumerate(range(13,25)):
        offset,length=struct.unpack_from('<II',source,16+asset*16)
        texture=bytearray(source[offset:offset+length])
        assert texture[:8]==b'CX\x20\0\x20\0\x04\0'
        n,at=struct.unpack_from('<II',texture,16);assert n==512 and at==48
        pix=texture[at:at+n];indices=[]
        for y in range(32):
            for x in range(32):
                bit=((y//8)*4+x//8)*64+(y%8)*8+x%8
                indices.append((pix[bit//2]>>(4*(bit%2)))&15)
        original=Image.new('RGB',(32,32));original.putdata([colors[v] for v in indices])
        # Give the shared-palette frame a temporary local palette so it uses
        # the same artwork-preserving lettering treatment as the Back icon.
        working=bytearray(texture)
        struct.pack_into('<I',working,8,len(working))
        working+=struct.pack('<16H',*palette)
        patched=icon(working,'READ')
        texture[at:at+n]=patched[at:at+n]
        indices=list(decode(texture).getdata())
        assert len(texture)==length
        rom[start+offset:start+offset+length]=texture
        edited=Image.new('RGB',(32,32));edited.putdata([colors[v] for v in indices])
        previews.paste(original.resize((96,96)),(0,row*96))
        previews.paste(edited.resize((96,96)),(128,row*96))
    previews.save(project/'qa/read-icon-before-after.png')
    print('Localized 3 executable Spirit prompts and 12 Read-button frames')
