"""Keep full map descriptions clear of the separate difficulty footer."""
import struct

def install(rom,files,project):
    arm=struct.unpack_from('<I',rom,32)[0]
    changes={
        0x830f0:(0xe3a0200a,0xe3a02008), # Local map's native 8px font.
        0x854f0:(0xe3a0200a,0xe3a02008), # Matching world-map font.
        0x83ad8:(0xe3a00024,0xe3a00018), # Description y: 36 -> 24.
        0x856b8:(0xe3a00024,0xe3a00018),
    }
    for offset,(old,new) in changes.items():
        assert struct.unpack_from('<I',rom,arm+offset)[0]==old,hex(offset)
        struct.pack_into('<I',rom,arm+offset,new)
    print('Map text: native 8px font; full word-wrapped descriptions above footer')
