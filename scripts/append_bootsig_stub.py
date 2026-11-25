#!/usr/bin/env python3
"""Append the 4KB ASN.1 DER BootSignature block from stock boot/recovery to an unsigned image.

aboot (boot_verifier.c) inspects the 4096 bytes immediately following
page_size + align(kernel) + align(ramdisk) + align(second) and panics into EDL
(05c6:900e) unless the first byte at that offset is 0x30 (ASN.1 SEQUENCE).
"""

import argparse
import struct
from pathlib import Path

ANDROID_BOOT_MAGIC = b"ANDROID!"
SIG_BLOCK_SIZE = 4096


def compute_image_end(img: bytes) -> int:
    """Parse Android boot image header (v0-v2 compatible) and return aligned payload end offset."""
    if len(img) < 40 or not img.startswith(ANDROID_BOOT_MAGIC):
        raise ValueError("Image does not start with ANDROID! magic")
    _, ksz, _, rsz, _, ssz, _, _, psz = struct.unpack_from("<8s8I", img, 0)
    if psz == 0 or (psz & (psz - 1)) != 0:
        raise ValueError(f"Invalid page size {psz}")

    def align(size: int) -> int:
        return ((size + psz - 1) // psz) * psz

    return psz + align(ksz) + align(rsz) + align(ssz)


def append_bootsig(stock_img: Path, target_img: Path, out_img: Path) -> None:
    """Extract stock 4KB BootSignature block and append it at aligned end of target_img."""
    stock = stock_img.read_bytes()
    stock_end = compute_image_end(stock)
    sig_block = stock[stock_end : stock_end + SIG_BLOCK_SIZE]
    if len(sig_block) != SIG_BLOCK_SIZE or sig_block[0] != 0x30:
        raise ValueError(
            f"Stock image {stock_img} lacks valid 0x30 DER signature at offset {stock_end}"
        )

    target = target_img.read_bytes()
    target_end = compute_image_end(target)
    if target_end > len(target):
        payload = target + b"\x00" * (target_end - len(target))
    else:
        payload = target[:target_end]

    result = payload + sig_block
    out_img.write_bytes(result)
    print(
        f"Wrote {out_img}: payload={target_end} bytes + {SIG_BLOCK_SIZE}-byte DER stub "
        f"(total={len(result)} bytes)"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stock", type=Path, help="Stock signed boot.bin or recovery.bin")
    parser.add_argument("target", type=Path, help="Unsigned custom boot/recovery image")
    parser.add_argument("output", type=Path, help="Output image with DER stub appended")
    args = parser.parse_args()
    append_bootsig(args.stock, args.target, args.output)


if __name__ == "__main__":
    main()
