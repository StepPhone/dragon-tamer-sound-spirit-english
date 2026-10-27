#!/usr/bin/env python3
"""Build the early Dragon Tamer English patch without modifying the Japanese source."""
from __future__ import annotations

import hashlib
import json
import struct
import sys
import zlib

from PIL import Image, ImageDraw, ImageFont
from pathlib import Path
from zipfile import BadZipFile, ZipFile

ROOT = Path(__file__).resolve().parents[1]
PROJECT = Path(__file__).resolve().parent
SOURCE = ROOT / "Dragon Tamer - Sound Spirit (Japan).nds"
SOURCE_ZIP = ROOT / "Dragon Tamer - Sound Spirit (Japan).zip"
OUTPUT = ROOT / "Dragon Tamer - Sound Spirit (English WIP).nds"
PATCH = PROJECT / "release" / "Dragon Tamer - Sound Spirit (English WIP).bps"
FULL_DRAFT = "--full-draft" in sys.argv
if FULL_DRAFT:
    OUTPUT = ROOT / "Dragon Tamer - Sound Spirit (English Full Text Draft).nds"
    PATCH = PROJECT / "release" / "Dragon Tamer - Sound Spirit (English Full Text Draft).bps"
TRANSLATIONS = PROJECT / "translations.json"
EXTRA_TRANSLATIONS = PROJECT / "extra_translations.json"
MORE_TRANSLATIONS = PROJECT / "more_translations.json"
MENU_TRANSLATIONS = PROJECT / "menu_translations.json"
SHOP_NEST_TRANSLATIONS = PROJECT / "shop_nest_en.json"
ITEM_NAMES_TRANSLATIONS = PROJECT / "item_names_en.json"
ITEM_DESCRIPTIONS_TRANSLATIONS = PROJECT / "item_descriptions_en.json"
DRAGON_FORCE_TRANSLATIONS = PROJECT / "dragon_force_descriptions_en.json"
PROLOGUE_TRANSLATIONS = PROJECT / "prologue_en_offsets.json"
CHAPTER1_TRANSLATIONS = PROJECT / "chapter1_en_offsets.json"
CHAPTER2_TRANSLATIONS = PROJECT / "chapter2_en_offsets.json"
CHAPTER3_TRANSLATIONS = PROJECT / "chapter3_en_offsets.json"
CHAPTER4_TRANSLATIONS = PROJECT / "chapter4_en_offsets.json"
CHAPTER5_TRANSLATIONS = PROJECT / "chapter5_en_offsets.json"
CHAPTER6_TRANSLATIONS = PROJECT / "chapter6_en_offsets.json"
CHAPTER7_TRANSLATIONS = PROJECT / "chapter7_en_offsets.json"
CHAPTER8_TRANSLATIONS = PROJECT / "chapter8_en_offsets.json"
CHAPTER9_TRANSLATIONS = PROJECT / "chapter9_en_offsets.json"
CHAPTER10_TRANSLATIONS = PROJECT / "chapter10_en_offsets.json"
CHAPTER11_TRANSLATIONS = PROJECT / "chapter11_en_offsets.json"
CHAPTER12_TRANSLATIONS = PROJECT / "chapter12_en_offsets.json"
CHAPTER13_TRANSLATIONS = PROJECT / "chapter13_en_offsets.json"
CHAPTER14_TRANSLATIONS = PROJECT / "chapter14_en_offsets.json"
CHAPTER15_TRANSLATIONS = PROJECT / "chapter15_en_offsets.json"
CHAPTER16_TRANSLATIONS = PROJECT / "chapter16_en_offsets.json"
CHAPTER17_TRANSLATIONS = PROJECT / "chapter17_en_offsets.json"
CHAPTER18_TRANSLATIONS = PROJECT / "chapter18_en_offsets.json"
CHAPTER19_TRANSLATIONS = PROJECT / "chapter19_en_offsets.json"
CHAPTER20_TRANSLATIONS = PROJECT / "chapter20_en_offsets.json"
CHAPTER21_TRANSLATIONS = PROJECT / "chapter21_en_offsets.json"
CHAPTER22_TRANSLATIONS = PROJECT / "chapter22_en_offsets.json"
CHAPTER23_TRANSLATIONS = PROJECT / "chapter23_en_offsets.json"
INTERFACE_TRANSLATIONS = PROJECT / "interface_translations.json"
HELP_TEXT_TRANSLATIONS = PROJECT / "help_text_translations.json"


def read_source_bytes() -> bytes:
    if SOURCE.is_file():
        return SOURCE.read_bytes()
    if not SOURCE_ZIP.is_file():
        raise SystemExit(f"Missing source ROM: {SOURCE} (or {SOURCE_ZIP})")
    try:
        with ZipFile(SOURCE_ZIP) as archive:
            candidates = [name for name in archive.namelist() if name.lower().endswith(".nds")]
            if len(candidates) != 1:
                raise SystemExit(f"Expected one .nds file in {SOURCE_ZIP}; found {len(candidates)}")
            return archive.read(candidates[0])
    except BadZipFile as exc:
        raise SystemExit(f"Could not read source archive: {SOURCE_ZIP}") from exc


def read_rom(source_bytes: bytes) -> bytearray:
    rom = bytearray(source_bytes)
    if len(rom) != 67_108_864:
        raise SystemExit(f"Expected a 64 MiB ROM; got {len(rom)} bytes")
    if rom[:12].rstrip(b"\0") != b"DRAGON TAMER" or rom[12:16] != b"AGOJ":
        raise SystemExit("Source ROM title/game code mismatch; refusing to patch")
    return rom


def file_table(rom: bytearray) -> dict[str, tuple[int, int]]:
    u32 = lambda offset: struct.unpack_from("<I", rom, offset)[0]
    fnt, fnt_size, fat, fat_size = (u32(x) for x in (0x40, 0x44, 0x48, 0x4C))
    if not (0 < fnt_size and fnt + fnt_size <= len(rom)):
        raise SystemExit("Invalid ROM file-name table")
    if not (0 < fat_size and fat + fat_size <= len(rom) and fat_size % 8 == 0):
        raise SystemExit("Invalid ROM file allocation table")
    output: dict[str, tuple[int, int]] = {}

    def walk(directory_id: int, prefix: str = "") -> None:
        if len(output) > fat_size // 8:
            raise SystemExit("Malformed file-name table recursion")
        entry = fnt + (directory_id & 0xFFF) * 8
        if entry + 8 > fnt + fnt_size:
            raise SystemExit("Directory entry is outside the file-name table")
        subtable_offset, file_id, _parent = struct.unpack_from("<IHH", rom, entry)
        cursor = fnt + subtable_offset
        while cursor < fnt + fnt_size and rom[cursor] != 0:
            name_len = rom[cursor]
            cursor += 1
            name_bytes = name_len & 0x7F
            name = bytes(rom[cursor:cursor + name_bytes]).decode("ascii")
            cursor += name_bytes
            if name_len & 0x80:
                if cursor + 2 > fnt + fnt_size:
                    raise SystemExit("Truncated subdirectory entry")
                child = struct.unpack_from("<H", rom, cursor)[0]
                cursor += 2
                walk(child, prefix + name + "/")
            else:
                if file_id * 8 + fat + 8 > fat + fat_size:
                    raise SystemExit("File entry is outside the allocation table")
                start, end = struct.unpack_from("<II", rom, fat + file_id * 8)
                if end < start or end > len(rom):
                    raise SystemExit("Invalid ROM file bounds")
                output[prefix + name] = (start, end - start)
                file_id += 1

    walk(0xF000)
    return output


def apply_offset_translations(rom: bytearray, files: dict[str, tuple[int, int]], table_path: Path, description: str) -> int:
    """Apply reviewed offset-based PAC text after source and storage validation."""
    filename = "data/new_script_dat.pac"
    if filename not in files:
        raise SystemExit(f"Missing {description} source file: {filename}")
    rows = json.loads(table_path.read_text(encoding="utf-8"))
    file_start, file_size = files[filename]
    seen: set[int] = set()
    spans: list[tuple[int, int]] = []
    for offset_text, row in rows.items():
        offset = int(offset_text)
        if offset in seen:
            raise SystemExit(f"Duplicate {description} translation at {filename}+{offset:#x}")
        seen.add(offset)
        expected = row["ja"].encode("shift_jis")
        replacement = row["en"].encode("ascii")
        if not expected or not replacement:
            raise SystemExit(f"Empty {description} text at {filename}+{offset:#x}")
        if offset < 0 or offset + len(expected) >= file_size:
            raise SystemExit(f"{description} translation is outside {filename} at {offset:#x}")
        absolute = file_start + offset
        if bytes(rom[absolute:absolute + len(expected)]) != expected:
            raise SystemExit(f"Japanese source mismatch at {filename}+{offset:#x}")
        if rom[absolute + len(expected)] != 0:
            raise SystemExit(f"Expected NUL terminator missing at {filename}+{offset:#x}")
        if len(replacement) > len(expected):
            raise SystemExit(
                f"{description} English exceeds source slot at {filename}+{offset:#x}: "
                f"{len(replacement)} > {len(expected)} bytes ({row['en']!r})"
            )
        spans.append((offset, offset + len(expected)))
        rom[absolute:absolute + len(expected)] = replacement.ljust(len(expected), b"\0")
    spans.sort()
    for previous, current in zip(spans, spans[1:]):
        if previous[1] > current[0]:
            raise SystemExit(f"Overlapping {description} translations in {filename}: {previous[0]:#x}, {current[0]:#x}")
    return len(rows)


