# Xiaomi Redmi 5 (`rosy`) — исследование загрузчика и запуск LineageOS 21 (Android 14)

> Эксперимент проводился на китайской версии **Xiaomi Redmi 5 (`rosy`, Snapdragon 450 / SDM450)** с MIUI 9 `V9.2.6.0.0.NDAMIEK`, для которой Mi Unlock возвращал ошибку `20045`. Перед изменением разделов сохраните пользовательские данные, резервные копии GPT, заводской прошивки и разделов `fsg`, `modemst1`, `modemst2` и `persist`.

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

## Запуск Android 11 и Android 14

- **Android 11 (e.g. Evolution X):** Boots using QSEE `keymaster.mbn` loaded by `qseecomd` once `android.hardware.keymaster@3.0-service` runs with `user system`, `group drmrpc system`, and SELinux type `hal_keymaster_qti_exec`.
- **Android 14 (LineageOS 21 + MindTheGapps 14):**
  - `keystore2` and `odsign` generate/import keys immediately on boot. Because `aboot` skipped `send_rot_command`, QSEE `keymaster.mbn` returns `-30` (`KM_ERROR_VERIFICATION_FAILED` — `"Current ROT not set"`), causing `system_server` (`SyntheticPasswordCrypto`) to crash repeatedly.
  - **Fix:** Disable `/vendor/lib64/hw/keystore.msm8953.so` and `/vendor/lib/hw/keystore.msm8953.so` (`*.bak`). AOSP's `android.hardware.keymaster@3.0-impl.so` automatically falls back to built-in `libpuresoftkeymasterdevice.so` (`"Could not find any keystore module, using software-only implementation."`).
  - Also remove `,fileencryption=ice` from `/vendor/etc/fstab.qcom` and format `/data`. See [patch_lineage21_vendor.sh](scripts/patch_lineage21_vendor.sh).

## Содержимое репозитория

| Path | Description |
| :--- | :--- |
| [docs/aboot-reverse-engineering.md](docs/aboot-reverse-engineering.md) | Detailed breakdown of `aboot` verification paths, GPT layout limits, Keymaster/Keystore2 logs, and tradeoffs |
| [scripts/patch_devinfo.py](scripts/patch_devinfo.py) | Sets `is_unlocked = 1` in `devinfo.bin` (`ANDROID-BOOT!`) |
| [scripts/patch_splash.py](scripts/patch_splash.py) | Replaces `SPLASH!!` header with `NOSPLASH` in `splash.bin` |
| [scripts/patch_gpt_keymaster.py](scripts/patch_gpt_keymaster.py) | Renames `keymaster` -> `keymaste1` in primary/backup GPT and updates CRCs |
| [scripts/append_bootsig_stub.py](scripts/append_bootsig_stub.py) | Copies the 4 KB ASN.1 DER signature block from stock `boot`/`recovery` onto any unsigned image |
| [scripts/split_mbn_pil.py](scripts/split_mbn_pil.py) | Splits Qualcomm ELF `.mbn` into `.mdt` + `.bXX` PIL files for `/vendor/firmware_mnt/image/` |
| [scripts/patch_lineage21_vendor.sh](scripts/patch_lineage21_vendor.sh) | Patches LineageOS 21 `/vendor` in TWRP for software Keymaster fallback and non-FBE `/data` |

## Ограничения и последствия

- **Защита ключей на Android 14.** В проверенной конфигурации используется программный Keymaster (`libpuresoftkeymasterdevice.so`) и отключено файловое шифрование пользовательских данных (FBE). По наблюдениям автора, Gatekeeper (`@1.0`) и сканер отпечатков (`@2.1`, `fpctzapp`) продолжили работать через TrustZone.
- **Every `boot` / `recovery` flash** (including Magisk patching or ROM updates) **must** pass through [append_bootsig_stub.py](scripts/append_bootsig_stub.py), or `aboot` will panic into `05c6:900e` until restored via EDL.
- **OTA updates**: Overwrite `/vendor` and `boot`, so re-run [append_bootsig_stub.py](scripts/append_bootsig_stub.py) and [patch_lineage21_vendor.sh](scripts/patch_lineage21_vendor.sh) from TWRP before rebooting to system.

## Благодарности

- [bkerler/edl](https://github.com/bkerler/edl) за инструменты Qualcomm Sahara/Firehose для работы в EDL.
- [TeamWin / TWRP](https://twrp.me/) и сопровождающим сборок LineageOS для `rosy`.
