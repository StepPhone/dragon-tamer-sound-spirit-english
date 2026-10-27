"""Reuse the supplied StepHackerZ native artwork on the lower boot screen."""
import struct
from PIL import Image
from patch_battle_readability import pac_entries,pack
from repack_script import install_file

def install(rom,files,project):
    source=Image.open(project/'StepHackerZ_ds_lower_256x192_native.png').convert('RGB')
    assert source.size==(256,192)
    im=source.quantize(colors=64,method=Image.Quantize.MEDIANCUT,dither=Image.Dither.NONE)
    pal=(im.getpalette()+[0]*192)[:192]
    colors=[((pal[i]*31+127)//255)|(((pal[i+1]*31+127)//255)<<5)|(((pal[i+2]*31+127)//255)<<10) for i in range(0,192,3)]
    name='data/ttlcim.pac';a,n=files[name];es=list(pac_entries(bytes(rom[a:a+n])))
    i,t,x,y=es[1]
    assert t[:8]==b'CT\x00\x01\xc0\x00\x08\x04'
    po=struct.unpack_from('<I',t,8)[0];size,at,ms,ma=struct.unpack_from('<4I',t,16)
    assert (size,ms)==(49152,1536)
    struct.pack_into('<64H',t,po,*colors)
    pixels=bytes(im.getpixel((tx+xx,ty+yy)) for ty in range(0,192,8) for tx in range(0,256,8) for yy in range(8) for xx in range(8))
    t[at:at+size]=pixels
    struct.pack_into('<768H',t,ma,*range(768))
    es[1]=i,t,x,y
    install_file(rom,files,name,pack(es))
    preview=Image.new('RGB',im.size)
    preview.putdata([tuple(((colors[v]>>s)&31)*255//31 for s in (0,5,10)) for v in im.getdata()])
    preview.save(project/'qa/credits_boot.png')
    print('Added native StepHackerZ lower boot-screen credits')