def apply_chapter1_translations(rom: bytearray, files: dict[str, tuple[int, int]]) -> int:
    """Apply reviewed prologue and awakening translations by verified PAC offsets."""
    filename = "data/new_script_dat.pac"
    if filename not in files:
        raise SystemExit(f"Missing opening script file: {filename}")
    entries = json.loads(CHAPTER1_TRANSLATIONS.read_text(encoding="utf-8"))
    file_start, file_size = files[filename]
    seen: set[int] = set()
    spans: list[tuple[int, int]] = []
    count = 0
    for offset_text, row in entries.items():
        offset = int(offset_text)
        expected_text, translated = row["ja"], row["en"]
        if offset in seen:
            raise SystemExit(f"Duplicate chapter-one translation at {filename}+{offset:#x}")
        seen.add(offset)
        replacement = translated.encode("ascii")
        if not replacement:
            raise SystemExit(f"Empty chapter-one translation at {filename}+{offset:#x}")
        if offset < 0 or offset + 1 > file_size:
            raise SystemExit(f"Chapter-one translation starts outside {filename} at {offset:#x}")
        absolute = file_start + offset
        end = rom.find(b"\0", absolute, file_start + file_size)
        if end < 0:
            raise SystemExit(f"Unterminated chapter-one source string at {filename}+{offset:#x}")
        source_bytes = bytes(rom[absolute:end])
        expected_bytes = expected_text.encode("shift_jis")
        if source_bytes != expected_bytes:
            if source_bytes == replacement:
                count += 1
                continue
            raise SystemExit(f"Japanese source mismatch at {filename}+{offset:#x}")
        try:
            source_text = source_bytes.decode("shift_jis")
        except UnicodeDecodeError as exc:
            raise SystemExit(f"Source at {filename}+{offset:#x} is not Shift-JIS text") from exc
        if not any("ぁ" <= char <= "ヿ" or "一" <= char <= "龯" for char in source_text):
            raise SystemExit(f"Source at {filename}+{offset:#x} is not Japanese text")
        if len(replacement) > len(source_bytes):
            raise SystemExit(
                f"Chapter-one English exceeds source slot at {filename}+{offset:#x}: "
                f"{len(replacement)} > {len(source_bytes)} bytes ({translated!r})"
            )
        spans.append((offset, offset + len(source_bytes)))
        rom[absolute:end] = replacement.ljust(len(source_bytes), b"\0")
        count += 1
    spans.sort()
    for previous, current in zip(spans, spans[1:]):
        if previous[1] > current[0]:
            raise SystemExit(f"Overlapping chapter-one translations in {filename}: {previous[0]:#x}, {current[0]:#x}")
    return count


def apply_translations(rom: bytearray, files: dict[str, tuple[int, int]]) -> int:
    rows = json.loads(TRANSLATIONS.read_text(encoding="utf-8"))
    count = 0
    seen: set[tuple[str, int]] = set()
    for row in rows:
        filename, offset = row["file"], row["offset"]
        if filename not in files:
            raise SystemExit(f"Missing ROM file: {filename}")
        if (filename, offset) in seen:
            raise SystemExit(f"Duplicate translation entry: {filename}+{offset:#x}")
        seen.add((filename, offset))
        start, size = files[filename]
        original, translated = row["ja"], row["en"]
        expected = original.encode("shift_jis")
        replacement = translated.encode("ascii")
        if len(expected) != row["length"]:
            raise SystemExit(f"Source length metadata mismatch at {offset:#x}")
        if len(replacement) > len(expected):
            raise SystemExit(f"English text exceeds its source slot at {offset:#x}: {translated!r}")
        if offset < 0 or offset + len(expected) >= size:
            raise SystemExit(f"Source string is outside {filename} at {offset:#x}")
        absolute = start + offset
        if rom[absolute:absolute + len(expected)] != expected:
            raise SystemExit(f"Japanese source mismatch at {filename}+{offset:#x}")
        if rom[absolute + len(expected)] != 0:
            raise SystemExit(f"Expected NUL terminator missing at {filename}+{offset:#x}")
        rom[absolute:absolute + len(expected)] = replacement.ljust(len(expected), b"\0")
        count += 1
    return count


