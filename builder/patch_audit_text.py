"""Player-facing text groups found by the full ROM audit."""
import csv,io,json,struct,textwrap,re
from repack_script import install_file

SCORES=['Star','Fate','School','Ramen','Bee','Chibi-Robo','Frog','Klonoa','Buster','Flame','Droplet','Tornado','Earth','Sparkle','Darkness','Haze','Holy','Fluffy','Shadow','Flight','Courage','Joy','Jewel']
RUNTIME={
0x1081e8:"Name",0x1081fc:"EL",
0x1080e0:"DK",0x1080e4:"ER",0x1080e8:"LT",0x1080ec:"WT",
0x1080f0:"WN",0x108100:"FI",0x108104:"NA",
0x102a90:'The dragon is not in the mood.',0x102ab0:'Please play the sound again.',
0x1041f8:'Model Test Menu',0x104210:'Model Test',0x10421c:'BG Test',
0x104be0:'Pre-battle event',0x104bf4:'Post-battle event',0x104c34:'[FRONT]',0x104c64:'[BENCH]',
0x104c70:'Stage:%2d/%2d [%s]',0x104d44:'%s  OFF  [ON]\n',0x104d58:'%s [OFF]  ON\n',
0x105114:'No floor name entered.',0x1051a0:'A switch is here. Press it?',
0x106350:'Morph',0x106390:'? Shift',0x106510:'%c%x%y%s effects',
0x106564:'To Fire',0x10656c:'To Aqua',0x106574:'To Wind',0x10657c:'To Soil',0x106584:'To Lite',0x10658c:'To Dark',0x106594:'To None',
0x1066ac:'{Invalid}',0x106bb4:'Use [%s]?',0x106bcc:'[%s] would have\nno effect now.',0x106bf8:'Discarded [%s].',
0x106c10:'[%s]:\nUse [%s]?',0x106c30:'[%s]:\n[%s] has no effect.',
0x107bb4:'Poison',0x107be8:'Asleep',0x107c00:'With breath',0x107c10:'In one hit',0x107c20:'Wind cut',0x107c30:'Paralyzed',
0x107c40:'With drain',0x107c70:'With a counter',0x107c84:'Poison/wind cut',0x107c98:'Asleep/paralyzed',
0x107cc0:'Before other dragons',0x107d0c:'After all other dragons',0x107d74:'%s dragons in dungeon',
0x107d98:'All',0x107dac:'Beat',0x107dc0:'None',0x107dc8:'Boss requirement:\n',0x107de0:'%s dragons in dungeon\n',
0x107dfc:'Entry requirement:\n',0x107e1c:' egg-born',0x107e30:' type',0x107e38:'Level <= %s',0x107e48:'Up to %s',0x107e54:'Team'}

def install(rom,files,project):
    report=[]
    # Preserve all CSV structure except the intended display cells.
    fn='data/archives.csv';a,n=files[fn];source=bytes(rom[a:a+n]).decode('cp932')
    originals=[]
    for line in source.splitlines():
        cells=line.split(',')
        if len(cells)>2 and cells[0].isdigit() and re.search('[ぁ-龯]',cells[2]):
            if cells[2] not in originals:originals.append(cells[2])
    assert len(originals)==23
    for ja,en in sorted(zip(originals,SCORES),key=lambda item:-len(item[0])):source=source.replace(ja,en+' Score')
    assert all(not re.search('[ぁ-龯]',line.split(',')[2]) for line in source.splitlines() if line.split(',')[0].isdigit())
    install_file(rom,files,fn,source.encode('cp932'))
    report.append({'file':fn,'active_titles':23})
    fn='data/endroll.csv';a,n=files[fn];source=bytes(rom[a:a+n]).decode('cp932')
    credits=json.loads((project/'credits_english.json').read_text(encoding='utf8'))
    for ja,en in sorted(credits.items(),key=lambda item:-len(item[0])):
        assert ja in source,ja
        source=source.replace(ja,en)
    assert not re.search('[ぁ-龯]',source)
    install_file(rom,files,fn,source.encode('cp932'))
    report.append({'file':fn,'translated_fields':66,'note':'Some personal-name readings are provisional; see credits review notes.'})
    # Native loader copies this quoted field to a 256-byte buffer at object+0x60.
    # Its next field begins at +0x160. Keep the entire description below 256.
    descriptions=(project/'encyclopedia_english.txt').read_text(encoding='utf8').splitlines()
    assert len(descriptions)==101 and all(s.isascii() and s for s in descriptions)
    wrapped=['\n'.join(textwrap.wrap(s,24,break_long_words=False,break_on_hyphens=False)) for s in descriptions]
    assert all(len(s.encode())<256 and len(s.splitlines())<=11 for s in wrapped)
    assert all(' '.join(s.split())==original for s,original in zip(wrapped,descriptions))
    fn='data/dragon_chara.csv';a,n=files[fn]
    rows=list(csv.reader(io.StringIO(bytes(rom[a:a+n]).decode('cp932'))))
    assert len(rows)==101 and all(len(r)==1 for r in rows)
    # Quoting is mandatory: this game's loader interprets unquoted newlines as
    # record delimiters. Use the original quoted multiline record convention.
    data=''.join('"'+s+'"\r\n' for s in wrapped).encode('ascii')
    assert [r[0] for r in csv.reader(io.StringIO(data.decode()))]==wrapped
    install_file(rom,files,fn,data)
    report.append({'file':fn,'descriptions':101,'max_bytes':max(map(len,wrapped)),'columns':24})
    (project/'qa/full_audit/encyclopedia_draft.json').write_text(json.dumps(descriptions,indent=2),encoding='utf8')
    arm,_,load,size=struct.unpack_from('<4I',rom,0x20)
    for p,en in RUNTIME.items():
        end=rom.index(0,arm+p);old=bytes(rom[arm+p:end]);capacity=((len(old)+1+3)//4)*4
        assert re.search('[ぁ-龯ｦ-ﾟ]',old.decode('cp932')),(hex(p),old)
        assert not any(rom[end:arm+p+capacity]),hex(p)
        new=en.encode()+b'\0'
        assert len(new)<=capacity,(hex(p),en,capacity)
        assert re.findall(rb'%[a-z0-9]+',old)==re.findall(rb'%[a-z0-9]+',new),(old,new)
        rom[arm+p:arm+p+capacity]=new.ljust(capacity,b'\0')
        report.append({'offset':hex(p),'ja':old.decode('cp932'),'en':en})
    (project/'qa/full_audit/text_patch_manifest.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
    print('Translated 23 score titles and',len(RUNTIME),'runtime/debug labels')


