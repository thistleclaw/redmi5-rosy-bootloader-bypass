#!/usr/bin/env python3
"""Split a monolithic Qualcomm ELF MBN (e.g. keymaster.mbn) into PIL .mdt + .bXX files.

Used to place Oreo 8.1 keymaster.* PIL segments into /vendor/firmware_mnt/image/
(modem partition) so QSEE can load keymaster dynamically when GPT 'keymaster' is hidden.
"""

import argparse
import struct
from pathlib import Path

ELF_MAGIC = b"\x7fELF"


def split_mbn(mbn_path: Path, out_dir: Path, prefix: str | None = None) -> None:
    """Extract .mdt (ELF + program headers + hash segment) and .b00..bNN segment files."""
    data = mbn_path.read_bytes()
    if len(data) < 52 or not data.startswith(ELF_MAGIC):
        raise ValueError(f"{mbn_path} is not an ELF MBN file")

    ei_class = data[4]
    if ei_class == 1:
        e_phoff = struct.unpack_from("<I", data, 28)[0]
        e_phentsize, e_phnum = struct.unpack_from("<HH", data, 42)
        ph_fmt = "<8I"
    elif ei_class == 2:
        e_phoff = struct.unpack_from("<Q", data, 32)[0]
        e_phentsize, e_phnum = struct.unpack_from("<HH", data, 54)
        ph_fmt = "<2I6Q"
    else:
        raise ValueError(f"Unsupported ELF class {ei_class}")

    stem = prefix or mbn_path.stem
    out_dir.mkdir(parents=True, exist_ok=True)

    segments: list[bytes] = []
    for idx in range(e_phnum):
        off = e_phoff + idx * e_phentsize
        if ei_class == 1:
            _, p_offset, _, _, p_filesz, _, _, _ = struct.unpack_from(ph_fmt, data, off)
        else:
            _, _, p_offset, _, _, p_filesz, _, _ = struct.unpack_from(ph_fmt, data, off)
        seg = data[p_offset : p_offset + p_filesz]
        segments.append(seg)
        (out_dir / f"{stem}.b{idx:02d}").write_bytes(seg)

    # .mdt = ELF header + program headers + hash table segment (segment 1 when >= 2 segments)
    mdt = bytearray(data[: e_phoff + e_phnum * e_phentsize])
    if len(segments) > 1:
        mdt.extend(segments[1])
    (out_dir / f"{stem}.mdt").write_bytes(bytes(mdt))

    print(f"Split {mbn_path} into {stem}.mdt + {e_phnum} segments in {out_dir}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mbn", type=Path, help="Input Qualcomm ELF MBN (e.g., keymaster.mbn)")
    parser.add_argument("out_dir", type=Path, help="Output directory for .mdt and .bXX files")
    parser.add_argument("--prefix", default=None, help="Output basename (defaults to MBN stem)")
    args = parser.parse_args()
    split_mbn(args.mbn, args.out_dir, args.prefix)


if __name__ == "__main__":
    main()