def validate_ascii_font(rom: bytearray, files: dict[str, tuple[int, int]], rows: list[dict]) -> int:
    """Verify the ROM's existing Shift-JIS NFTR maps every translated ASCII glyph."""
    filename = "data/sjis08.NFTR"
    if filename not in files:
        raise SystemExit(f"Missing game font: {filename}")
    start, length = files[filename]
    font = bytes(rom[start:start + length])
    if font[:4] != b"RTFN" or struct.unpack_from("<I", font, 8)[0] != len(font):
        raise SystemExit("Invalid NFTR font header")

    blocks: list[tuple[bytes, int, int]] = []
    cursor = 16
    while cursor < len(font):
        if cursor + 8 > len(font):
            raise SystemExit("Truncated NFTR block header")
        tag = font[cursor:cursor + 4]
        size = struct.unpack_from("<I", font, cursor + 4)[0]
        if size < 8 or cursor + size > len(font):
            raise SystemExit(f"Invalid NFTR block size for {tag!r}")
        blocks.append((tag, cursor, size))
        cursor += size
    if cursor != len(font):
        raise SystemExit("NFTR blocks do not fill the font file")

    finf = next((offset for tag, offset, _ in blocks if tag == b"FNIF"), None)
    cglp = next(((offset, size) for tag, offset, size in blocks if tag == b"PLGC"), None)
    cwdh = next(((offset, size) for tag, offset, size in blocks if tag == b"HDWC"), None)
    cmaps = [(offset, size) for tag, offset, size in blocks if tag == b"PAMC"]
    if finf is None or cglp is None or cwdh is None or not cmaps:
        raise SystemExit("NFTR is missing a required font or character-map block")
    if font[finf + 15] != 2:
        raise SystemExit("Expected the game's font encoding to be Shift-JIS")

    glyph_offset, glyph_block_size = cglp
    cell_width, cell_height, cell_size = struct.unpack_from("<BBH", font, glyph_offset + 8)
    bpp = font[glyph_offset + 14]
    if not cell_size or not bpp or cell_size < (cell_width * cell_height * bpp + 7) // 8:
        raise SystemExit("Invalid NFTR glyph-cell dimensions")
    glyph_count = (glyph_block_size - 16) // cell_size

    width_offset, width_block_size = cwdh
    first_glyph, last_glyph = struct.unpack_from("<HH", font, width_offset + 8)
    width_entries = (width_block_size - 16) // 3
    if last_glyph < first_glyph or last_glyph - first_glyph + 1 > width_entries:
        raise SystemExit("Invalid NFTR glyph-width table")

    codepoint_to_glyph: dict[int, int] = {}
    for offset, size in cmaps:
        first, last, mapping_type = struct.unpack_from("<HHH", font, offset + 8)
        if mapping_type == 0:
            if size < 22:
                raise SystemExit("Truncated direct NFTR character map")
            first_index = struct.unpack_from("<H", font, offset + 20)[0]
            for cp in range(first, last + 1):
                codepoint_to_glyph[cp] = first_index + cp - first
        elif mapping_type == 1:
            if size < 20 + (last - first + 1) * 2:
                raise SystemExit("Truncated table NFTR character map")
            if size != 24:
                for cp in range(first, last + 1):
                    codepoint_to_glyph[cp] = struct.unpack_from("<H", font, offset + 20 + (cp - first) * 2)[0]
        elif mapping_type == 2:
            if size < 22:
                raise SystemExit("Truncated scan NFTR character map")
            entry_count = struct.unpack_from("<H", font, offset + 20)[0]
            if size < 22 + entry_count * 4:
                raise SystemExit("Truncated scan NFTR character-map entries")
            for index in range(entry_count):
                cp, glyph = struct.unpack_from("<HH", font, offset + 22 + index * 4)
                codepoint_to_glyph[cp] = glyph
        else:
            raise SystemExit(f"Unknown NFTR character-map type: {mapping_type}")

    required = {
        ord(char)
        for row in rows
        for char in row["en"]
        if char not in ("\n", "\r")
    }
    # Also validate bytes and glyphs for the additional opening-scene translations.
    extra_translations = json.loads(EXTRA_TRANSLATIONS.read_text(encoding="utf-8"))
    extra_translations.extend(json.loads(MORE_TRANSLATIONS.read_text(encoding="utf-8")))
    menu_translations = json.loads(MENU_TRANSLATIONS.read_text(encoding="utf-8"))
    shop_nest_translations = json.loads(SHOP_NEST_TRANSLATIONS.read_text(encoding="utf-8"))
    item_names = json.loads(ITEM_NAMES_TRANSLATIONS.read_text(encoding="utf-8"))
    item_descriptions = json.loads(ITEM_DESCRIPTIONS_TRANSLATIONS.read_text(encoding="utf-8"))
    dragon_force_descriptions = json.loads(DRAGON_FORCE_TRANSLATIONS.read_text(encoding="utf-8"))
    chapter3_translations = json.loads(CHAPTER3_TRANSLATIONS.read_text(encoding="utf-8"))
    chapter4_translations = json.loads(CHAPTER4_TRANSLATIONS.read_text(encoding="utf-8"))
    chapter5_translations = json.loads(CHAPTER5_TRANSLATIONS.read_text(encoding="utf-8"))
    chapter6_translations = json.loads(CHAPTER6_TRANSLATIONS.read_text(encoding="utf-8"))
    chapter7_translations = json.loads(CHAPTER7_TRANSLATIONS.read_text(encoding="utf-8"))
    chapter8_translations = json.loads(CHAPTER8_TRANSLATIONS.read_text(encoding="utf-8"))
    chapter9_translations = json.loads(CHAPTER9_TRANSLATIONS.read_text(encoding="utf-8"))
    chapter10_translations = json.loads(CHAPTER10_TRANSLATIONS.read_text(encoding="utf-8"))
    chapter11_translations = json.loads(CHAPTER11_TRANSLATIONS.read_text(encoding="utf-8"))
    chapter12_translations = json.loads(CHAPTER12_TRANSLATIONS.read_text(encoding="utf-8"))
    chapter13_translations = json.loads(CHAPTER13_TRANSLATIONS.read_text(encoding="utf-8"))
    chapter14_translations = json.loads(CHAPTER14_TRANSLATIONS.read_text(encoding="utf-8"))
    chapter15_translations = json.loads(CHAPTER15_TRANSLATIONS.read_text(encoding="utf-8"))
    required.update(
        ord(char)
        for row in extra_translations
        for char in row["en"]
        if char not in ("\n", "\r")
    )
    required.update(
        ord(char)
        for row in menu_translations
        for char in row["en"]
        if char not in ("\n", "\r")
    )
    required.update(
        ord(char)
        for file_translations in shop_nest_translations.values()
        for text in file_translations.values()
        for char in text
        if char not in ("\n", "\r")
    )
    required.update(ord(char) for text in item_names.values() for char in text)
    required.update(
        ord(char)
        for text in item_descriptions.values()
        for char in text
        if char not in ("\n", "\r")
    )
    required.update(
        ord(char)
        for text in dragon_force_descriptions.values()
        for char in text
        if char not in ("\n", "\r")
    )
    required.update(
        ord(char)
        for row in chapter3_translations.values()
        for char in row["en"]
        if char not in ("\n", "\r")
    )
    required.update(
        ord(char)
        for row in chapter4_translations.values()
        for char in row["en"]
        if char not in ("\n", "\r")
    )
    required.update(
        ord(char)
        for row in chapter5_translations.values()
        for char in row["en"]
        if char not in ("\n", "\r")
    )
    required.update(
        ord(char)
        for row in chapter6_translations.values()
        for char in row["en"]
        if char not in ("\n", "\r")
    )
    required.update(
        ord(char)
        for row in chapter7_translations.values()
        for char in row["en"]
        if char not in ("\n", "\r")
    )
    required.update(
        ord(char)
        for row in chapter8_translations.values()
        for char in row["en"]
        if char not in ("\n", "\r")
    )
    required.update(
        ord(char)
        for row in chapter9_translations.values()
        for char in row["en"]
        if char not in ("\n", "\r")
    )
    required.update(
        ord(char)
        for row in chapter10_translations.values()
        for char in row["en"]
        if char not in ("\n", "\r")
    )
    required.update(
        ord(char)
        for row in chapter11_translations.values()
        for char in row["en"]
        if char not in ("\n", "\r")
    )
    required.update(
        ord(char)
        for row in chapter12_translations.values()
        for char in row["en"]
        if char not in ("\n", "\r")
    )
    required.update(
        ord(char)
        for row in chapter13_translations.values()
        for char in row["en"]
        if char not in ("\n", "\r")
    )
    required.update(
        ord(char)
        for row in chapter14_translations.values()
        for char in row["en"]
        if char not in ("\n", "\r")
    )
    required.update(
        ord(char)
        for row in chapter15_translations.values()
        for char in row["en"]
        if char not in ("\n", "\r")
    )
    completion = json.loads((PROJECT / "story_completion.json").read_text(encoding="utf-8"))
    required.update(ord(c) for text in completion.values() for c in text if c not in "\n\r")
    for text in completion.values():
        for line in text.split("\n"):
            width = sum(font[width_offset+16+3*(codepoint_to_glyph[ord(c)]-first_glyph)+2] for c in line)
            if width > 168:
                raise SystemExit(f"Completion line exceeds portrait dialogue width ({width}px): {line!r}")
    if FULL_DRAFT:
        for draft_name in ('full_draft_story.json', 'full_draft_map.json'):
            draft = json.loads((PROJECT / draft_name).read_text(encoding='utf8'))
            required.update(ord(c) for t in draft.values() for c in t if c not in '\n\r')
        # Input text may need multiple pages. paginate_dialogue validates the
        # final, composed text using the story font after all tables are merged.
    for cp in required:
        if cp not in codepoint_to_glyph:
            raise SystemExit(f"English glyph U+{cp:04X} is not mapped by the game font")
        glyph = codepoint_to_glyph[cp]
        if glyph == 0xFFFF or glyph >= glyph_count:
            raise SystemExit(f"English glyph U+{cp:04X} maps outside the bitmap table")
        if not first_glyph <= glyph <= last_glyph:
            raise SystemExit(f"English glyph U+{cp:04X} has no width metrics")
        if cp != 0x20:
            bitmap = font[glyph_offset + 16 + glyph * cell_size:glyph_offset + 16 + (glyph + 1) * cell_size]
            if not any(bitmap):
                raise SystemExit(f"English glyph U+{cp:04X} has an empty bitmap")
    for row in menu_translations:
        filename, offset = row["file"], row["offset"]
        if filename not in files:
            raise SystemExit(f"Missing menu-text ROM file: {filename}")
        expected = row["ja"].encode("shift_jis")
        replacement = row["en"].encode("ascii")
        if len(expected) != row["length"]:
            raise SystemExit(f"Menu-text source length mismatch at {filename}+{offset:#x}")
        if len(replacement) > len(expected):
            raise SystemExit(f"English menu text exceeds its source slot at {filename}+{offset:#x}: {row['en']!r}")
        file_start, file_size = files[filename]
        if offset < 0 or offset + len(expected) >= file_size:
            raise SystemExit(f"Menu-text source is outside {filename} at {offset:#x}")
        file_data = rom[file_start:file_start + file_size]
        if file_data[offset:offset + len(expected)] != expected:
            raise SystemExit(f"Japanese menu-text source mismatch at {filename}+{offset:#x}")
        if file_data[offset + len(expected)] != 0:
            raise SystemExit(f"Expected NUL terminator missing at {filename}+{offset:#x}")

    item_file = "data/item_info.csv"
    if item_file not in files:
        raise SystemExit(f"Missing item-name table: {item_file}")
    item_start, item_size = files[item_file]
    item_data = bytes(rom[item_start:item_start + item_size])
    item_rows: dict[str, tuple[int, int]] = {}
    cursor = 0
    while cursor < len(item_data):
        line_end = item_data.find(b"\n", cursor)
        if line_end < 0:
            line_end = len(item_data)
        line = item_data[cursor:line_end].rstrip(b"\r")
        if line and line[:1].isdigit():
            columns = line.split(b",")
            if len(columns) < 2 or not columns[0].isdigit():
                raise SystemExit(f"Malformed item-info row at {item_file}+{cursor:#x}")
            item_rows[columns[0].decode("ascii")] = (cursor + len(columns[0]) + 1, len(columns[1]))
        cursor = line_end + 1
    if set(item_names) != set(item_rows):
        missing, extra = set(item_rows) - set(item_names), set(item_names) - set(item_rows)
        raise SystemExit(f"Item-name table coverage mismatch; missing={sorted(missing)}, extra={sorted(extra)}")
    for index, translated in item_names.items():
        offset, capacity = item_rows[index]
        replacement = translated.encode("ascii")
        if len(replacement) > capacity:
            raise SystemExit(f"English item name exceeds source slot at {item_file}[{index}]: {translated!r}")
        if offset < 0 or offset + capacity > item_size:
            raise SystemExit(f"Item-name slot outside {item_file}[{index}]")

    comments_file = "data/item_comment.krd"
    if comments_file not in files:
        raise SystemExit(f"Missing item-description table: {comments_file}")
    comments_start, comments_size = files[comments_file]
    comments_data = bytes(rom[comments_start:comments_start + comments_size])
    comment_count = struct.unpack_from("<I", comments_data, 0)[0]
    if 4 + comment_count * 4 > comments_size:
        raise SystemExit(f"Invalid item-description offset table in {comments_file}")
    comment_slots: dict[str, tuple[int, int]] = {}
    for index in range(comment_count):
        begin = struct.unpack_from("<I", comments_data, 4 + index * 4)[0]
        end = struct.unpack_from("<I", comments_data, 8 + index * 4)[0] if index + 1 < comment_count else comments_size
        if begin < 4 + comment_count * 4 or end <= begin or end > comments_size:
            raise SystemExit(f"Invalid item-description bounds for index {index}")
        terminator = comments_data.find(b"\0", begin, end)
        if terminator < 0 or terminator != end - 1:
            raise SystemExit(f"Invalid item-description terminator for index {index}")
        comment_slots[str(index)] = (begin, terminator - begin)
    if set(item_descriptions) != {key for key, (_offset, capacity) in comment_slots.items() if capacity}:
        expected = {key for key, (_offset, capacity) in comment_slots.items() if capacity}
        missing, extra = expected - set(item_descriptions), set(item_descriptions) - expected
        raise SystemExit(f"Item-description table coverage mismatch; missing={sorted(missing)}, extra={sorted(extra)}")
    for index, translated in item_descriptions.items():
        _offset, capacity = comment_slots[index]
        replacement = translated.encode("ascii")
        if len(replacement) > capacity:
            raise SystemExit(f"English item description exceeds source slot at {comments_file}[{index}]: {translated!r}")

    force_files = ("data/df_comment_a.krd", "data/df_comment_b.krd")
    force_layouts: list[dict[str, tuple[int, int, bytes]]] = []
    for force_file in force_files:
        if force_file not in files:
            raise SystemExit(f"Missing Dragon Force description table: {force_file}")
        force_start, force_size = files[force_file]
        force_data = bytes(rom[force_start:force_start + force_size])
        data_start = struct.unpack_from("<I", force_data, 0)[0]
        if data_start < 4 or data_start > force_size or (data_start - 4) % 4:
            raise SystemExit(f"Invalid Dragon Force pointer table in {force_file}")
        entry_count = (data_start - 4) // 4
        pointers = [data_start]
        pointers.extend(struct.unpack_from("<I", force_data, 4 + index * 4)[0] for index in range(entry_count))
        pointers.append(force_size)
        if len(pointers) != 102:
            raise SystemExit(f"Expected 101 Dragon Force descriptions in {force_file}; found {len(pointers) - 1}")
        slots: dict[str, tuple[int, int, bytes]] = {}
        for index, (begin, end) in enumerate(zip(pointers, pointers[1:])):
            if begin < data_start or end <= begin or end > force_size:
                raise SystemExit(f"Invalid Dragon Force bounds at {force_file}[{index}]")
            segment = force_data[begin:end]
            terminator = segment.find(b"\0")
            if terminator < 0 or terminator != len(segment) - 1:
                raise SystemExit(f"Invalid Dragon Force terminator at {force_file}[{index}]")
            original = segment[:terminator]
            original.decode("shift_jis")
            slots[str(index)] = (force_start + begin, terminator, original)
        if set(slots) != set(dragon_force_descriptions):
            missing, extra = set(slots) - set(dragon_force_descriptions), set(dragon_force_descriptions) - set(slots)
            raise SystemExit(f"Dragon Force description coverage mismatch for {force_file}; missing={sorted(missing)}, extra={sorted(extra)}")
        force_layouts.append(slots)
    normalize_force_text = lambda text: "".join(text.split()).replace("味方1体の", "味方1体に").replace("味方全体の", "味方全体に").replace("HPを", "HP").replace("のHPを", "のHP").replace("のHP入れかえる", "のHPを入れかえる").replace("HPいれかえる", "HPを入れかえる").replace("からHP", "から").replace("100ダメージ", "100のダメージ").replace("140ダメージ", "140のダメージ").replace("180ダメージ", "180のダメージ").replace("220ダメージ", "220のダメージ").replace("240ダメージ", "240のダメージ").replace("260ダメージ", "260のダメージ").replace("340ダメージ", "340のダメージ").replace("70ダメージ", "70のダメージ").replace("90ダメージ", "90のダメージ").replace("160ダメージ", "160のダメージ").replace("200ダメージ", "200のダメージ").replace("300ダメージ", "300のダメージ").replace("50のHP", "50HP").replace("90のHP", "90HP").replace("160のHP", "160HP").replace("120ダメージ", "120のダメージ").replace("130ダメージ", "130のダメージ").replace("HP入れかえる", "HPを入れかえる").replace("1体と", "1体と").replace("だれか1体", "1体")
    if any(
        normalize_force_text(force_layouts[0][index][2].decode("shift_jis"))
        != normalize_force_text(force_layouts[1][index][2].decode("shift_jis"))
        for index in dragon_force_descriptions
    ):
        raise SystemExit("Dragon Force description sources differ between display layouts")
    for index, translated in dragon_force_descriptions.items():
        replacement = translated.encode("ascii")
        for layout in force_layouts:
            _offset, capacity, _original = layout[index]
            if len(replacement) > capacity:
                raise SystemExit(f"English Dragon Force description exceeds source slot at index {index}: {translated!r}")

    return len(required)


