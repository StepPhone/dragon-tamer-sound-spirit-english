#!/usr/bin/env python3
"""Extract a Nintendo DS ROM's files and executable components without modifying it.

Requires ndspy (https://ndspy.readthedocs.io/). NitroFS payloads are extracted
byte-for-byte; compressed ARM9/ARM7 code and compressed overlays are additionally
written in decompressed form while their original stored forms are preserved.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import struct
import sys
from pathlib import Path, PurePosixPath
from zipfile import BadZipFile, ZipFile

import ndspy.rom
from ndspy import codeCompression

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = ROOT / "Dragon Tamer - Sound Spirit (Japan).zip"
DEFAULT_OUT = Path(__file__).resolve().parent / "extracted_rom"


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def read_source(source: Path) -> tuple[bytes, str]:
    if source.suffix.lower() == ".zip":
        try:
            with ZipFile(source) as archive:
                candidates = [name for name in archive.namelist() if name.lower().endswith(".nds")]
                if len(candidates) != 1:
                    raise ValueError(f"Expected exactly one .nds member in {source}; found {len(candidates)}")
                return archive.read(candidates[0]), candidates[0]
        except BadZipFile as exc:
            raise ValueError(f"Invalid ZIP archive: {source}") from exc
    return source.read_bytes(), source.name


def safe_relative_path(name: str) -> Path:
    posix = PurePosixPath(name)
    if posix.is_absolute() or not posix.parts or any(part in ("", ".", "..") for part in posix.parts):
        raise ValueError(f"Unsafe path in ROM filename table: {name!r}")
    return Path(*posix.parts)


def write_file(base: Path, relative: str, data: bytes) -> dict:
    path = safe_relative_path(relative)
    target = base / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    return {"path": path.as_posix(), "size": len(data), "sha256": sha256(data)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", nargs="?", type=Path, default=DEFAULT_SOURCE, help="input .nds or .zip")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT, help="output directory (default: dragon_tamer_translation/extracted_rom)")
    args = parser.parse_args()

    source = args.source.resolve()
    output = args.out.resolve()
    if output == source or source in output.parents or output in source.parents:
        parser.error("output and source must be separate, non-overlapping paths")
    rom_bytes, archive_member = read_source(source)
    rom = ndspy.rom.NintendoDSRom(rom_bytes)
    if bytes(rom.idCode) != b"AGOJ":
        raise ValueError(f"Expected Dragon Tamer game code AGOJ; found {bytes(rom.idCode)!r}")

    header = {
        "title": bytes(rom.name).decode("ascii", errors="replace").rstrip("\0"),
        "game_code": bytes(rom.idCode).decode("ascii"),
        "source": str(source),
        "source_member": archive_member,
        "source_size": len(rom_bytes),
        "source_sha256": sha256(rom_bytes),
        "header_arm9_source_offset": struct.unpack_from("<I", rom_bytes, 0x20)[0],
        "secure_area_note": "DS Secure Area is at ROM offsets 0x4000-0x7FFF for this layout; BIOS KEY1 secure-boot encryption is not the same as whole-ROM encryption.",
    }

    output.mkdir(parents=True, exist_ok=True)
    files_dir = output / "nitrofs"
    if files_dir.exists() and any(files_dir.iterdir()):
        raise FileExistsError(f"Refusing to overwrite a non-empty extraction directory: {files_dir}")
    files_dir.mkdir(parents=True, exist_ok=True)

    manifest = []
    named_ids = set()
    for file_id, data in enumerate(rom.files):
        name = rom.filenames.filenameOf(file_id)
        if name is None:
            relative = f"_unnamed/file_{file_id:04d}.bin"
        else:
            relative = name
            named_ids.add(file_id)
        row = write_file(files_dir, relative, bytes(data))
        row.update({"file_id": file_id, "named": name is not None, "stored_sha256": row["sha256"]})
        manifest.append(row)

    # The table should name every FAT entry in this ROM; preserve the gap if it does not.
    if len(named_ids) != len(rom.files) - sum(1 for row in manifest if not row["named"]):
        raise ValueError("FNT name lookup did not cover the expected file-table entries")

    code_dir = output / "code"
    code_dir.mkdir(exist_ok=True)
    code_manifest = []
    for label, data, ram_address in (
        ("arm9", bytes(rom.arm9), rom.arm9RamAddress),
        ("arm7", bytes(rom.arm7), rom.arm7RamAddress),
    ):
        stored = write_file(code_dir, f"{label}.stored.bin", data)
        expanded = codeCompression.decompress(data)
        decoded = write_file(code_dir, f"{label}.bin", expanded)
        decoded.update({"stored_path": stored["path"], "stored_sha256": stored["sha256"], "ram_address": ram_address, "decompressed": expanded != data})
        code_manifest.append(decoded)

    overlay_manifest = []
    for label, table, loader in (
        ("arm9", bytes(rom.arm9OverlayTable), rom.loadArm9Overlays),
        ("arm7", bytes(rom.arm7OverlayTable), rom.loadArm7Overlays),
    ):
        table_dir = output / "overlays"
        table_dir.mkdir(exist_ok=True)
        table_info = write_file(table_dir, f"{label}_table.bin", table)
        for overlay_id, overlay in sorted(loader().items()):
            file_name = rom.filenames.filenameOf(overlay.fileID)
            stored_data = bytes(rom.files[overlay.fileID])
            directory = table_dir / label
            stored = write_file(directory, f"{overlay_id:04d}.stored.bin", stored_data)
            decoded = write_file(directory, f"{overlay_id:04d}.bin", bytes(overlay.data))
            decoded.update({
                "overlay_id": overlay_id,
                "file_id": overlay.fileID,
                "rom_filename": file_name,
                "ram_address": overlay.ramAddress,
                "ram_size": overlay.ramSize,
                "bss_size": overlay.bssSize,
                "compressed": overlay.compressed,
                "stored_path": stored["path"],
                "stored_sha256": stored["sha256"],
            })
            overlay_manifest.append(decoded)
        if table_info["size"] % 32:
            raise ValueError(f"Malformed {label} overlay table size: {table_info['size']}")

    other_manifest = []
    for relative, data in (
        ("header.bin", rom_bytes[:0x200]),
        ("banner.bin", bytes(rom.iconBanner)),
        ("arm9_post_data.bin", bytes(rom.arm9PostData)),
        ("arm9_overlay_table.bin", bytes(rom.arm9OverlayTable)),
        ("arm7_overlay_table.bin", bytes(rom.arm7OverlayTable)),
    ):
        other_manifest.append(write_file(output, relative, data))

    header.update({
        "nitrofs_file_count": len(manifest),
        "named_nitrofs_file_count": sum(row["named"] for row in manifest),
        "unnamed_nitrofs_file_count": sum(not row["named"] for row in manifest),
        "total_nitrofs_bytes": sum(row["size"] for row in manifest),
        "arm_overlay_count": len(overlay_manifest),
        "nitrofs": manifest,
        "code": code_manifest,
        "overlays": overlay_manifest,
        "other_components": other_manifest,
    })
    (output / "manifest.json").write_text(json.dumps(header, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    # Round-trip check that ndspy parsed every NitroFS file from the exact source bytes.
    for row in manifest:
        extracted = (files_dir / safe_relative_path(row["path"])).read_bytes()
        if len(extracted) != row["size"] or sha256(extracted) != row["sha256"]:
            raise ValueError(f"Extraction verification failed for {row['path']}")
    print(f"Source ROM SHA-256: {header['source_sha256']}")
    print(f"Extracted {len(manifest)} NitroFS files ({header['named_nitrofs_file_count']} named, {header['unnamed_nitrofs_file_count']} unnamed), totaling {header['total_nitrofs_bytes']:,} bytes.")
    print(f"Extracted {len(overlay_manifest)} overlays and {len(code_manifest)} main executables.")
    print(f"Output: {output}")
    print(f"Inventory: {output / 'manifest.json'}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, struct.error) as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
