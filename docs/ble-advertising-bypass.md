# Fixing BLE Advertising (`BLE advertiser not available`) on Xiaomi Redmi 5 (`rosy`)

## Root Cause

On Xiaomi Redmi 5 (`rosy`, LineageOS 21), `dumpsys bluetooth_manager` (`Hci Controller Dumpsys`) reports:

- `hci_version: "V_5_0"` / `lmp_version: "V_5_0"` (`manufacturer_name: 29`, Qualcomm)
- `le_maximum_advertising_data_length: 31`
- `le_number_supported_advertising_sets: 1`
- `mMaxScanFilters: 0`

Because the controller exposes only **1** legacy BLE advertising set (and no multi-advertising / offloaded scan filtering), Android's `BluetoothAdapter.isMultipleAdvertisementSupported()` returns `false`.

Apps such as **BitChat** (`com.bitchat.droid`) check `isMultipleAdvertisementSupported()` before calling `getBluetoothLeAdvertiser()`, immediately failing with:

```text
E BluetoothGattServerManager: BLE advertiser not available
E BluetoothConnectionManager: Failed to start server manager
```

even though the controller is fully capable of running a single BLE GATT server + advertising instance.

## Solution (Zygisk + Vector / LSPosed)

Hook `android.bluetooth.BluetoothAdapter.isMultipleAdvertisementSupported()` in the target app to return `true` so it proceeds to use the single hardware advertising slot.

### 1. Enable Zygisk and Install Vector (LSPosed)

1. Enable Zygisk in Magisk (`Magisk -> Settings -> Zygisk`, or via root shell):
   ```bash
   /debug_ramdisk/su -c '/debug_ramdisk/magisk --sqlite "REPLACE INTO settings (key,value) VALUES(\"zygisk\",1)"'
   ```
2. Install [JingMatrix/Vector](https://github.com/JingMatrix/Vector) (Android 14+ Zygisk LSPosed fork):
   ```bash
   adb push Vector-Release.zip /data/local/tmp/
   adb shell "/debug_ramdisk/su -c '/debug_ramdisk/magisk --install-module /data/local/tmp/Vector-Release.zip'"
   ```

### 2. Minimal Xposed Hook (`BleAdvBypass`)

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

### 3. Enable Scope and Reboot

After installing `BleAdvBypass.apk` and rebooting for Zygisk/Vector to load:

```bash
/data/adb/modules/zygisk_vector/cli modules enable com.thistle.bleadvbypass
/data/adb/modules/zygisk_vector/cli scope set com.thistle.bleadvbypass com.bitchat.droid/0
```

## Verification

After launching BitChat, `logcat` and `dumpsys bluetooth_manager` confirm the single BLE advertising slot works for both GATT server and client mesh connections:

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
