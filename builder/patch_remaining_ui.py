"""Native chapter cards and battle labels missed by the text-table pass."""
import struct
from PIL import Image, ImageFilter
from patch_battle_readability import pac_entries, pack, decode, encode, textmask
from repack_script import install_file
from pixel_ui import mask as pixel_mask


def install(rom, files, project):
    name = 'data/evtitle_cim.pac'
    a,n = files[name]
    entries = list(pac_entries(bytes(rom[a:a+n])))
    labels = ['Prelude'] + ['Movement '+s for s in ['I','II','III','IV','V','VI','VII']] + ['Encore']
    preview = Image.new('L', (256, 9*64))
    for asset,label in enumerate(labels, 1):
        i,t,x,y = entries[asset]
        assert struct.unpack_from('<HH',t,2) == (128,32)
        # These CX images are two consecutive 64x32 OBJ sprites, not a
        # single 128-pixel-wide tile grid. Palette is shared at runtime.
        mask = textmask(128,32,label,18).point(lambda v: 15 if v >= 128 else 0)
        tiled = Image.new('L',(64,64))
        tiled.paste(mask.crop((0,0,64,32)),(0,0))
        tiled.paste(mask.crop((64,0,128,32)),(0,32))
        struct.pack_into('<HH',t,2,64,64)
        t = encode(t,tiled)
        struct.pack_into('<HH',t,2,128,32)
        entries[asset] = i,t,x,y
        preview.paste(mask.point(lambda v:v*17).resize((256,64)),(0,(asset-1)*64))
    preview.save(project/'qa/chapter-cards-english.png')
    install_file(rom,files,name,pack(entries))

    name = 'data/town_cim.pac'
    a,n = files[name]
    entries = list(pac_entries(bytes(rom[a:a+n])))
    labels = ['Arena Battle','Buy','Ask for Info','Other Info','Battle Info','Go to Nest','Save','Sell','Dragon Info']
    for asset,label in enumerate(labels,28):
        i,t,x,y=entries[asset]
        assert struct.unpack_from('<HH',t,2)==(96,32)
        struct.pack_into('<HH',t,2,32,96)
        raw=decode(t); logical=Image.new('L',(96,32))
        for col in range(3):logical.paste(raw.crop((0,col*32,32,col*32+32)),(col*32,0))
        pal=struct.unpack_from('<16H',t,48)
        brightness=[sum((v>>s)&31 for s in (0,5,10)) for v in pal]
        dark=min(range(1,16),key=lambda k:brightness[k])
        light=max(range(1,16),key=lambda k:brightness[k])
        mask=textmask(88,18,label,11)
        for yy in range(18):
            for xx in range(88):logical.putpixel((4+xx,2+yy),dark if mask.getpixel((xx,yy))>=128 else light)
        for col in range(3):raw.paste(logical.crop((col*32,0,col*32+32,32)),(0,col*32))
        t=encode(t,raw);struct.pack_into('<HH',t,2,96,32)
        entries[asset]=i,t,x,y
    install_file(rom,files,name,pack(entries))

    name = 'data/namee.pac'
    a,n = files[name]
    entries = list(pac_entries(bytes(rom[a:a+n])))
    i,t,x,y = entries[2]
    im = decode(t)
    # Each 48x16 button is stored as three successive 16x16 strips.
    logical = Image.new('L',(48,144))
    for row in range(9):
        for col in range(3):
            top=row*48+col*16
            logical.paste(im.crop((0,top,16,top+16)),(col*16,row*16))
    palette = struct.unpack_from('<16H',t,32)
    brightness = [sum((v>>s)&31 for s in (0,5,10)) for v in palette]
    dark=min(range(1,16),key=lambda k:brightness[k])
    light=max(range(1,16),key=lambda k:brightness[k])
    for row,label in [(0,'HIRA'),(1,'KATA'),(2,'ABC123'),(3,'KANJI'),(4,'SYMBOL'),(5,'SPACE'),(7,'OK')]:
        height=24 if row==7 else 12
        mask=pixel_mask(42,height,label)
        for yy in range(height):
            for xx in range(42):
                logical.putpixel((3+xx,row*16+2+yy),dark if mask.getpixel((xx,yy))>=128 else light)
    for row in range(9):
        for col in range(3):
            im.paste(logical.crop((col*16,row*16,col*16+16,row*16+16)),(0,row*48+col*16))
    entries[2]=i,encode(t,im),x,y
    install_file(rom,files,name,pack(entries))

    name = 'data/btl2cim.pac'
    a,n = files[name]
    entries = list(pac_entries(bytes(rom[a:a+n])))
    i,t,x,y = entries[27]
    im = decode(t)
    labels = ['Attack','Defend','DF','Charge','Change','Purify','Taunt','Down','Dark','Stun','Counter']
    for row,label in enumerate(labels):
        mask = textmask(48,16,label,10).point(lambda v:255 if v>=128 else 0)
        outline = mask.filter(ImageFilter.MaxFilter(3))
        tile = Image.new('L',(48,16),0)
        tile.paste(5,(0,0,48,16),outline)
        tile.paste(1,(0,0,48,16),mask)
        im.paste(tile,(0,row*16))
    entries[27] = i,encode(t,im),x,y
    i,t,x,y = entries[18]
    im = decode(t)
    # Original EXP caption occupies this solid brown region of the result panel.
    mask = textmask(68,14,'EXP Earned',10)
    for yy in range(14):
        for xx in range(68):
            im.putpixel((68+xx,33+yy),15 if mask.getpixel((xx,yy))>=128 else 4)
    entries[18] = i,encode(t,im),x,y
    install_file(rom,files,name,pack(entries))

    arm,_,_,size = struct.unpack_from('<4I',rom,0x20)
    old = '獲得賞金'.encode('shift_jis')+b'\0'
    area = bytes(rom[arm:arm+size])
    assert area.count(old)==1
    at = arm+area.index(old)
    rom[at:at+len(old)] = b'Gold\0'.ljust(len(old),b'\0')
    captions={
        'チーム%s':'Team %s','マスター':'Master','残り%sターン':'%s turns',
        'トータル成績':'Total Record','%5d勝 %5d敗 %5d分':'%5dW %5dL %5dD',
        '%3d勝 %3d敗 %3d分':'%3dW %3dL %3dD',
        '%-10s %3d勝 %3d敗 %3d分':'%-10s %3dW %3dL %3dD','少年':'Boy',
        '風属性':'Wind','地属性':'Earth','光属性':'Light','水属性':'Water','闇属性':'Dark','無属性':'None','火属性':'Fire',
        'No.%03d 種族：%s':'No.%03d Type:%s','名前：%s':'Name:%s',
        'ドラゴンフォース：%s':'Dragon Force:%s','消費FP：%2d':'FP:%2d',
        '挑発':'Lure','浄化':'Heal','ねむり':'Sleep','しびれ':'Stun',
        '防御力':'DEF','攻撃力':'ATK','素早さ':'Speed','属性変化':'Element',
        'カウンター':'Counter','復活オーラ':'Revive','かなしばり':'Paralyze',
        'カマイタチ':'Windcut','防御力アップ':'DEF Up','素早さダウン':'Speed Down',
        '素早さアップ':'Speed Up','チャージ封印':'Charge Lock','攻撃力ダウン':'ATK Down',
        'チェンジ封印':'Change Lock','防御力ダウン':'DEF Down','フォース封印':'Force Lock',
        '強制チェンジ':'Force Swap','攻撃力アップ':'ATK Up','攻撃力トレード':'ATK Trade',
        '防御力トレード':'DEF Trade','ダブルアタック':'Double Hit','逃げられなかった':'Escape failed',
        '所持金 %5dＧ':'Gold %5dG','メダル %5d枚':'Medal %5d',
        'タマゴ':'Egg','名前順':'Name','属性順':'Type','種族順':'Race','レベル順':'Level','タマゴ順':'Egg',
        '＜%sページ目＞':'Page %s','チームを選んでください':'Select a team.',
        ' ドラゴンを選択してください。':'Select a dragon.',
        '  変更する場所を選んで下さい':'Choose a destination.',
        'どの順に並び替えますか？':'Choose sort order.',
        '店員':'Shop','ネスト係員':'Nest Staff','アヤカ':'Ayaka',
        'タマゴを選んでください':'Select an egg.',
        'ドラゴンスコアを選んでください':'Select a Dragon Score.',
        '？のスコア':'? Score',
    }
    for ja,en in captions.items():
        old=ja.encode('shift_jis')+b'\0';new=en.encode('ascii')+b'\0'
        assert len(new)<=len(old),(ja,en)
        area=bytes(rom[arm:arm+size]);positions=[];cursor=0
        while True:
            pos=area.find(old,cursor)
            if pos<0:break
            # Only patch complete strings, never suffixes of other strings.
            if pos%4==0 or area[pos-1]==0:positions.append(pos)
            cursor=pos+len(old)
        assert positions,ja
        for pos in positions:rom[arm+pos:arm+pos+len(old)]=new.ljust(len(old),b'\0')
    print('Localized 9 chapter cards, 11 battle overlays and result captions')

