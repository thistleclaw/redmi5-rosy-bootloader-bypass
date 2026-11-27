# Xiaomi Redmi 5 (`rosy`) — Zero-Cost Bootloader Unlock Bypass & Android 14 (LineageOS 21) Guide

> **Disclaimer:** Educational research and hardware recovery documentation for **Xiaomi Redmi 5 (`rosy`, Snapdragon 450 / SDM450)**. Tested on a China-variant device whose official Mi Unlock returned `code: 20045` (fake Global MIUI 9 `V9.2.6.0.0.NDAMIEK` / blocked server unlock). Always back up EFS/IMEI (`fsg`, `modemst1`, `modemst2`, `persist`) and full GPT/firmware before modifying partitions.

## Why Official Unlock Fails (and Why Simple `devinfo` Patching Bricks to EDL `05c6:900e`)

On Snapdragon 450 (`msm8953` / `rosy`), SBL1 verifies `aboot` (Little Kernel), so `aboot` itself cannot be modified. Simply setting `is_unlocked = 1` in `devinfo` or flashing an unsigned TWRP/ROM triggers **four separate traps** inside `aboot`:

1. **`splash_warn` shutdown**: When booting in `YELLOW`/`ORANGE` state, `aboot` displays the warning screen from the `splash` partition (`SPLASH!!` magic) and may shut down or halt.
2. **GPT `keymaster` / `send_rot_command` panic**: In unlocked (`ORANGE`) or unverified state, `aboot` attempts to preload the `keymaster` partition and send Root of Trust (`send_rot_command`). Without a valid embedded RSA certificate, `aboot` logs `"RSA is null from the embedded certificate"` and calls `_panic()`, dropping directly into Qualcomm EDL (`05c6:900e`).
3. **`boot_verifier` DER signature check panic**: `aboot` checks the trailing 4096-byte `BootSignature` block immediately after `page_size + align(kernel) + align(ramdisk) + align(second)` in **both** `boot` and `recovery`. If the first byte at that offset is not `0x30` (ASN.1 `SEQUENCE`), `aboot` panics into `05c6:900e` — even when `devinfo` says unlocked!
4. **GPT `cmnlib64` size mismatch (Nougat 7.1.2 vs Oreo 8.1)**: On Android 7.1.2 factory partition layouts, `cmnlib64` / `cmnlib64bak` are `512` sectors (`262,144` bytes), whereas Oreo 8.1 `cmnlib64_30.mbn` is `269,088` bytes (`526` sectors). Flashing it directly overwrites the next partition or gets rejected.

## How the Bypass Works

1. **Back up everything via EDL (`edl.py`)** (`aboot`, `boot`, `recovery`, `splash`, `devinfo`, `config`, `fsg`, `modemst1`, `modemst2`, `persist`, and primary/backup GPT).
2. **Upgrade firmware partitions (excluding `cmnlib64`)** from Android 8.1 Oreo (`rpm`, `tz`, `aboot`, `lksecapp`, `sbl1`, `cmnlib`, `devcfg`, `keymaster`, `modem`, `dsp` + `*bak` copies).
3. **Patch `devinfo`** (`offset 0x10`: `0 -> 1`) using [patch_devinfo.py](scripts/patch_devinfo.py).
4. **Neutralize `splash`** (`SPLASH!!` -> `NOSPLASH`) using [patch_splash.py](scripts/patch_splash.py).
5. **Rename GPT entry `keymaster` -> `keymaste1`** (leaving `keymasterbak` untouched) in both primary and backup GPT using [patch_gpt_keymaster.py](scripts/patch_gpt_keymaster.py). `aboot` no longer finds `keymaster`, skips `send_rot_command`, and boots cleanly.
6. **Split `keymaster.mbn` into PIL segments** (`.mdt` + `.b00`..`.b06`) with [split_mbn_pil.py](scripts/split_mbn_pil.py) and copy them into `/vendor/firmware_mnt/image/` (the `modem` FAT partition) so QSEE can load `keymaster` dynamically at userspace boot.
7. **Append a 4096-byte ASN.1 DER stub** extracted from stock `boot.img` / `recovery.img` to **every** custom `recovery` (TWRP) and `boot` image using [append_bootsig_stub.py](scripts/append_bootsig_stub.py).

## Running Modern Android (11 vs 14)

