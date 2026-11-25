#!/usr/bin/env python3
"""Neutralize SPLASH!! magic in splash.bin so aboot skips splash_warn shutdown."""

import argparse
from pathlib import Path

SPLASH_MAGIC = b"SPLASH!!"
NEUTRAL_MAGIC = b"NOSPLASH"


def patch_splash(src: Path, dst: Path) -> None:
    """Replace leading SPLASH!! magic with NOSPLASH while keeping geometry intact."""
    data = bytearray(src.read_bytes())
    if not data.startswith(SPLASH_MAGIC):
        raise ValueError(f"{src} does not start with {SPLASH_MAGIC!r} (got {data[:8]!r})")
    data[: len(SPLASH_MAGIC)] = NEUTRAL_MAGIC
    dst.write_bytes(data)
    print(f"Patched {dst}: header {SPLASH_MAGIC!r} -> {NEUTRAL_MAGIC!r}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="Input splash.bin")
    parser.add_argument("output", type=Path, help="Output splash_nosplash.bin")
    args = parser.parse_args()
    patch_splash(args.input, args.output)


if __name__ == "__main__":
    main()