def apply_extra_translations(rom: bytearray, files: dict[str, tuple[int, int]]) -> int:
    rows = json.loads(EXTRA_TRANSLATIONS.read_text(encoding="utf-8"))
    rows.extend(json.loads(MORE_TRANSLATIONS.read_text(encoding="utf-8")))
    seen: set[tuple[str, int]] = set()
    for row in rows:
        filename, offset = row["file"], row["offset"]
        if filename not in files:
            raise SystemExit(f"Missing ROM file: {filename}")
        if (filename, offset) in seen:
            raise SystemExit(f"Duplicate additional translation entry: {filename}+{offset:#x}")
        seen.add((filename, offset))
        start, size = files[filename]
        original, translated = row["ja"], row["en"]
        expected, replacement = original.encode("shift_jis"), translated.encode("ascii")
        if len(expected) != row["length"]:
            raise SystemExit(f"Additional source length mismatch at {offset:#x}")
        if len(replacement) > len(expected):
            raise SystemExit(f"English text exceeds its source slot at {offset:#x}: {translated!r}")
        if offset < 0 or offset + len(expected) >= size:
            raise SystemExit(f"Additional source is outside {filename} at {offset:#x}")
        absolute = start + offset
        current = bytes(rom[absolute:absolute + len(expected)])
        if current != expected:
            # Opening prologue entries are already translated by the reviewed
            # offset table and may use a different English rendering.
            if filename == "data/new_script_dat.pac" and 50326 <= offset <= 51013:
                continue
            raise SystemExit(f"Japanese source mismatch at {filename}+{offset:#x}")
        if rom[absolute + len(expected)] != 0:
            raise SystemExit(f"Expected NUL terminator missing at {filename}+{offset:#x}")
        rom[absolute:absolute + len(expected)] = replacement.ljust(len(expected), b"\0")
    return len(rows)


def apply_menu_translations(rom: bytearray, files: dict[str, tuple[int, int]]) -> int:
    rows = json.loads(MENU_TRANSLATIONS.read_text(encoding="utf-8"))
    seen: set[tuple[str, int]] = set()
    for row in rows:
        filename, offset = row["file"], row["offset"]
        if filename not in files:
            raise SystemExit(f"Missing menu-text ROM file: {filename}")
        if (filename, offset) in seen:
            raise SystemExit(f"Duplicate menu translation entry: {filename}+{offset:#x}")
        seen.add((filename, offset))
        file_start, file_size = files[filename]
        expected = row["ja"].encode("shift_jis")
        replacement = row["en"].encode("ascii")
        if len(expected) != row["length"]:
            raise SystemExit(f"Menu-text source length mismatch at {filename}+{offset:#x}")
        if len(replacement) > len(expected):
            raise SystemExit(f"English menu text exceeds its source slot at {filename}+{offset:#x}: {row['en']!r}")
        if offset < 0 or offset + len(expected) >= file_size:
            raise SystemExit(f"Menu-text source is outside {filename} at {offset:#x}")
        absolute = file_start + offset
        if rom[absolute:absolute + len(expected)] != expected:
            raise SystemExit(f"Japanese menu-text source mismatch at {filename}+{offset:#x}")
        if rom[absolute + len(expected)] != 0:
            raise SystemExit(f"Expected NUL terminator missing at {filename}+{offset:#x}")
        rom[absolute:absolute + len(expected)] = replacement.ljust(len(expected), b"\0")
    return len(rows)


def apply_interface_translations(rom: bytearray, files: dict[str, tuple[int, int]]) -> int:
    """Replace reviewed non-story help-page headings and paragraphs in fixed-size slots."""
    translations = json.loads(INTERFACE_TRANSLATIONS.read_text(encoding="utf-8"))
    count = 0

    for filename, entries in translations.items():
        if filename not in files:
            raise SystemExit(f"Missing interface text file: {filename}")
        file_start, file_size = files[filename]
        spans: list[tuple[int, int]] = []
        for offset_text, row in entries.items():
            offset = int(offset_text)
            expected = row["ja"].encode("shift_jis")
            replacement = row["en"].encode("ascii")
            end = offset + len(expected)
            if not expected or not replacement or offset < 0 or end >= file_size:
                raise SystemExit(f"Invalid interface source slot at {filename}+{offset:#x}")
            absolute = file_start + offset
            local_offset = offset
            if bytes(rom[absolute:absolute + len(expected)]) != expected:
                raise SystemExit(f"Japanese interface source mismatch at {filename}+{offset:#x}")
            if rom[absolute + len(expected)] != 0:
                raise SystemExit(f"Expected NUL terminator missing at {filename}+{offset:#x}")
            if len(replacement) > len(expected):
                raise SystemExit(f"Interface text exceeds source slot at {filename}+{offset:#x}: {row['en']!r}")
            spans.append((local_offset, offset + len(expected)))
            rom[absolute:absolute + len(expected)] = replacement.ljust(len(expected), b"\0")
            count += 1
        spans.sort()
        for previous, current in zip(spans, spans[1:]):
            if previous[1] > current[0]:
                raise SystemExit(f"Overlapping interface translations in {filename}: {previous[0]:#x}, {current[0]:#x}")
    return count