- **Android 11 (e.g. Evolution X):** Boots using QSEE `keymaster.mbn` loaded by `qseecomd` once `android.hardware.keymaster@3.0-service` runs with `user system`, `group drmrpc system`, and SELinux type `hal_keymaster_qti_exec`.
- **Android 14 (LineageOS 21 + MindTheGapps 14):**
  - `keystore2` and `odsign` generate/import keys immediately on boot. Because `aboot` skipped `send_rot_command`, QSEE `keymaster.mbn` returns `-30` (`KM_ERROR_VERIFICATION_FAILED` — `"Current ROT not set"`), causing `system_server` (`SyntheticPasswordCrypto`) to crash repeatedly.
  - **Fix:** Disable `/vendor/lib64/hw/keystore.msm8953.so` and `/vendor/lib/hw/keystore.msm8953.so` (`*.bak`). AOSP's `android.hardware.keymaster@3.0-impl.so` automatically falls back to built-in `libpuresoftkeymasterdevice.so` (`"Could not find any keystore module, using software-only implementation."`).
  - Also remove `,fileencryption=ice` from `/vendor/etc/fstab.qcom` and format `/data`. See [patch_lineage21_vendor.sh](scripts/patch_lineage21_vendor.sh).

## Rooting with Magisk

Flashing Magisk directly in TWRP (or flashing a Magisk-patched `boot.img` from the app) **will brick to EDL (`05c6:900e`)** because `magiskboot` strips the trailing 4 KB `0x30` DER stub when repacking `boot.img`. Additionally, Oreo `aboot` still reports `Device unlocked: false` in `fastboot oem device-info`, so `fastboot flash boot` fails with `Partition flashing is not allowed` — flash via **TWRP** or **EDL** instead.

1. Patch `boot.img` with Magisk and re-append the stock DER stub using [patch_boot_magisk.sh](scripts/patch_boot_magisk.sh):
   ```bash
   ./scripts/patch_boot_magisk.sh Magisk.apk lineage21_boot_signedstub.img boot.bin lineage21_boot_magisk_signedstub.img
   ```
2. Install the Magisk app and flash the signed-stub image in TWRP:
   ```bash
   adb install -r Magisk.apk
   adb reboot recovery
   adb push lineage21_boot_magisk_signedstub.img /tmp/boot_magisk.img
   adb shell "dd if=/tmp/boot_magisk.img of=/dev/block/bootdevice/by-name/boot bs=4096 && sync"
   adb reboot
   ```
3. On Android 14 / Magisk v31+, `su` lives at `/debug_ramdisk/su`. Open the Magisk app after booting to finish setup and manage Superuser permissions.

## Repository Contents

| Path | Description |
| :--- | :--- |
| [docs/aboot-reverse-engineering.md](docs/aboot-reverse-engineering.md) | Detailed breakdown of `aboot` verification paths, GPT layout limits, Keymaster/Keystore2 logs, and tradeoffs |
| [scripts/patch_devinfo.py](scripts/patch_devinfo.py) | Sets `is_unlocked = 1` in `devinfo.bin` (`ANDROID-BOOT!`) |
| [scripts/patch_splash.py](scripts/patch_splash.py) | Replaces `SPLASH!!` header with `NOSPLASH` in `splash.bin` |
| [scripts/patch_gpt_keymaster.py](scripts/patch_gpt_keymaster.py) | Renames `keymaster` -> `keymaste1` in primary/backup GPT and updates CRCs |
| [scripts/append_bootsig_stub.py](scripts/append_bootsig_stub.py) | Copies the 4 KB ASN.1 DER signature block from stock `boot`/`recovery` onto any unsigned image |
| [scripts/split_mbn_pil.py](scripts/split_mbn_pil.py) | Splits Qualcomm ELF `.mbn` into `.mdt` + `.bXX` PIL files for `/vendor/firmware_mnt/image/` |
| [scripts/patch_lineage21_vendor.sh](scripts/patch_lineage21_vendor.sh) | Patches LineageOS 21 `/vendor` in TWRP for software Keymaster fallback and non-FBE `/data` |
| [scripts/patch_boot_magisk.sh](scripts/patch_boot_magisk.sh) | Patches `boot.img` with Magisk over ADB and appends the 4 KB DER stub |

## Caveats & Limitations

- **Hardware-backed Keystore / StrongBox**: Disabled on Android 14 (uses `libpuresoftkeymasterdevice.so`). Gatekeeper (`@1.0`) and Fingerprint (`@2.1` / `fpctzapp`) still run normally in TrustZone.
- **Every `boot` / `recovery` flash** (including Magisk patching or ROM updates) **must** pass through [append_bootsig_stub.py](scripts/append_bootsig_stub.py), or `aboot` will panic into `05c6:900e` until restored via EDL.
- **OTA updates**: Overwrite `/vendor` and `boot`, so re-run [append_bootsig_stub.py](scripts/append_bootsig_stub.py) and [patch_lineage21_vendor.sh](scripts/patch_lineage21_vendor.sh) from TWRP before rebooting to system.

## Credits

- [bkerler/edl](https://github.com/bkerler/edl) for Qualcomm Sahara/Firehose EDL tooling.
- [TeamWin / TWRP](https://twrp.me/) & LineageOS maintainers for `rosy`.
