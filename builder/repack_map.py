"""Rebuild map string matrices while preserving row/column IDs and numeric fields."""
import json
import struct
import sys
import textwrap
from repack_script import install_file


def entries(data):
    assert data[:4] == b'PK\0\1'
    count,total=struct.unpack_from('<II',data,4)
    assert count==3 and total==len(data)
    for i in range(count):
        start,size,x,y=struct.unpack_from('<4I',data,16+16*i)
        entry=data[start:start+size]
        columns,rows=struct.unpack_from('<II',entry)
        count=columns*rows
        assert (columns,rows)==((6,8),(5,42),(5,8))[i]
        pointers=struct.unpack_from('<'+'I'*count,entry,8)
        assert pointers[0]==8+4*count
        assert all(8+4*count<=p<size for p in pointers)
        strings=[bytes(entry[p:entry.index(0,p)]) for p in pointers]
        yield i,start,entry[:8+4*count],pointers,strings,x,y


def install(rom,original,files,project):
    filename='data/map_text.pac';start,size=files[filename]
    source=original[start:start+size]
    translations=json.loads((project/'map_translations.json').read_text(encoding='utf8'))
    if '--full-draft' in sys.argv:
        draft=json.loads((project/'full_draft_map.json').read_text(encoding='utf8'))
        draft.update(translations)
        translations=draft
    out=bytearray(source[:64]);changed=0
    for i,start,head,pointers,strings,x,y in entries(source):
        entry=bytearray(head)
        for j,raw in enumerate(strings):
            ja=raw.decode('shift_jis');text=translations.get(ja)
            if text is not None:
                columns=struct.unpack_from('<I',head)[0]
                field=j%columns
                if field==1:
                    lines=textwrap.wrap(text,32,break_long_words=False,break_on_hyphens=False)
                    assert len(lines)<=11,(i,j,len(lines))
                    assert all(len(line)<=32 for line in lines)
                    assert ' '.join(lines)==' '.join(text.split())
                    text='\n'.join(lines)
                elif field==2 and i in (1,2):
                    text='\n'.join(textwrap.wrap(text,55,break_long_words=False,break_on_hyphens=False))
                en=text.encode('ascii')
            else:en=raw
            assert b'\0' not in en
            changed+=en!=raw
            struct.pack_into('<I',entry,8+4*j,len(entry))
            entry+=en+b'\0'
        struct.pack_into('<4I',out,16+16*i,len(out),len(entry),x,y)
        out+=entry
    struct.pack_into('<I',out,8,len(out))
    for old,new in zip(entries(source),entries(out)):
        assert old[2][:8]==new[2][:8] and len(old[4])==len(new[4])
        for ja,en in zip(old[4],new[4]):
            if ja.isascii():assert ja==en
    install_file(rom,files,filename,out)
    print('Map repack:',len(source),'->',len(out),'bytes;',changed,'translated fields')