def apply_help_text_translations(rom: bytearray, files: dict[str, tuple[int, int]]) -> int:
    """Replace reviewed help-page paragraphs in their original NUL-delimited PAC slots."""
    translations = json.loads(HELP_TEXT_TRANSLATIONS.read_text(encoding="utf-8"))
    count = 0
    for filename, entries in translations.items():
        if filename not in files:
            raise SystemExit(f"Missing help text file: {filename}")
        file_start, file_size = files[filename]
        spans: list[tuple[int, int]] = []
        for offset_text, row in entries.items():
            offset = int(offset_text)
            expected = row["ja"].encode("shift_jis")
            replacement = row["en"].encode("ascii")
            if not expected or not replacement or offset < 0 or offset + len(expected) > file_size:
                raise SystemExit(f"Invalid help text slot at {filename}+{offset:#x}")
            absolute = file_start + offset
            source_end = rom.find(b"\0", absolute, file_start + file_size)
            if source_end < 0 or bytes(rom[absolute:source_end]) != expected:
                raise SystemExit(f"Japanese help source mismatch at {filename}+{offset:#x}")
            if len(replacement) > len(expected):
                raise SystemExit(f"Help text exceeds source slot at {filename}+{offset:#x}: {row['en']!r}")
            spans.append((offset, source_end - file_start))
            rom[absolute:source_end] = replacement.ljust(len(expected), b"\0")
            count += 1
        spans.sort()
        for previous, current in zip(spans, spans[1:]):
            if previous[1] > current[0]:
                raise SystemExit(f"Overlapping help text translations in {filename}: {previous[0]:#x}, {current[0]:#x}")
    return count


def apply_shop_nest_translations(rom: bytearray, files: dict[str, tuple[int, int]]) -> int:
    translations = json.loads(SHOP_NEST_TRANSLATIONS.read_text(encoding="utf-8"))
    count = 0
    for filename, entries in translations.items():
        if filename not in files:
            raise SystemExit(f"Missing shop/Nest text ROM file: {filename}")
        file_start, file_size = files[filename]
        data = rom[file_start:file_start + file_size]
        string_count = struct.unpack_from("<I", data, 0)[0]
        if 4 + string_count * 4 > file_size:
            raise SystemExit(f"Invalid string-offset table in {filename}")
        for index_text, translated in entries.items():
            index = int(index_text)
            if index < 0 or index >= string_count:
                raise SystemExit(f"Invalid string index {index} in {filename}")
            offset = struct.unpack_from("<I", data, 4 + index * 4)[0]
            if offset >= file_size:
                raise SystemExit(f"String offset outside {filename}: {offset:#x}")
            end = data.find(0, offset)
            if end < 0:
                raise SystemExit(f"Unterminated string {index} in {filename}")
            expected = data[offset:end]
            replacement = translated.encode("ascii")
            if len(replacement) > len(expected):
                raise SystemExit(f"English text exceeds source slot at {filename}[{index}]: {translated!r}")
            absolute = file_start + offset
            rom[absolute:absolute + len(expected)] = replacement.ljust(len(expected), b"\0")
            count += 1
    return count


def apply_item_name_translations(rom: bytearray, files: dict[str, tuple[int, int]]) -> int:
    translations = json.loads(ITEM_NAMES_TRANSLATIONS.read_text(encoding="utf-8"))
    filename = "data/item_info.csv"
    if filename not in files:
        raise SystemExit(f"Missing item-name table: {filename}")
    file_start, file_size = files[filename]
    source = bytes(rom[file_start:file_start + file_size])
    slots: dict[str, tuple[int, int]] = {}
    cursor = 0
    while cursor < len(source):
        line_end = source.find(b"\n", cursor)
        if line_end < 0:
            line_end = len(source)
        line = source[cursor:line_end].rstrip(b"\r")
        if line and line[:1].isdigit():
            columns = line.split(b",")
            if len(columns) < 2 or not columns[0].isdigit():
                raise SystemExit(f"Malformed item-info row at {filename}+{cursor:#x}")
            slots[columns[0].decode("ascii")] = (cursor + len(columns[0]) + 1, len(columns[1]))
        cursor = line_end + 1
    if set(translations) != set(slots):
        missing, extra = set(slots) - set(translations), set(translations) - set(slots)
        raise SystemExit(f"Item-name table coverage mismatch; missing={sorted(missing)}, extra={sorted(extra)}")
    for index, translated in translations.items():
        offset, capacity = slots[index]
        replacement = translated.encode("ascii")
        if len(replacement) > capacity:
            raise SystemExit(f"English item name exceeds source slot at {filename}[{index}]: {translated!r}")
        absolute = file_start + offset
        rom[absolute:absolute + capacity] = replacement.ljust(capacity, b" ")
    return len(translations)


def apply_item_description_translations(rom: bytearray, files: dict[str, tuple[int, int]]) -> int:
    translations = json.loads(ITEM_DESCRIPTIONS_TRANSLATIONS.read_text(encoding="utf-8"))
    filename = "data/item_comment.krd"
    if filename not in files:
        raise SystemExit(f"Missing item-description table: {filename}")
    file_start, file_size = files[filename]
    source = bytes(rom[file_start:file_start + file_size])
    count = struct.unpack_from("<I", source, 0)[0]
    if 4 + count * 4 > file_size:
        raise SystemExit(f"Invalid item-description offset table in {filename}")
    slots: dict[str, tuple[int, int]] = {}
    for index in range(count):
        begin = struct.unpack_from("<I", source, 4 + index * 4)[0]
        end = struct.unpack_from("<I", source, 8 + index * 4)[0] if index + 1 < count else file_size
        if begin < 4 + count * 4 or end <= begin or end > file_size:
            raise SystemExit(f"Invalid item-description bounds for index {index}")
        terminator = source.find(b"\0", begin, end)
        if terminator < 0 or terminator != end - 1:
            raise SystemExit(f"Invalid item-description terminator for index {index}")
        if terminator > begin:
            slots[str(index)] = (file_start + begin, terminator - begin)
    if set(translations) != set(slots):
        missing, extra = set(slots) - set(translations), set(translations) - set(slots)
        raise SystemExit(f"Item-description table coverage mismatch; missing={sorted(missing)}, extra={sorted(extra)}")
    for index, translated in translations.items():
        offset, capacity = slots[index]
        replacement = translated.encode("ascii")
        if len(replacement) > capacity:
            raise SystemExit(f"English item description exceeds source slot at {filename}[{index}]: {translated!r}")
        rom[offset:offset + capacity] = replacement.ljust(capacity, b" ")
    return len(translations)


def apply_dragon_force_translations(rom: bytearray, files: dict[str, tuple[int, int]]) -> int:
    translations = json.loads(DRAGON_FORCE_TRANSLATIONS.read_text(encoding="utf-8"))
    count = 0
    for filename in ("data/df_comment_a.krd", "data/df_comment_b.krd"):
        if filename not in files:
            raise SystemExit(f"Missing Dragon Force description table: {filename}")
        file_start, file_size = files[filename]
        source = bytes(rom[file_start:file_start + file_size])
        data_start = struct.unpack_from("<I", source, 0)[0]
        if data_start < 4 or data_start > file_size or (data_start - 4) % 4:
            raise SystemExit(f"Invalid Dragon Force pointer table in {filename}")
        pointer_count = (data_start - 4) // 4
        pointers = [data_start]
        pointers.extend(struct.unpack_from("<I", source, 4 + index * 4)[0] for index in range(pointer_count))
        pointers.append(file_size)
        if len(pointers) != 102:
            raise SystemExit(f"Expected 101 Dragon Force descriptions in {filename}; found {len(pointers) - 1}")
        slots: dict[str, tuple[int, int, bytes]] = {}
        for index, (begin, end) in enumerate(zip(pointers, pointers[1:])):
            if begin < data_start or end <= begin or end > file_size:
                raise SystemExit(f"Invalid Dragon Force bounds at {filename}[{index}]")
            segment = source[begin:end]
            terminator = segment.find(b"\0")
            if terminator < 0 or terminator != len(segment) - 1:
                raise SystemExit(f"Invalid Dragon Force terminator at {filename}[{index}]")
            original = segment[:terminator]
            original.decode("shift_jis")
            if terminator:
                slots[str(index)] = (file_start + begin, terminator, original)
        if set(translations) != set(slots):
            missing, extra = set(slots) - set(translations), set(translations) - set(slots)
            raise SystemExit(f"Dragon Force description coverage mismatch for {filename}; missing={sorted(missing)}, extra={sorted(extra)}")
        for index, translated in translations.items():
            offset, capacity, original = slots[index]
            replacement = translated.encode("ascii")
            if len(replacement) > capacity:
                raise SystemExit(f"English Dragon Force description exceeds source slot at {filename}[{index}]: {translated!r}")
            rom[offset:offset + capacity] = replacement.ljust(capacity, b" ")
        count += len(translations)
    return count


