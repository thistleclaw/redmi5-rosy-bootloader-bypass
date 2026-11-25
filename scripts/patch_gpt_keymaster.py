#!/usr/bin/env python3
"""Rename a GPT partition entry (e.g. keymaster -> keymaste1) and update GPT CRCs.

Works on both primary GPT dumps (512B MBR + 512B header + entry array) and
backup GPT dumps (entry array + 512B header).
"""

import argparse
import struct
import zlib
from pathlib import Path

GPT_SIGNATURE = b"EFI PART"
ENTRY_SIZE = 128


def _detect_layout(buf: bytes) -> tuple[int, int]:
    """Return (header_offset, entries_offset) for a primary or backup GPT blob."""
    if len(buf) >= 1024 and buf[512:520] == GPT_SIGNATURE:
        return 512, 1024
    if len(buf) >= 1024 and buf[-512:-504] == GPT_SIGNATURE:
        return len(buf) - 512, 0
    raise ValueError("Could not locate 'EFI PART' header in primary (0x200) or backup (-0x200) slot")


def patch_gpt(src: Path, dst: Path, old_name: str, new_name: str) -> None:
    """Rename partition entry in GPT and recompute array + header CRC32 checksums."""
    if len(new_name) > 35:
        raise ValueError("GPT UTF-16LE partition name must be <= 35 characters")

    data = bytearray(src.read_bytes())
    hdr_off, arr_off = _detect_layout(data)

    hdr_size = struct.unpack_from("<I", data, hdr_off + 12)[0]
    num_entries, entry_size = struct.unpack_from("<II", data, hdr_off + 80)
    if entry_size != ENTRY_SIZE:
        raise ValueError(f"Unsupported GPT entry size {entry_size} (expected {ENTRY_SIZE})")

    arr_len = num_entries * entry_size
    if arr_off + arr_len > len(data):
        raise ValueError("Truncated GPT partition entry array")

    found = False
    for idx in range(num_entries):
        e_off = arr_off + idx * entry_size
        raw_name = bytes(data[e_off + 56 : e_off + 128])
        name = raw_name.decode("utf-16-le").rstrip("\x00")
        if name == old_name:
            encoded = new_name.encode("utf-16-le").ljust(72, b"\x00")
            data[e_off + 56 : e_off + 128] = encoded
            found = True
            print(f"Renamed partition #{idx}: {old_name!r} -> {new_name!r}")
            break

    if not found:
        raise ValueError(f"Partition {old_name!r} not found in {src}")

    arr_crc = zlib.crc32(data[arr_off : arr_off + arr_len]) & 0xFFFFFFFF
    struct.pack_into("<I", data, hdr_off + 88, arr_crc)
    struct.pack_into("<I", data, hdr_off + 16, 0)
    hdr_crc = zlib.crc32(data[hdr_off : hdr_off + hdr_size]) & 0xFFFFFFFF
    struct.pack_into("<I", data, hdr_off + 16, hdr_crc)

    dst.write_bytes(data)
    print(f"Wrote {dst}: array_crc=0x{arr_crc:08x}, header_crc=0x{hdr_crc:08x}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="Input gpt_main.bin or gpt_bak.bin")
    parser.add_argument("output", type=Path, help="Output patched GPT binary")
    parser.add_argument("--old", default="keymaster", help="Existing partition name (default: keymaster)")
    parser.add_argument("--new", default="keymaste1", help="Replacement name (default: keymaste1)")
    args = parser.parse_args()
    patch_gpt(args.input, args.output, args.old, args.new)


if __name__ == "__main__":
    main()
