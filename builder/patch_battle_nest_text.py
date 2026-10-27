"""Translate complete battle-name, egg-name and battle-callout tables."""
import json
import struct
from PIL import Image,ImageFilter,ImageFont
from patch_battle_readability import decode,encode,textmask
from repack_script import install_file


def install(rom,files,project):
    dictionaries=json.loads((project/'battle_nest_names.json').read_text(encoding='utf8'))
    # Dungeon HUD labels are fixed 32-byte fields, separate from map captions.
    fn='data/dungeon00.krd';a,n=files[fn];dungeon=bytearray(rom[a:a+n])
    labels=json.loads((project/'dungeon_names_source.json').read_text(encoding='utf8'))
    assert len(labels)==53
    for row in labels:
        p=row['offset'];old=row['ja'].encode('shift_jis');new=row['en'].encode('ascii')
        assert dungeon[p:p+32]==old.ljust(32,b'\0') and len(new)<32
        assert dungeon[p-16:p-8]==struct.pack('<II',1,16)
        dungeon[p:p+32]=new.ljust(32,b'\0')
    install_file(rom,files,fn,dungeon)
    for fn,column in [('dragon_base.csv',13),('spforce.csv',0),('eggpack.csv',2)]:
        source=(project/'extracted_rom/nitrofs/data'/fn).read_bytes()
        lines=source.decode('shift_jis').splitlines(keepends=True)
        count=0
        for i,line in enumerate(lines):
            if line.startswith('#'):continue
            fields=line.split(',')
            if len(fields)>column and fields[column] in dictionaries[fn]:
                original=fields.copy()
                fields[column]=dictionaries[fn][fields[column]]
                assert all(a==b for j,(a,b) in enumerate(zip(original,fields)) if j!=column)
                lines[i]=','.join(fields);count+=1
        assert count==len(dictionaries[fn]),(fn,count)
        install_file(rom,files,'data/'+fn,''.join(lines).encode('shift_jis'))

    # The large Dragon Force splash names are a second, image-based copy.
    fn='data/btl_u_DFname.cim';a,n=files[fn];t=bytearray(rom[a:a+n])
    im=decode(t);names=list(dictionaries['spforce.csv'].values())
    assert im.size==(160,len(names)*32)
    pal=struct.unpack_from('<16H',t,32)
    dark=min(range(1,16),key=lambda i:sum((pal[i]>>s)&31 for s in (0,5,10)))
    light=max(range(1,16),key=lambda i:sum((pal[i]>>s)&31 for s in (0,5,10)))
    for row,name in enumerate(names):
        size=17
        while ImageFont.truetype('C:/Windows/Fonts/arialbd.ttf',size).getlength(name)>154:size-=1
        assert size>=11,(name,size)
        m=textmask(160,32,name,size).point(lambda v:255 if v>=96 else 0)
        tile=Image.new('L',(160,32),0)
        tile.paste(dark,(0,0,160,32),m.filter(ImageFilter.MaxFilter(3)))
        tile.paste(light,(0,0,160,32),m)
        im.paste(tile,(0,row*32))
    encoded=encode(t,im);assert decode(encoded).tobytes()==im.tobytes()
    install_file(rom,files,fn,encoded)

    fn='data/bm_body.krd';a,n=files[fn];source=bytes(rom[a:a+n])
    count=struct.unpack_from('<I',source,4)[0]//8
    translated=json.loads((project/'battle_callouts_english.json').read_text())
    speakers={'トント':'Tonto','アヤカ':'Ayaka','宮守り様':'Shrine Guardian','トレヴァー':'Trevor',
              'ユージーン':'Eugene','帝兵':'Imperial Soldier','牙王':'Fang King','シャオトゥ':'Xiaotu',
              'タチヤナ':'Tatyana','逆炎':'Reverse Flame','サリカス兵':'Sarikas Soldier','アルベルト':'Albert',
              '盗賊':'Bandit','セルジオ':'Sergio','ライラ':'Lyla','女王':'Queen','応竜':'Yinglong',
              'リヴァイアサン':'Leviathan','ウロボロス':'Ouroboros','ケツアルカトル':'Quetzalcoatl',
              'ティアマト':'Tiamat','ファフニール':'Fafnir','オロチ':'Orochi','竜切りジャック':'Dragon Slayer Jack',
              'ウラジミール':'Vladimir','ヨーゼフ':'Josef','鉄面ゴーリー':'Ironmask Gory',
              'ヤナガ':'Yanaga','サンデーナマズ':'Sunday Catfish','王子ざうるす':'Prince Saurus',
              'ドラゴン仙人２！':'Dragon Sage 2!','':''}
    out=bytearray(source[:count*8]);report=[]
    for i in range(count):
        tag,p=struct.unpack_from('<II',source,i*8)
        end=struct.unpack_from('<I',source,(i+1)*8+4)[0] if i+1<count else len(source)
        name,ja,empty=source[p:end].split(b'\0');assert empty==b''
        en=translated[str(i)]
        assert ja.decode('shift_jis').count('%s')==en.count('%s')
        lines=['']
        for word in en.split():
            candidate=(lines[-1]+' '+word).strip()
            if len(candidate.replace('%s','X'*16))>33 and lines[-1]:lines.append(word)
            else:lines[-1]=candidate
        assert len(lines)<=2 and max(len(s.replace('%s','X'*16)) for s in lines)<=33,(i,lines)
        struct.pack_into('<II',out,i*8,tag,len(out))
        out+=speakers[name.decode('shift_jis')].encode('ascii')+b'\0'+'\n'.join(lines).encode('ascii')+b'\0'
        report.append(dict(id=i,name=speakers[name.decode('shift_jis')],text='\n'.join(lines)))
    assert len(report)==len(translated)==261
    install_file(rom,files,fn,out)
    (project/'battle_callouts_built.json').write_text(json.dumps(report,indent=2)+'\n')
    arm,_,_,size=struct.unpack_from('<4I',rom,0x20)
    for ja,en in [('フラト','Frat'),('メゾピ','Mezopi'),('アクト','Act'),('フォルテ','Forte'),('のタマゴ',' Egg')]:
        old=ja.encode('shift_jis')+b'\0';new=en.encode()+b'\0';area=bytes(rom[arm:arm+size])
        assert len(new)<=len(old) and area.count(old)==1
        p=arm+area.index(old);rom[p:p+len(old)]=new.ljust(len(old),b'\0')
    print('Translated 101 dragon names, 101 force names/splashes, 6 eggs, 261 battle callouts')
