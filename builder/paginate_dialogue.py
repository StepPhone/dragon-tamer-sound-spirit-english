"""Word-wrap the story font and add native wait/clear continuation pages.

Reverse-engineered ARM9: 0209e458 appends string (op4); 0209e4c8
waits for input (op6), then 0209dcb4 clears body text; op7 clears
without input. Op22 appends the player name, op5 appends a newline.
The body selects font size 10 at 020a0724 (five-pixel ASCII advances).
All 441 source events are linear: reject any branch opcode 0..3.
"""
import json
import struct
import unicodedata

COLS = 33  # 165 pixels, inside the portrait dialogue's right edge
NAME_COLS = 12  # reserve 60 pixels for a six-character Japanese name


def commands(entry):
    start, count, _ = struct.unpack_from('<3I', entry[2])
    return [struct.unpack_from('<4I', entry[2], start + i*16) for i in range(count)]


def paginate(data, project):
    from repack_script import entries
    out = bytearray(data[:16+441*16])
    reports = []
    for e in entries(data):
        aid, _, _, _, original_strings, x, y = e
        old = commands(e)
        assert all(c[0] not in range(4) for c in old), ('Branch requires relocation', aid)
        strings = list(original_strings)
        new = []
        mapping = []
        changes = []
        row = col = 0
        last = ''
        timed = False

        def extra_text(text):
            sid = len(strings)
            strings.append(text.encode('ascii'))
            new.append((4, sid, 0, 0))
            return sid

        def page():
            nonlocal row, col, last
            if timed:
                new.extend([(8, 180, 0, 0), (7, 0, 0, 0)])
            else:
                new.append((6, 0, 0, 0))
            row = col = 0
            last = ''

        for ci, c in enumerate(old):
            op, sid, _, _ = c
            # Use the event's existing interaction style for continuations.
            boundary = next((v[0] for v in old[ci:] if v[0] in (6, 7)), 6)
            timed = boundary == 7
            if op == 4:
                text = unicodedata.normalize('NFKC', strings[sid].decode('shift_jis')).replace('。', '.')
                assert text.isascii(), (aid, sid, text)
                words = [part for word in text.split() for part in
                         [word[i:i+COLS] for i in range(0, len(word), COLS)]]
                segments = ['']
                for wi, word in enumerate(words):
                    # Preserve punctuation joins while separating adjacent words.
                    space = bool(col and (wi or text[:1].isspace() or
                                 (last and last[-1].isalnum() and word[0].isalnum())))
                    if col + len(word) + int(space) > COLS:
                        if row == 0:
                            segments[-1] += '\n'
                            row, col, space = 1, 0, False
                        else:
                            segments.append('')
                            row, col, space = 0, 0, False
                    # No word in the current English data exceeds a full line.
                    assert len(word) <= COLS, (aid, sid, word)
                    segments[-1] += (' ' if space else '') + word
                    col += len(word) + int(space)
                    last = word
                if text[-1:].isspace() and col < COLS:
                    segments[-1] += ' '
                    col += 1
                    last = ' '
                final_state = row, col, last
                # An initial empty segment means the previous fragment filled
                # the page. Clear before executing this original instruction.
                if not segments[0] and len(segments) > 1:
                    page()
                    segments.pop(0)
                strings[sid] = segments[0].encode('ascii')
                mapping.append(len(new))
                new.append(c)
                page_ids = [sid]
                for segment in segments[1:]:
                    page()
                    page_ids.append(extra_text(segment))
                row, col, last = final_state
                assert ''.join(text.split()) == ''.join(''.join(segments).split()), (aid, sid)
                changes.append(dict(string_id=sid, original_text=text, pages=segments, page_string_ids=page_ids))
            else:
                if op == 22:
                    if col + NAME_COLS > COLS:
                        if row:
                            page()
                        else:
                            extra_text('\n')
                            row, col = 1, 0
                    col += NAME_COLS
                    last = 'NAME'
                mapping.append(len(new))
                new.append(c)
                if op in (6, 7) or (op == 12 and sid in (4, 5)):
                    row = col = 0
                    last = ''
                elif op == 5:
                    if row:
                        page()
                    else:
                        row, col, last = 1, 0, ''
        assert [new[i] for i in mapping] == old
        start = 12 + 4*len(strings)
        entry = bytearray(struct.pack('<3I', start, len(new), len(strings)))
        entry += bytes(4*len(strings))
        entry += b''.join(struct.pack('<4I', *c) for c in new)
        for sid, text in enumerate(strings):
            struct.pack_into('<I', entry, 12+4*sid, len(entry))
            entry += text + b'\0'
        struct.pack_into('<4I', out, 16+16*aid, len(out), len(entry), x, y)
        out += entry
        reports.append(dict(asset_id=aid, original_command_positions=mapping,
                            original_string_count=len(original_strings),
                            added_commands=len(new)-len(old), dialogue=changes))
    struct.pack_into('<I', out, 8, len(out))
    (project/'dialogue_pagination.json').write_text(json.dumps(reports, indent=2)+'\n', encoding='utf8')
    validate(data, out, reports)
    print('Dialogue layout:', sum(len(r['dialogue']) for r in reports),
          'strings;', sum(r['added_commands'] for r in reports), 'continuation instructions')
    return bytes(out)


def validate(original, built, reports):
    from repack_script import entries
    for a, b, report in zip(entries(original), entries(built), reports):
        old, new = commands(a), commands(b)
        positions = report['original_command_positions']
        assert len(positions) == len(old)
        assert positions == sorted(set(positions))
        assert [new[p] for p in positions] == old
        injected = [c for i, c in enumerate(new) if i not in set(positions)]
        assert all(c == (6, 0, 0, 0) or c == (7, 0, 0, 0) or
                   c == (8, 180, 0, 0) or
                   (c[0] == 4 and len(a[4]) <= c[1] < len(b[4]) and c[2:] == (0, 0))
                   for c in injected)
        for change in report['dialogue']:
            texts = [b[4][sid].decode('ascii') for sid in change['page_string_ids']]
            assert texts == change['pages']
            assert ''.join(''.join(texts).split()) == ''.join(change['original_text'].split())
        row = col = 0
        for c in new:
            if c[0] == 4:
                text = b[4][c[1]].decode('ascii')
                assert all(len(line) <= COLS for line in text.split('\n'))
                assert text.count('\n') <= 1
                for ch in text:
                    if ch == '\n':
                        row, col = row+1, 0
                    elif ch not in '<>':
                        col += 1
                    assert row <= 1 and col <= COLS, (a[0], c, row, col)
            elif c[0] == 22:
                col += NAME_COLS
                assert row <= 1 and col <= COLS
            elif c[0] in (6, 7) or (c[0] == 12 and c[1] in (4, 5)):
                row = col = 0
            elif c[0] == 5:
                row, col = row+1, 0
