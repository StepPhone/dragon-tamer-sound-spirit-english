"""Expand the battle-help label pool without changing its label IDs."""
import struct
from repack_script import install_file


def install(rom,files):
    name='data/info_battle.pac';start,size=files[name]
    data=bytearray(rom[start:start+size]);entry_start,entry_size=struct.unpack_from('<II',data,48)
    assert entry_start+entry_size==len(data)
    count=struct.unpack_from('<I',data,entry_start)[0];assert count==34
    slot=entry_start+4+24*4
    old=struct.unpack_from('<I',data,slot)[0]
    assert data[entry_start+old:entry_start+old+3]=='毒'.encode('shift_jis')+b'\0'
    struct.pack_into('<I',data,slot,entry_size)
    data+=b'Poison\0'
    struct.pack_into('<I',data,52,entry_size+7)
    struct.pack_into('<I',data,8,len(data))
    install_file(rom,files,name,data)
