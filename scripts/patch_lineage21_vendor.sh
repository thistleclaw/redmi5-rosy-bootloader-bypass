#!/usr/bin/env bash
# Patch LineageOS 21 /vendor from TWRP recovery so Android 14 boots without aboot RoT or FBE ICE:
# 1. Disable hardware QTI keystore module (falls back to built-in libpuresoftkeymasterdevice.so).
# 2. Remove ,fileencryption=ice from /vendor/etc/fstab.qcom.
# Note: Back up /vendor or review changes before running. After flashing, format /data in TWRP.
set -euo pipefail

adb wait-for-recovery
adb shell '
set -e
mount -o rw /vendor || mount -o remount,rw /vendor

for lib in /vendor/lib64/hw/keystore.msm8953.so /vendor/lib/hw/keystore.msm8953.so; do
  if [ -f "$lib" ] && [ ! -f "${lib}.bak" ]; then
    mv "$lib" "${lib}.bak"
    echo "Disabled $lib -> ${lib}.bak"
  fi
done

if [ -f /vendor/etc/fstab.qcom ]; then
  sed -i "s/,fileencryption=ice//g" /vendor/etc/fstab.qcom
  grep "userdata" /vendor/etc/fstab.qcom
fi

rm -rf /data/misc/keystore/* 2>/dev/null || true
sync
'
echo "LineageOS 21 /vendor patch complete. Format /data in TWRP if switching from FBE, then flash boot_signedstub.img."
