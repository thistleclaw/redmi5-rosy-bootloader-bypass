# Xiaomi Redmi 5 (`rosy`) — руководство по бесплатному обходу блокировки загрузчика и установке Android 14 (LineageOS 21)

> **Отказ от ответственности:** Документация по образовательному исследованию и восстановлению **Xiaomi Redmi 5 (`rosy`, Snapdragon 450 / SDM450)**. Проверено на китайской версии устройства, для которой официальный Mi Unlock возвращал `code: 20045` (поддельная Global MIUI 9 `V9.2.6.0.0.NDAMIEK` / разблокировка через сервер заблокирована). Перед изменением разделов всегда создавайте резервные копии EFS/IMEI (`fsg`, `modemst1`, `modemst2`, `persist`), а также полные резервные копии GPT и прошивки.

## Почему официальная разблокировка не работает (и почему простое изменение `devinfo` приводит к кирпичу с переходом в EDL `05c6:900e`)

На Snapdragon 450 (`msm8953` / `rosy`) SBL1 проверяет `aboot` (Little Kernel), поэтому сам `aboot` изменить нельзя. Простая установка `is_unlocked = 1` в `devinfo` или прошивка неподписанного TWRP/ROM активирует **четыре отдельных механизма защиты** внутри `aboot`:

1. **Выключение через `splash_warn`**: при загрузке в состоянии `YELLOW`/`ORANGE` `aboot` показывает экран предупреждения из раздела `splash` (магическая сигнатура `SPLASH!!`) и может выключить устройство или остановить загрузку.
2. **Паника GPT `keymaster` / `send_rot_command`**: в разблокированном состоянии (`ORANGE`) или состоянии без подтверждённой целостности `aboot` пытается предварительно загрузить раздел `keymaster` и передать корень доверия (Root of Trust) с помощью `send_rot_command`. При отсутствии корректного встроенного RSA-сертификата `aboot` записывает в журнал `"RSA is null from the embedded certificate"` и вызывает `_panic()`, сразу переводя устройство в Qualcomm EDL (`05c6:900e`).
3. **Паника при проверке DER-подписи в `boot_verifier`**: `aboot` проверяет завершающий 4096-байтовый блок `BootSignature`, расположенный непосредственно после `page_size + align(kernel) + align(ramdisk) + align(second)`, как в `boot`, так и в `recovery`. Если первый байт по этому смещению не равен `0x30` (ASN.1 `SEQUENCE`), `aboot` вызывает панику и переходит в `05c6:900e` — даже если в `devinfo` указано, что загрузчик разблокирован!
4. **Несоответствие размера GPT-раздела `cmnlib64` (Nougat 7.1.2 и Oreo 8.1)**: в заводской разметке разделов Android 7.1.2 размеры `cmnlib64` / `cmnlib64bak` составляют `512` секторов (`262 144` байта), тогда как размер `cmnlib64_30.mbn` из Oreo 8.1 равен `269 088` байтам (`526` секторов). Его прямая прошивка перезаписывает следующий раздел либо отклоняется.

## Как работает обход

1. **Создайте резервные копии всего через EDL (`edl.py`)**: `aboot`, `boot`, `recovery`, `splash`, `devinfo`, `config`, `fsg`, `modemst1`, `modemst2`, `persist`, а также основной и резервной GPT.
2. **Обновите разделы прошивки (кроме `cmnlib64`)** файлами из Android 8.1 Oreo: `rpm`, `tz`, `aboot`, `lksecapp`, `sbl1`, `cmnlib`, `devcfg`, `keymaster`, `modem`, `dsp` и их копиями `*bak`.
3. **Измените `devinfo`** (`смещение 0x10`: `0 -> 1`) с помощью [patch_devinfo.py](scripts/patch_devinfo.py).
4. **Нейтрализуйте `splash`** (`SPLASH!!` -> `NOSPLASH`) с помощью [patch_splash.py](scripts/patch_splash.py).
5. **Переименуйте запись GPT `keymaster` -> `keymaste1`** (не изменяя `keymasterbak`) одновременно в основной и резервной GPT с помощью [patch_gpt_keymaster.py](scripts/patch_gpt_keymaster.py). После этого `aboot` больше не находит `keymaster`, пропускает `send_rot_command` и нормально продолжает загрузку.
6. **Разделите `keymaster.mbn` на сегменты PIL** (`.mdt` + `.b00`..`.b06`) с помощью [split_mbn_pil.py](scripts/split_mbn_pil.py) и скопируйте их в `/vendor/firmware_mnt/image/` (FAT-раздел `modem`), чтобы QSEE мог динамически загрузить `keymaster` на этапе запуска пользовательского пространства.
7. **Добавьте 4096-байтовую заглушку ASN.1 DER**, извлечённую из заводского `boot.img` / `recovery.img`, в конец **каждого** пользовательского образа `recovery` (TWRP) и `boot` с помощью [append_bootsig_stub.py](scripts/append_bootsig_stub.py).

