# Reverse-Engineering Notes: Xiaomi Redmi 5 (`rosy`) `aboot` & Keymaster/Keystore2

These notes document exact binary behaviors observed on Oreo 8.1 `emmc_appsboot.mbn` (`601,640` bytes) and LineageOS 21 (`21.0-20240726-UNOFFICIAL-rosy`) running on SDM450 (`rosy`).

## 1. `aboot` (`emmc_appsboot.mbn`) String & Verification Anchors

Verified offsets inside `emmc_appsboot.mbn` (from Oreo firmware `9.10.10` / `V9+` series):

| Feature / String | File Offset | Observed Behavior |
| :--- | :--- | :--- |
| `boot_verifier` | `0x6a638` | Parses trailing 4096-byte signature block at `page_size + align(kernel) + align(ramdisk) + align(second)` |
| `RSA is null from the embedded certificate` | `0x6a74c` | Triggers `_panic()` -> EDL `05c6:900e` if verified-boot RSA certificate is null |
| `send_rot_command` | `0x6a888` | Loads `keymaster` partition and passes Root of Trust (RoT) to TZ/QSEE |
| `SPLASH!!` | `0x6fcec` | Warning display handler (`splash_warn`); non-matching magic skips warning halt |

### BootSignature Stub Requirement

Stock `boot.img` (`27,226,112` bytes of kernel + ramdisk + page padding) is immediately followed by a 4096-byte ASN.1 DER block starting with `30 82 05 46 02 01 01 30` (`1,354` non-zero bytes zero-padded to `4096`).

In `boot_verifier.c`, `aboot` reads the byte at `end` expecting `0x30` (ASN.1 `SEQUENCE`). When missing (all `0x00` or truncated image), `aboot` calls `_panic()` -> Sahara/EDL `05c6:900e` even when `devinfo` is unlocked (`is_unlocked = 1`). Appending the 4096-byte DER block from stock `boot.img` satisfies the `0x30` structural entry check on both `boot` and `recovery` images.

## 2. Partition Layout & GPT Findings (`rosy`, Nougat 7.1.2 Base -> Oreo 8.1 FW)

Inspected directly from raw GPT dump (`17,408` bytes = protective MBR `512` B + GPT header `512` B + 128 entries x `128` B):

| Partition Index | Name | Sectors (512 B) | Size (Bytes) | Notes |
| :--- | :--- | :--- | :--- | :--- |
| 17 | `splash` | `40,960` | `20,971,520` | `SPLASH!!` -> `NOSPLASH` |
| 18 | `aboot` | `2,048` | `1,048,576` | Signed by OEM; do not modify |
| 20 | `boot` | `131,072` | `67,108,864` | Requires 4 KB DER stub |
| 21 | `recovery` | `131,072` | `67,108,864` | Requires 4 KB DER stub |
| 22 | `devinfo` | `2,048` | `1,048,576` | Magic `ANDROID-BOOT!\x00\x00\x00`; offset `0x10` = `is_unlocked` |
| 40 | `cmnlib64` | `512` | `262,144` | **Smaller** than Oreo `cmnlib64_30.mbn` (`269,088` B) |
| 41 | `cmnlib64bak` | `512` | `262,144` | Keep 7.1.2 `cmnlib64` intact |
| 42 | `keymaster` | `512` | `262,144` | Renamed to `keymaste1` in GPT |
| 43 | `keymasterbak` | `512` | `262,144` | Left intact |

Renaming `keymaster` -> `keymaste1` changes the GPT partition array CRC32 (and GPT header self-CRC32 in both primary LBA 1 and backup LBA `last_usable + 1`). When modifying primary & backup GPT, **both** headers' `PartitionEntryLBA` and `HeaderCRC32` must be updated independently.

## 3. Why `devinfo` (`0x10 = 1`) + GPT Rename Works

- **`devinfo` offset `0x10` (`16`)**: `0` = locked, `1` = unlocked.
- With `keymaster` renamed to `keymaste1`, `aboot` fails to open `keymaster` and skips `send_rot_command` instead of panicking on `"RSA is null from the embedded certificate"`.
- In Android userspace, `qseecomd` can still load `keymaster` from `/vendor/firmware_mnt/image/keymaster.mdt` + `.b00`..`.b06` (split from `keymaster.mbn` via PIL format).

## 4. Android 11 vs Android 14 Keymaster Behavior

### Android 11 (Evolution X)
- `android.hardware.keymaster@3.0-service` ran as `nobody` with context `hal_keymaster_default`, failing to access `/vendor/firmware_mnt/image/` (`0550 system:system`, `firmware_file`).
- Changing `/vendor/etc/init/android.hardware.keymaster@3.0-service.rc` to `user system`, `group drmrpc system` and labeling the binary `u:object_r:hal_keymaster_qti_exec:s0` let `qseecomd` load QSEE `keymaster.mbn`, allowing Evolution X 11 to boot cleanly.

### Android 14 (LineageOS 21 + `keystore2`)
On Android 14, `keystore2` + `odsign` + `LockSettingsService.migrateUserToSpWithBoundKeysLocked()` call `generateKey` / `importKey` during boot:

```text
E/keymaster1_device: Generate key send cmd failed (ret: 0, resp->status: -30)
E/keystore2: Caused by: Error::Km(r#VERIFICATION_FAILED)
E/AndroidRuntime: FATAL EXCEPTION IN SYSTEM PROCESS: main
  java.lang.IllegalStateException: Failed to encrypt blob
  at com.android.server.locksettings.SyntheticPasswordCrypto.createBlob
```

Inside QSEE `keymaster.mbn`, `"Current ROT not set"` causes `-30` (`KM_ERROR_VERIFICATION_FAILED`) because `aboot` never issued `send_rot_command`.

However, LineageOS 21's `/vendor/lib64/hw/android.hardware.keymaster@3.0-impl.so` links `libpuresoftkeymasterdevice.so` and includes an explicit fallback:
```text
Could not find any keystore module, using software-only implementation.
```
Moving `/vendor/lib64/hw/keystore.msm8953.so` and `/vendor/lib/hw/keystore.msm8953.so` to `*.bak` causes `hw_get_module("keystore", ...)` to fall through to `libpuresoftkeymasterdevice.so`. `keystore2` immediately completes `initUserSuperKeys`, `SyntheticPasswordCrypto` falls back to non-rollback-resistant keys, and `system_server` boots to Setup Wizard in ~30 seconds.