def patch_command_menu_graphics(rom: bytearray, files: dict[str, tuple[int, int]]) -> int:
    """Replace the four Japanese command labels baked into the title menu's texture."""
    filename = "data/command_menu.pac"
    if filename not in files:
        raise SystemExit(f"Missing command-menu graphics: {filename}")
    file_start, file_size = files[filename]
    source = bytes(rom[file_start:file_start + file_size])
    if source[:4] != b"PK\x00\x01":
        raise SystemExit(f"Invalid command-menu PAC header: {filename}")
    entry_count = struct.unpack_from("<I", source, 4)[0]
    if entry_count < 3 or 16 + entry_count * 16 > file_size:
        raise SystemExit("Invalid command-menu PAC entry table")

    entry_offset, entry_size = struct.unpack_from("<II", source, 16 + 2 * 16)
    if entry_offset + entry_size > file_size:
        raise SystemExit("Command-menu texture entry is outside the PAC")
    texture = bytearray(source[entry_offset:entry_offset + entry_size])
    if texture[:2] != b"CT" or struct.unpack_from("<HH", texture, 2) != (96, 128):
        raise SystemExit("Unexpected command-menu button texture layout")
    if texture[8] != 0x20:
        raise SystemExit("Expected 4-bpp command-menu texture")

    width, height = struct.unpack_from("<HH", texture, 2)
    data_size, data_offset = struct.unpack_from("<II", texture, 16)
    palette_offset = struct.unpack_from("<I", texture, 20)[0]
    if data_offset + data_size > len(texture) or palette_offset != 0x40:
        raise SystemExit("Invalid command-menu texture data offsets")
    if data_size != width * height // 2 or height != 128:
        raise SystemExit("Unexpected command-menu texture pixel dimensions")

    palette = [struct.unpack_from("<H", texture, 0x20 + i * 2)[0] for i in range(16)]
    expected_ink = (0x0447, 0x0465, 0x10EC)
    if tuple(palette[2:5]) != expected_ink:
        raise SystemExit("Unexpected command-menu label palette")
    pixels = bytearray(texture[data_offset:data_offset + data_size])
    texts = (
        "Make a Team",
        "Use Items",
        "Check Key Items",
        "Use Return Ring",
    )
    from pixel_ui import mask as pixel_text_mask

    for row, text in enumerate(texts):
        top = row * 32
        # Draw at native resolution: Arial at seven pixels merged letter stems.
        # The 5x7 bitmap alphabet has solid, evenly spaced strokes.
        mask = Image.new("L", (width, 32))
        mask.paste(pixel_text_mask(width - 4, 18, text), (2, 3))

        # The labels use mostly dark palette indices; 5 (a neutral purple)
        # appears in the main label strokes too, so include it in the mask.
        for local_y in range(3, 21):
            y = top + local_y
            for x in range(width):
                at = ((y // 8) * (width // 8) + x // 8) * 32 + (y % 8) * 4 + (x % 8) // 2
                shift = 4 * (x % 2)
                old_index = (pixels[at] >> shift) & 0xF
                if old_index in (1, 2, 3, 4, 5):
                    pixels[at] = (pixels[at] & ~(0xF << shift)) | (13 << shift)
                if mask.getpixel((x, local_y)) >= 96:
                    pixels[at] = (pixels[at] & ~(0xF << shift)) | (2 << shift)

    texture[data_offset:data_offset + data_size] = pixels
    rom[file_start + entry_offset:file_start + entry_offset + entry_size] = texture
    return len(texts)


def patch_title_menu_graphics(rom: bytearray, files: dict[str, tuple[int, int]]) -> int:
    """Translate title sprites stored as consecutive 32-pixel-wide objects."""
    start, size = files["data/dttitle_cim.pac"]
    labels = {0: "Continue", 1: "Erase Data", 2: "Headphones", 3: "New Game",
              4: "Options", 5: "Sound Settings", 6: "Stereo", 7: "Surround",
              8: "Wireless Battle", 9: "Battle Record", 30: "Touch the screen."}
    previews = []
    for asset, text in labels.items():
        offset, length = struct.unpack_from("<II", rom, start+16+asset*16)
        texture = bytearray(rom[start+offset:start+offset+length])
        assert texture[:2] == b"CX" and texture[6] == 4
        width, height = struct.unpack_from("<HH", texture, 2)
        data_size, data_offset = struct.unpack_from("<II", texture, 16)
        assert data_size == width*height//2 and width % 32 == 0
        colors = [tuple(((c >> shift)&31)*255//31 for shift in (0,5,10))
                  for c in struct.unpack_from("<16H",texture,48)]
        pixels = bytearray(texture[data_offset:data_offset+data_size])
        def address(x,y):
            return (x//32)*32*height+((y//8)*4+(x%32)//8)*64+(y%8)*8+x%8
        image = Image.new("RGB", (width,height))
        for y in range(height):
            for x in range(width):
                n=address(x,y)
                image.putpixel((x,y), colors[(pixels[n//2]>>(4*(n%2)))&15])
        prompt = asset == 30
        box = (45,2,211,13) if prompt else (6,4,89,20)
        background = (52,20,37) if prompt else (255,195,120)
        ink = (255,255,255) if prompt else (30,16,8)
        draw = ImageDraw.Draw(image)
        draw.rectangle(box, fill=background)
        font = ImageFont.truetype("C:/Windows/Fonts/Arial.ttf", 9)
        bounds=draw.textbbox((0,0),text,font=font)
        tw,th=bounds[2]-bounds[0],bounds[3]-bounds[1]
        assert tw <= box[2]-box[0]-2
        draw.text(((box[0]+box[2]-tw)//2-bounds[0],
                   (box[1]+box[3]-th)//2-bounds[1]),text,font=font,fill=ink)
        pal=Image.new("P",(1,1)); pal.putpalette([v for c in colors for v in c])
        indexed=image.quantize(palette=pal,dither=Image.Dither.NONE)
        for y in range(box[1],box[3]+1):
            for x in range(box[0],box[2]+1):
                n=address(x,y); shift=4*(n%2); color=indexed.getpixel((x,y))
                assert color < 16
                pixels[n//2]=(pixels[n//2]&~(15<<shift))|(color<<shift)
        texture[data_offset:data_offset+data_size]=pixels
        rom[start+offset:start+offset+length]=texture
        previews.append(indexed.convert("RGB"))
    sheet=Image.new("RGB",(512, len(previews)*64))
    for i,im in enumerate(previews): sheet.paste(im.resize((im.width*2,im.height*2)),(0,i*64))
    sheet.save(PROJECT/"title_menu_english_preview.png")
    return len(labels)


def patch_title_logo_graphics(rom: bytearray, files: dict[str, tuple[int, int]]) -> int:
    """Replace the Japanese subtitle on every title-logo animation frame."""
    filename = "data/dttitle_cim.pac"
    if filename not in files:
        raise SystemExit(f"Missing title-logo graphics: {filename}")
    file_start, file_size = files[filename]
    source = bytes(rom[file_start:file_start + file_size])
    if source[:4] != b"PK\x00\x01":
        raise SystemExit(f"Invalid title-logo PAC header: {filename}")
    entry_count = struct.unpack_from("<I", source, 4)[0]
    if entry_count < 28 or 16 + entry_count * 16 > file_size:
        raise SystemExit("Invalid title-logo PAC entry table")

    text = "DRAGON TAMER: SOUND SPIRIT"
    x1, x2, y1, y2 = 31, 197, 85, 97
    scale = 4
    font = ImageFont.truetype("C:/Windows/Fonts/Arialbd.ttf", 7 * scale)
    patched_frames = 0
    # The title PAC alternates the logo-bearing composite with bare background
    # images; subtitle text exists only on the even-numbered composite entries.
    for entry_id in range(10, 28, 2):
        entry_offset, entry_size = struct.unpack_from("<II", source, 16 + entry_id * 16)
        if entry_offset + entry_size > file_size:
            raise SystemExit(f"Title-logo texture entry {entry_id} is outside the PAC")
        texture = bytearray(source[entry_offset:entry_offset + entry_size])
        if texture[:4] != b"CX\x00\x01":
            raise SystemExit(f"Unexpected title-logo texture header at entry {entry_id}")
        data_size, data_offset = struct.unpack_from("<II", texture, 16)
        lookup_size, lookup_offset = struct.unpack_from("<II", texture, 24)
        width, height = 256, 192
        if (
            texture[4:8] != b"\xC0\x00\x08\x10"
            or data_size != width * height
            or data_offset != 0x230
            or lookup_size != 0x600
            or lookup_offset != 0xC230
            or lookup_offset + lookup_size > len(texture)
            or data_offset + data_size > len(texture)
        ):
            raise SystemExit(f"Unexpected title-logo texture layout at entry {entry_id}")

        colors: list[tuple[int, int, int]] = []
        for color_id in range(256):
            color = struct.unpack_from("<H", texture, 0x30 + color_id * 2)[0]
            colors.append(tuple(((color >> shift) & 0x1F) * 255 // 31 for shift in (0, 5, 10)))
        if colors[0] != (0, 255, 0):
            raise SystemExit(f"Unexpected key color in title-logo palette at entry {entry_id}")
        pixels = texture[data_offset:data_offset + data_size]
        linear = [0] * data_size
        for y in range(height):
            for x in range(width):
                tiled_offset = ((y // 8) * (width // 8) + x // 8) * 64 + (y % 8) * 8 + x % 8
                linear[y * width + x] = pixels[tiled_offset]
        image = Image.new("RGB", (width, height))
        image.putdata([colors[index] for index in linear])

        # The Japanese tagline sits on the black strip below "SOUND SPIRIT".
        # Restrict the repaint to its full width to preserve adjacent logo art.
        canvas = image.resize((width * scale, height * scale), Image.Resampling.NEAREST)
        draw = ImageDraw.Draw(canvas)
        draw.rectangle(
            (x1 * scale, y1 * scale, (x2 + 1) * scale - 1, (y2 + 1) * scale - 1),
            fill=(0, 0, 0),
        )
        bounds = draw.textbbox((0, 0), text, font=font, stroke_width=scale)
        text_width, text_height = bounds[2] - bounds[0], bounds[3] - bounds[1]
        box_width, box_height = (x2 - x1 + 1) * scale, (y2 - y1 + 1) * scale
        if text_width > box_width - 8 * scale or text_height > box_height - 2 * scale:
            raise SystemExit(f"English title subtitle does not fit the logo: {text!r}")
        left = x1 * scale + (box_width - text_width) // 2 - bounds[0]
        top = y1 * scale + (box_height - text_height) // 2 - bounds[1]
        draw.text(
            (left, top), text, font=font, fill=(255, 205, 45),
            stroke_width=scale, stroke_fill=(62, 25, 13),
        )
        image = canvas.resize((width, height), Image.Resampling.LANCZOS)

        # Preserve source pixels outside the Japanese subtitle rectangle. Quantize
        # against this frame's complete palette, as each animation frame has its
        # own backdrop palette; only write indices in the replaced artwork region.
        palette_image = Image.new("P", (1, 1))
        palette_image.putpalette([channel for color in colors for channel in color])
        indexed = image.quantize(palette=palette_image, dither=Image.Dither.NONE)
        linear = indexed.tobytes()
        for y in range(y1, y2 + 1):
            for x in range(x1, x2 + 1):
                tiled_offset = ((y // 8) * (width // 8) + x // 8) * 64 + (y % 8) * 8 + x % 8
                pixels[tiled_offset] = linear[y * width + x]
        texture[data_offset:data_offset + data_size] = pixels
        rom[file_start + entry_offset:file_start + entry_offset + entry_size] = texture
        patched_frames += 1
    return patched_frames



def patch_battle_ui_english(rom: bytearray, files: dict[str, tuple[int, int]]) -> int:
    """Replace localized Japanese battle-command labels in the CT 4-bpp atlas."""
    filename = "data/btl2cim.pac"
    if filename not in files:
        raise SystemExit(f"Missing battle UI graphics: {filename}")
    file_start, file_size = files[filename]
    source = bytes(rom[file_start:file_start + file_size])
    if source[:4] != b"PK\x00\x01":
        raise SystemExit(f"Invalid battle UI PAC header: {filename}")
    entry_count = struct.unpack_from("<I", source, 4)[0]
    if entry_count != 29 or 16 + entry_count * 16 > file_size:
        raise SystemExit("Unexpected battle UI texture table")
    entry_offset, entry_size = struct.unpack_from("<II", source, 16 + 1 * 16)
    if entry_offset + entry_size > file_size:
        raise SystemExit("Battle command labels are outside their PAC")
    texture = bytearray(source[entry_offset:entry_offset + entry_size])
    if texture[:4] != b"CT\x60\x00" or struct.unpack_from("<HH", texture, 2) != (96, 144):
        raise SystemExit("Unexpected battle-command texture dimensions")
    if texture[8] != 0x20:
        raise SystemExit("Battle-command labels are not 4-bpp")
    data_size, data_offset = struct.unpack_from("<II", texture, 16)
    palette_offset = struct.unpack_from("<I", texture, 20)[0]
    if data_size != 0x1B00 or data_offset != 0x40 or palette_offset != 0x40:
        raise SystemExit("Unexpected battle-command texture layout")
    pixels = bytearray(texture[data_offset:data_offset + data_size])
    # These six 96x24 button strips are the actual battle commands in the
    # existing 96x144 atlas, replacing attack/defend/force/charge/change/purify.
    labels = ("Attack", "Defend", "Dragon Force", "FP Charge", "Change", "Purify")
    font = ImageFont.truetype("C:/Windows/Fonts/arialbd.ttf", 12)
    expected = (0x03E0, 0x28E1, 0x7AC3, 0x1840, 0x0BDF, 0x016B, 0x473F, 0x1970, 0x3AFF, 0x2ABF, 0x225F, 0x1DDD, 0x42BF, 0x571E, 0x08F5, 0x0447)
    # Source archive identifies the Japanese button atlas by its format and palette content.
    source_palette = tuple(struct.unpack_from("<H", texture, 0x20 + index * 2)[0] for index in range(16))
    if source_palette != expected:
        raise SystemExit("Unexpected battle command label palette; refusing to redraw")
    row_height = 24
    for row, label in enumerate(labels):
        top = row * row_height
        mask = Image.new("L", (96, row_height))
        draw = ImageDraw.Draw(mask)
        bounds = draw.textbbox((0, 0), label, font=font)
        text_w, text_h = bounds[2] - bounds[0], bounds[3] - bounds[1]
        if text_w > 86 or text_h > 17:
            raise SystemExit(f"Battle command label does not fit: {label!r}")
        draw.text(((96 - text_w) // 2 - bounds[0], (row_height - text_h) // 2 - bounds[1]), label, font=font, fill=255)
        for local_y in range(3, 21):
            y = top + local_y
            for x in range(4, 92):
                at = ((y // 8) * (96 // 8) + x // 8) * 32 + (y % 8) * 4 + (x % 8) // 2
                shift = (x % 2) * 4
                # A flat pale interior gives the larger dark lettering clear
                # contrast while retaining the original button borders.
                shade = 6
                pixels[at] = (pixels[at] & ~(0xF << shift)) | (shade << shift)
                if mask.getpixel((x, local_y)) >= 96:
                    pixels[at] = (pixels[at] & ~(0xF << shift)) | (15 << shift)
    texture[data_offset:data_offset + data_size] = pixels
    rom[file_start + entry_offset:file_start + entry_offset + entry_size] = texture
    return len(labels)



def bps_number(value: int) -> bytes:
    result = bytearray()
    while True:
        byte = value & 0x7F
        value >>= 7
        if value == 0:
            result.append(byte | 0x80)
            return bytes(result)
        result.append(byte)
        value -= 1


def crc32(data: bytes) -> int:
    return zlib.crc32(data) & 0xFFFFFFFF


def make_bps(source: bytes, target: bytes) -> bytes:
    """Encode simple copy-and-literal runs into a standards-compliant BPS1 patch."""
    patch = bytearray(b"BPS1")
    patch += bps_number(len(source))
    patch += bps_number(len(target))
    patch += bps_number(0)
    pos = 0
    # Keep scanning linear: one SourceRead run for unchanged bytes and short literals for edits.
    while pos < len(target):
        if target[pos] == source[pos]:
            end = pos + 1
            while end < len(target) and target[end] == source[end]:
                end += 1
            patch += bps_number(((end - pos - 1) << 2) | 0)  # SourceRead
            pos = end
        else:
            end = pos + 1
            while end < len(target) and target[end] != source[end]:
                end += 1
            literal = target[pos:end]
            patch += bps_number(((len(literal) - 1) << 2) | 1)  # TargetRead
            patch += literal
            pos = end
    patch += struct.pack("<II", crc32(source), crc32(target))
    patch += struct.pack("<I", crc32(patch))
    return bytes(patch)


def apply_bps(source: bytes, patch: bytes) -> bytes:
    if patch[:4] != b"BPS1":
        raise ValueError("Not a BPS1 patch")
    cursor = 4

    def read_number() -> int:
        nonlocal cursor
        value = shift = 0
        while True:
            byte = patch[cursor]
            cursor += 1
            value += (byte & 0x7F) << shift
            if byte & 0x80:
                return value
            shift += 7
            value += 1 << shift

    source_size, target_size, metadata_size = read_number(), read_number(), read_number()
    if source_size != len(source):
        raise ValueError("Source ROM size does not match patch")
    cursor += metadata_size
    target = bytearray()
    source_relative = target_relative = 0
    while len(target) < target_size:
        action = read_number()
        mode, length = action & 3, (action >> 2) + 1
        if mode == 0:
            start = len(target)
            target.extend(source[start:start + length])
        elif mode == 1:
            target.extend(patch[cursor:cursor + length])
            cursor += length
        elif mode == 2:
            delta = read_number()
            source_relative += -(delta >> 1) if delta & 1 else (delta >> 1)
            target.extend(source[source_relative:source_relative + length])
            source_relative += length
        else:
            delta = read_number()
            target_relative += -(delta >> 1) if delta & 1 else (delta >> 1)
            for _ in range(length):
                target.append(target[target_relative])
                target_relative += 1
    expected_source_crc, expected_target_crc, expected_patch_crc = struct.unpack_from("<III", patch, len(patch) - 12)
    if crc32(source) != expected_source_crc or crc32(target) != expected_target_crc or crc32(patch[:-4]) != expected_patch_crc:
        raise ValueError("BPS checksum validation failed")
    return bytes(target)


def main() -> None:
    original = read_source_bytes()
    source = read_rom(original)
    rom_files = file_table(source)
    translations = json.loads(TRANSLATIONS.read_text(encoding="utf-8"))
    glyph_count = validate_ascii_font(source, rom_files, translations)
    translated_count = apply_translations(source, rom_files)
    prologue_count = apply_offset_translations(source, rom_files, PROLOGUE_TRANSLATIONS, "prologue")
    # The opening translation table also includes these reviewed offsets, with
    # legacy wording; apply the offset-table copy after its source is validated.
    for offset_rows in (
        json.loads(PROLOGUE_TRANSLATIONS.read_text(encoding="utf-8")),
        json.loads(CHAPTER1_TRANSLATIONS.read_text(encoding="utf-8")),
    ):
        file_start, file_size = rom_files["data/new_script_dat.pac"]
        for offset_text, row in offset_rows.items():
            offset = int(offset_text)
            expected = row["ja"].encode("shift_jis")
            replacement = row["en"].encode("ascii")
            if offset < 0 or offset + len(expected) >= file_size:
                raise SystemExit(f"Reviewed opening translation is outside the script at {offset:#x}")
            absolute = file_start + offset
            if bytes(original[file_start + offset:file_start + offset + len(expected)]) != expected:
                raise SystemExit(f"Japanese source mismatch at data/new_script_dat.pac+{offset:#x}")
            if original[file_start + offset + len(expected)] != 0:
                raise SystemExit(f"Expected NUL terminator missing at data/new_script_dat.pac+{offset:#x}")
            source[absolute:absolute + len(expected)] = replacement.ljust(len(expected), b"\0")
    chapter1_count = apply_chapter1_translations(source, rom_files)
    chapter2_count = apply_offset_translations(source, rom_files, CHAPTER2_TRANSLATIONS, "chapter two")
    chapter3_count = apply_offset_translations(source, rom_files, CHAPTER3_TRANSLATIONS, "chapter three")
    chapter4_count = apply_offset_translations(source, rom_files, CHAPTER4_TRANSLATIONS, "chapter four")
    chapter5_count = apply_offset_translations(source, rom_files, CHAPTER5_TRANSLATIONS, "chapter five")
    chapter6_count = apply_offset_translations(source, rom_files, CHAPTER6_TRANSLATIONS, "chapter six")
    chapter7_count = apply_offset_translations(source, rom_files, CHAPTER7_TRANSLATIONS, "chapter seven")
    chapter8_count = apply_offset_translations(source, rom_files, CHAPTER8_TRANSLATIONS, "chapter eight")
    chapter9_count = apply_offset_translations(source, rom_files, CHAPTER9_TRANSLATIONS, "chapter nine")
    chapter10_count = apply_offset_translations(source, rom_files, CHAPTER10_TRANSLATIONS, "chapter ten")
    chapter11_count = apply_offset_translations(source, rom_files, CHAPTER11_TRANSLATIONS, "chapter eleven")
    chapter12_count = apply_offset_translations(source, rom_files, CHAPTER12_TRANSLATIONS, "chapter twelve")
    chapter13_count = apply_offset_translations(source, rom_files, CHAPTER13_TRANSLATIONS, "chapter thirteen")
    chapter14_count = apply_offset_translations(source, rom_files, CHAPTER14_TRANSLATIONS, "chapter fourteen")
    chapter15_count = apply_offset_translations(source, rom_files, CHAPTER15_TRANSLATIONS, "chapter fifteen")
    chapter16_count = apply_offset_translations(source, rom_files, CHAPTER16_TRANSLATIONS, "chapter sixteen")
    chapter17_count = apply_offset_translations(source, rom_files, CHAPTER17_TRANSLATIONS, "chapter seventeen")
    chapter18_count = apply_offset_translations(source, rom_files, CHAPTER18_TRANSLATIONS, "chapter eighteen")
    chapter19_count = apply_offset_translations(source, rom_files, CHAPTER19_TRANSLATIONS, "chapter nineteen")
    chapter20_count = apply_offset_translations(source, rom_files, CHAPTER20_TRANSLATIONS, "chapter twenty")
    chapter21_count = apply_offset_translations(source, rom_files, CHAPTER21_TRANSLATIONS, "chapter twenty-one")
    chapter22_count = apply_offset_translations(source, rom_files, CHAPTER22_TRANSLATIONS, "chapter twenty-two")
    chapter23_count = apply_offset_translations(source, rom_files, CHAPTER23_TRANSLATIONS, "chapter twenty-three")
    extra_count = apply_extra_translations(source, rom_files)
    menu_count = apply_menu_translations(source, rom_files)
    shop_nest_count = apply_shop_nest_translations(source, rom_files)
    interface_count = apply_interface_translations(source, rom_files)
    help_text_count = apply_help_text_translations(source, rom_files)
    item_name_count = apply_item_name_translations(source, rom_files)
    item_description_count = apply_item_description_translations(source, rom_files)
    dragon_force_count = apply_dragon_force_translations(source, rom_files)
    graphic_label_count = patch_command_menu_graphics(source, rom_files)
    title_label_count = patch_title_menu_graphics(source, rom_files)
    logo_frame_count = patch_title_logo_graphics(source, rom_files)
    battle_graphic_count = patch_battle_ui_english(source, rom_files)
    from patch_intro_read import install as install_intro_read
    install_intro_read(source, rom_files, PROJECT)
    from patch_battle_readability import install as install_battle_readability
    install_battle_readability(source, rom_files, PROJECT)
    from patch_remaining_ui import install as install_remaining_ui
    install_remaining_ui(source, file_table(source), PROJECT)
    from patch_map_icons import install as install_map_icons
    install_map_icons(source, file_table(source), PROJECT)
    from patch_battle_nest_text import install as install_battle_nest_text
    install_battle_nest_text(source, file_table(source), PROJECT)
    from patch_nest_graphics import install as install_nest_graphics
    install_nest_graphics(source, file_table(source), PROJECT)
    from patch_map_layout import install as install_map_layout
    install_map_layout(source, file_table(source), PROJECT)
    from patch_boot_credits import install as install_boot_credits
    install_boot_credits(source, file_table(source), PROJECT)
    from patch_audit_text import install as install_audit_text
    install_audit_text(source, file_table(source), PROJECT)
    from patch_audit_graphics import install as install_audit_graphics
    install_audit_graphics(source, file_table(source), PROJECT)
    from repack_script import install
    install(source, original, rom_files, PROJECT)
    from repack_map import install as install_map
    install_map(source, original, rom_files, PROJECT)
    if FULL_DRAFT:
        from repack_help_label import install as install_help
        install_help(source, rom_files)
    target = bytes(source)
    patch = make_bps(original, target)
    if apply_bps(original, patch) != target:
        raise SystemExit("Generated BPS patch failed round-trip validation")
    OUTPUT.write_bytes(target)
    PATCH.parent.mkdir(parents=True, exist_ok=True)
    PATCH.write_bytes(patch)
    print(f"Patched {translated_count + extra_count + prologue_count + chapter1_count + chapter2_count + chapter3_count + chapter4_count + chapter5_count + chapter6_count + chapter7_count + chapter8_count + chapter9_count + chapter10_count + chapter11_count + chapter12_count + chapter13_count + chapter14_count + chapter15_count + chapter16_count + chapter17_count + chapter18_count + chapter19_count + chapter20_count + chapter21_count + chapter22_count + chapter23_count} legacy fixed-slot story entries ({prologue_count} prologue, {chapter1_count} awakening, {chapter2_count} chapter two, {chapter3_count} chapter three, {chapter4_count} chapter four, {chapter5_count} chapter five, {chapter6_count} chapter six, {chapter7_count} chapter seven, {chapter8_count} chapter eight, {chapter9_count} chapter nine, {chapter10_count} chapter ten, {chapter11_count} chapter eleven, {chapter12_count} chapter twelve, {chapter13_count} chapter thirteen, {chapter14_count} chapter fourteen, {chapter15_count} chapter fifteen, {chapter16_count} chapter sixteen, {chapter17_count} chapter seventeen, {chapter18_count} chapter eighteen, {chapter19_count} chapter nineteen, {chapter20_count} chapter twenty, {chapter21_count} chapter twenty-one, {chapter22_count} chapter twenty-two, {chapter23_count} chapter twenty-three), {menu_count} system prompts, {shop_nest_count} shop/Nest strings, {interface_count} help headings and {help_text_count} help paragraphs, {item_name_count} item names, {item_description_count} item descriptions, {dragon_force_count} Dragon Force descriptions, {graphic_label_count} command-menu labels, {title_label_count} title/settings sprites, {logo_frame_count} title-logo frames, and {battle_graphic_count} battle-command labels; verified {glyph_count} existing ASCII font glyphs")
    print(f"ROM: {OUTPUT} ({len(target)} bytes, SHA-256 {hashlib.sha256(target).hexdigest()})")
    print(f"BPS: {PATCH} ({len(patch)} bytes)")


if __name__ == "__main__":
    try:
        main()
    except (KeyError, ValueError, struct.error, UnicodeDecodeError) as exc:
        print(f"Build failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
