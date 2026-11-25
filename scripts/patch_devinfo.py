#!/usr/bin/env python3
"""Set is_unlocked = 1 in a Qualcomm ANDROID-BOOT! devinfo partition image."""

import argparse
from pathlib import Path

DEVINFO_MAGIC = b"ANDROID-BOOT!\x00\x00\x00"
IS_UNLOCKED_OFFSET = 0x10


def patch_devinfo(src: Path, dst: Path) -> None:
    """Validate devinfo header and set byte 0x10 (is_unlocked) to 1."""
    data = bytearray(src.read_bytes())
    if len(data) < 0x20 or not data.startswith(DEVINFO_MAGIC):
        raise ValueError(f"{src} is not a valid ANDROID-BOOT! devinfo image")
    old_val = data[IS_UNLOCKED_OFFSET]
    data[IS_UNLOCKED_OFFSET] = 1
    dst.write_bytes(data)
    print(f"Patched {dst}: is_unlocked {old_val} -> 1 (offset 0x{IS_UNLOCKED_OFFSET:x})")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="Input devinfo.bin")
    parser.add_argument("output", type=Path, help="Output unlocked devinfo image")
    args = parser.parse_args()
    patch_devinfo(args.input, args.output)


if __name__ == "__main__":
    main()
