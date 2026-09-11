# 小米平板 2 Arch Linux DNX 刷机包

基于 [`E7G/linux_latte`](https://github.com/E7G/linux_latte) 的 Mi Pad 2
Linux 6.14 完整内核，并叠加适合 Cherry Trail/Airmont、2 GiB 内存设备的
CachyOS 优化。

## 已集成

- 屏幕、背光、触摸、底部三键及按键灯
- BQ27520 电池、BQ25890 充电、KTD2026 RGB LED
- BCM4356 Wi-Fi 与 BCM4356A2 蓝牙固件
- RT5659、双 TFA9890 的 ALSA UCM
- OV5693 前摄、T4KA3 后摄、DW9761 对焦、AtomISP firmware
- 传感器及自动旋转
- USB ACM 串口调试；Wi-Fi 故障时仍可通过 USB 登录
- Timeshift/Btrfs 一键备份恢复脚本与硬件 smoke test
- VFAT CP437/ASCII 启动分区支持

Secure Boot 和 suspend/resume 不作为本分支验收项。测试防息屏工具已安装，
但默认不启用：

```bash
sudo mp2-test-no-idle enable
sudo mp2-test-no-idle disable
```

硬件检查：

```bash
sudo /usr/local/libexec/mipad2-hardware-smoke
```

## GitHub Actions 构建

打开 **Actions → Build CachyOS DNX package → Run workflow**。成功后下载
`xiaomi-latte-cachyos-dnx` artifact。包内包含：

```text
images/gpt.bin
images/xiaomi-latte-boot.img
images/xiaomi-latte-rootfs.img
device_files/fastboot.efi
DNX_flash_all.bat
DNX_flash-boot.bat
SHA256SUMS
```

## 刷入

Windows 管理员终端运行 `DNX_flash_all.bat`。脚本会先核对文件、fastboot 和
设备代号 `latte`，任何刷写步骤失败都会立即停止。

Linux 可手动执行：

```bash
fastboot boot device_files/fastboot.efi
fastboot flash gpt images/gpt.bin
fastboot flash boot images/xiaomi-latte-boot.img
fastboot flash system images/xiaomi-latte-rootfs.img
fastboot reboot
```

默认用户：`user`；默认密码：`123456`。首次启动后应立即修改密码。
