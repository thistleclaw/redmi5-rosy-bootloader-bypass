# Исправление BLE Advertising (`BLE advertiser not available`) на Xiaomi Redmi 5 (`rosy`)

## Причина проблемы

На Xiaomi Redmi 5 (`rosy`, LineageOS 21) в выводе `dumpsys bluetooth_manager` (`Hci Controller Dumpsys`) контроллер сообщает:

- `hci_version: "V_5_0"` / `lmp_version: "V_5_0"` (`manufacturer_name: 29`, Qualcomm)
- `le_maximum_advertising_data_length: 31`
- `le_number_supported_advertising_sets: 1`
- `mMaxScanFilters: 0`

Поскольку контроллер поддерживает ровно **1** базовый BLE advertising-сет (и не поддерживает мульти-адвертайзинг / аппаратную фильтрацию сканирования), метод Android `BluetoothAdapter.isMultipleAdvertisementSupported()` возвращает `false`.

Приложения вроде **BitChat** (`com.bitchat.droid`) проверяют `isMultipleAdvertisementSupported()` до вызова `getBluetoothLeAdvertiser()` и сразу падают с ошибкой:

```text
E BluetoothGattServerManager: BLE advertiser not available
E BluetoothConnectionManager: Failed to start server manager
```

хотя сам контроллер спокойно способен держать один BLE GATT-сервер и 1 рекламный слот.

## Решение (Zygisk + Vector / LSPosed)

Достаточно перехватить `android.bluetooth.BluetoothAdapter.isMultipleAdvertisementSupported()` в нужном приложении и вернуть `true`, чтобы оно использовало единственный доступный аппаратный слот.

### 1. Включение Zygisk и установка Vector (LSPosed)

1. Включите Zygisk в настройках Magisk (или через root-shell):
   ```bash
   /debug_ramdisk/su -c '/debug_ramdisk/magisk --sqlite "REPLACE INTO settings (key,value) VALUES(\"zygisk\",1)"'
   ```
2. Установите [JingMatrix/Vector](https://github.com/JingMatrix/Vector) (форк LSPosed под Android 14+ и Zygisk):
   ```bash
   adb push Vector-Release.zip /data/local/tmp/
   adb shell "/debug_ramdisk/su -c '/debug_ramdisk/magisk --install-module /data/local/tmp/Vector-Release.zip'"
   ```

### 2. Минимальный Xposed-хук (`BleAdvBypass`)

```java
package com.thistle.bleadvbypass;

import de.robv.android.xposed.IXposedHookLoadPackage;
import de.robv.android.xposed.XC_MethodReplacement;
import de.robv.android.xposed.XposedHelpers;
import de.robv.android.xposed.callbacks.XC_LoadPackage;

public class Hook implements IXposedHookLoadPackage {
    @Override
    public void handleLoadPackage(XC_LoadPackage.LoadPackageParam lpparam) throws Throwable {
        if (!"com.bitchat.droid".equals(lpparam.packageName)) return;
        XposedHelpers.findAndHookMethod(
            "android.bluetooth.BluetoothAdapter",
            lpparam.classLoader,
            "isMultipleAdvertisementSupported",
            XC_MethodReplacement.returnConstant(Boolean.TRUE)
        );
    }
}
```

### 3. Активация модуля и области действия

После установки `BleAdvBypass.apk` и перезагрузки для загрузки Zygisk/Vector:

```bash
/data/adb/modules/zygisk_vector/cli modules enable com.thistle.bleadvbypass
/data/adb/modules/zygisk_vector/cli scope set com.thistle.bleadvbypass com.bitchat.droid/0
```

## Проверка результата

После запуска BitChat в `logcat` и `dumpsys bluetooth_manager` видно, что единственный BLE-слот полноценно поднимает GATT-сервер, advertising и двустороннее mesh-соединение:

```text
I BluetoothGattServerManager: GATT server setup complete
I BluetoothGattServerManager: Advertising started (power mode: PERFORMANCE)
I BluetoothGattServerManager: Connected to <peer_mac> (server)
I BluetoothGattClientManager: Connected to <peer_mac> (client)
D BluetoothMeshService: Observed direct BLE route <peer_mac> to <peer_id>
```

```text
GATT Advertiser Map
  Total number of ongoing advertising                   : 1
  Ongoing advertising:
    com.bitchat.droid
     Advertising ID                                     : 1
```
