#!/usr/bin/env bash
set -euo pipefail

# Patch a custom boot.img with Magisk (via adb on device) and append the
# 4KB ASN.1 DER BootSignature stub required by rosy's aboot.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

usage() {
  cat <<EOF
Usage: $(basename "$0") <Magisk.apk> <input_boot.img> <stock_boot.bin> <output_signed_boot.img>

Patches <input_boot.img> using Magisk's arm64-v8a binaries extracted from <Magisk.apk>
over ADB, then appends the 4096-byte ASN.1 DER stub from <stock_boot.bin> so aboot
does not panic into EDL (05c6:900e).
EOF
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" || $# -ne 4 ]]; then
  usage
  exit $([[ $# -eq 4 ]] && echo 0 || echo 1)
fi

MAGISK_APK="$1"
INPUT_BOOT="$2"
STOCK_BOOT="$3"
OUTPUT_BOOT="$4"

for f in "$MAGISK_APK" "$INPUT_BOOT" "$STOCK_BOOT"; do
  if [[ ! -f "$f" ]]; then
    echo "Error: file not found: $f" >&2
    exit 1
  fi
done

for cmd in adb unzip python3; do
  if ! command -v "$cmd" >/dev/null 2>&1; then
    echo "Error: required command not found: $cmd" >&2
    exit 1
  fi
done

WORKDIR="$(mktemp -d)"
REMOTE_DIR="/data/local/tmp/magisk_patch"
trap 'rm -rf "$WORKDIR"; adb shell "rm -rf $REMOTE_DIR" >/dev/null 2>&1 || true' EXIT

echo "[1/4] Extracting Magisk arm64-v8a patcher files..."
unzip -p "$MAGISK_APK" assets/boot_patch.sh > "$WORKDIR/boot_patch.sh"
unzip -p "$MAGISK_APK" assets/util_functions.sh > "$WORKDIR/util_functions.sh"
unzip -p "$MAGISK_APK" lib/arm64-v8a/libmagiskinit.so > "$WORKDIR/magiskinit"
unzip -p "$MAGISK_APK" lib/arm64-v8a/libmagisk.so > "$WORKDIR/magisk"
unzip -p "$MAGISK_APK" lib/arm64-v8a/libmagiskboot.so > "$WORKDIR/magiskboot"
unzip -p "$MAGISK_APK" lib/arm64-v8a/libinit-ld.so > "$WORKDIR/init-ld"
cp "$INPUT_BOOT" "$WORKDIR/boot.img"

echo "[2/4] Pushing files and running boot_patch.sh on device..."
adb wait-for-device
adb shell "rm -rf $REMOTE_DIR && mkdir -p $REMOTE_DIR"
adb push "$WORKDIR"/* "$REMOTE_DIR/" >/dev/null
adb shell "cd $REMOTE_DIR && sh boot_patch.sh boot.img"

echo "[3/4] Pulling repacked boot image..."
adb pull "$REMOTE_DIR/new-boot.img" "$WORKDIR/new-boot.img" >/dev/null

echo "[4/4] Appending 4KB ASN.1 DER BootSignature stub..."
python3 "$SCRIPT_DIR/append_bootsig_stub.py" \
  "$STOCK_BOOT" \
  "$WORKDIR/new-boot.img" \
  "$OUTPUT_BOOT"

cat <<EOF

Done! Next steps:
  1. Install Magisk app:
       adb install -r "$MAGISK_APK"
  2. Flash "$OUTPUT_BOOT" to 'boot' via TWRP (fastboot flash is blocked by aboot):
       adb reboot recovery
       adb push "$OUTPUT_BOOT" /tmp/boot_magisk.img
       adb shell "dd if=/tmp/boot_magisk.img of=/dev/block/bootdevice/by-name/boot bs=4096 && sync"
       adb reboot
     (Or flash via EDL: edl.py w boot "$OUTPUT_BOOT")
  3. Open the Magisk app once booted to complete setup and grant Superuser prompts.
EOF
