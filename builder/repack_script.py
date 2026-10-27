"""Repack script strings without changing any event instructions or string IDs."""
import collections
import json
import struct
import sys


def entries(data):
    assert data[:4] == b'PK\0\1'
    count,total = struct.unpack_from('<II',data,4)
    assert count == 441 and total == len(data)
    for i in range(count):
        start,size,extra1,extra2 = struct.unpack_from('<4I',data,16+16*i)
        entry = data[start:start+size]
        command_start,command_count,string_count = struct.unpack_from('<3I',entry)
        assert command_start == 12+4*string_count
        pointers = struct.unpack_from('<'+'I'*string_count,entry,12)
        text_start = command_start+16*command_count
        assert not pointers or pointers[0] == text_start
        strings = [bytes(entry[p:entry.index(0,p)]) for p in pointers]
        assert all(text_start<=p<size for p in pointers)
        yield i,start,entry[:text_start],pointers,strings,extra1,extra2


def repack(original,patched,project):
    old = list(entries(original)); current = list(entries(patched))
    reviewed = collections.defaultdict(set)
    for source,built in zip(old,current):
        for ja,en in zip(source[4],built[4]):
            if ja!=en and en.isascii() and en:
                reviewed[ja].add(en)
    shared = {ja:next(iter(options)) for ja,options in reviewed.items() if len(options)==1}
    completion=json.loads((project/'story_completion.json').read_text(encoding='utf-8'))
    if '--full-draft' in sys.argv:
        draft=json.loads((project/'full_draft_story.json').read_text(encoding='utf8'))
        draft.update(completion)
        completion=draft
    overrides={ja.encode('shift_jis'):en.encode('ascii') for ja,en in completion.items()}
    out=bytearray(original[:16+441*16]); manifest=[]; reused=0; added=0
    for source,built in zip(old,current):
        i,old_start,head,pointers,strings,x,y=source
        assert built[2] == head, ('Changed script instructions',i)
        entry=bytearray(head)
        for j,(pointer,ja,en) in enumerate(zip(pointers,strings,built[4])):
            # The engine compares this exact SJIS sentinel to insert the saved
            # player name. Translating its glyphs into ASCII disables substitution.
            if ja == '＊＊＊＊＊'.encode('shift_jis'):
                en = ja
            elif ja in overrides:
                en=overrides[ja];added+=1
            elif en==ja and ja in shared:
                en=shared[ja];reused+=1
            assert b'\0' not in en
            new_offset=len(entry)
            struct.pack_into('<I',entry,12+4*j,new_offset)
            entry+=en+b'\0'
            manifest.append(dict(asset_id=i,string_id=j,source_offset=old_start+pointer,
                                 output_offset=len(out)+new_offset,
                                 ja=ja.decode('shift_jis'),text=en.decode('shift_jis'),
                                 translated=ja!=en and en.isascii()))
        struct.pack_into('<4I',out,16+16*i,len(out),len(entry),x,y)
        out+=entry
    struct.pack_into('<I',out,8,len(out))
    rebuilt=list(entries(out))
    for source,built in zip(old,rebuilt):
        command_start=struct.unpack_from('<I',source[2])[0]
        assert source[2][command_start:]==built[2][command_start:]
        assert len(source[4])==len(built[4])
    (project/('script_manifest_full_draft.json' if '--full-draft' in sys.argv else 'script_manifest.json')).write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('Script repack:',len(original),'->',len(out),'bytes;',reused,'reviewed copies,',added,'completion entries')
    if '--full-draft' in sys.argv:
        from paginate_dialogue import paginate
        return paginate(bytes(out), project)
    return bytes(out)


def install(rom,original,files,project):
    start,size=files['data/new_script_dat.pac']
    data=repack(original[start:start+size],bytes(rom[start:start+size]),project)
    install_file(rom,files,'data/new_script_dat.pac',data)


def install_file(rom,files,filename,data):
    start,size=files[filename]
    fat,fat_size=struct.unpack_from('<II',rom,0x48)
    records=[(p,*struct.unpack_from('<II',rom,p)) for p in range(fat,fat+fat_size,8)]
    matches=[p for p,a,b in records if (a,b)==(start,start+size)]
    assert len(matches)==1
    if len(data)>size:
        # A later patch may shrink a previously relocated resource. Its old
        # tail remains occupied; the used-ROM watermark prevents reusing it.
        start=(max(max(b for p,a,b in records),struct.unpack_from('<I',rom,0x80)[0])+511)&~511
        assert start+len(data)<=len(rom)
        assert all(v in (0,255) for v in rom[start:start+len(data)])
    rom[start:start+len(data)]=data
    struct.pack_into('<II',rom,matches[0],start,start+len(data))
    used=max(struct.unpack_from('<I',rom,0x80)[0],start+len(data))
    struct.pack_into('<I',rom,0x80,used)
    crc=0xffff
    for byte in rom[:0x15e]:
        crc^=byte
        for _ in range(8):crc=(crc>>1)^(0xa001 if crc&1 else 0)
    struct.pack_into('<H',rom,0x15e,crc)