## Запуск современных версий Android (11 и 14)

- **Android 11 (например, Evolution X):** загружается с использованием QSEE `keymaster.mbn`, который загружает `qseecomd`, если `android.hardware.keymaster@3.0-service` запускается с `user system`, `group drmrpc system` и типом SELinux `hal_keymaster_qti_exec`.
- **Android 14 (LineageOS 21 + MindTheGapps 14):**
  - `keystore2` и `odsign` создают/импортируют ключи сразу при загрузке. Поскольку `aboot` пропустил `send_rot_command`, QSEE `keymaster.mbn` возвращает `-30` (`KM_ERROR_VERIFICATION_FAILED` — `"Current ROT not set"`), из-за чего `system_server` (`SyntheticPasswordCrypto`) постоянно аварийно завершается.
  - **Исправление:** отключите `/vendor/lib64/hw/keystore.msm8953.so` и `/vendor/lib/hw/keystore.msm8953.so` (переименуйте в `*.bak`). Реализация AOSP `android.hardware.keymaster@3.0-impl.so` автоматически переключится на встроенную `libpuresoftkeymasterdevice.so` (`"Could not find any keystore module, using software-only implementation."`).
  - Также удалите `,fileencryption=ice` из `/vendor/etc/fstab.qcom` и отформатируйте `/data`. См. [patch_lineage21_vendor.sh](scripts/patch_lineage21_vendor.sh).

## Содержимое репозитория

| Путь | Описание |
| :--- | :--- |
| [docs/aboot-reverse-engineering.md](docs/aboot-reverse-engineering.md) | Подробный разбор путей проверки в `aboot`, ограничений разметки GPT, журналов Keymaster/Keystore2 и компромиссов |
| [scripts/patch_devinfo.py](scripts/patch_devinfo.py) | Устанавливает `is_unlocked = 1` в `devinfo.bin` (`ANDROID-BOOT!`) |
| [scripts/patch_splash.py](scripts/patch_splash.py) | Заменяет заголовок `SPLASH!!` на `NOSPLASH` в `splash.bin` |
| [scripts/patch_gpt_keymaster.py](scripts/patch_gpt_keymaster.py) | Переименовывает `keymaster` -> `keymaste1` в основной/резервной GPT и обновляет контрольные суммы CRC |
| [scripts/append_bootsig_stub.py](scripts/append_bootsig_stub.py) | Копирует 4-КБ блок подписи ASN.1 DER из заводского `boot`/`recovery` в любой неподписанный образ |
| [scripts/split_mbn_pil.py](scripts/split_mbn_pil.py) | Разделяет Qualcomm ELF `.mbn` на PIL-файлы `.mdt` + `.bXX` для `/vendor/firmware_mnt/image/` |
| [scripts/patch_lineage21_vendor.sh](scripts/patch_lineage21_vendor.sh) | Изменяет `/vendor` LineageOS 21 через TWRP для перехода на программный Keymaster и использования `/data` без FBE |

## Предупреждения и ограничения

- **Аппаратный Keystore / StrongBox**: отключён на Android 14 (используется `libpuresoftkeymasterdevice.so`). Gatekeeper (`@1.0`) и Fingerprint (`@2.1` / `fpctzapp`) продолжают нормально работать в TrustZone.
- **Каждая прошивка `boot` / `recovery`** (включая патчинг Magisk или обновления ROM) **должна** предварительно обрабатываться с помощью [append_bootsig_stub.py](scripts/append_bootsig_stub.py), иначе `aboot` вызовет панику и переведёт устройство в `05c6:900e` до восстановления через EDL.
- **OTA-обновления**: перезаписывают `/vendor` и `boot`, поэтому перед перезагрузкой в систему повторно запустите [append_bootsig_stub.py](scripts/append_bootsig_stub.py) и [patch_lineage21_vendor.sh](scripts/patch_lineage21_vendor.sh) из TWRP.

## Благодарности

- [bkerler/edl](https://github.com/bkerler/edl) — за инструменты Qualcomm Sahara/Firehose для работы с EDL.
- [TeamWin / TWRP](https://twrp.me/) и сопровождающим LineageOS — за поддержку `rosy`.
