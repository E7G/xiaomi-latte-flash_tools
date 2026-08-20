# Xiaomi Mi Pad 2 Arch Linux DNX flash package

基于 `xiaomi-latte-dev/linux_latte` 的 Mi Pad 2 自定义 6.14 内核，并迁移适合 Cherry Trail/Airmont、2 GiB 内存设备的 CachyOS 优化。

## 内核配置

- CachyOS 6.14 base patch 中的 BORE、O3、Silvermont、ADIOS/BFQ 等改动
- `-march=silvermont`、Clang ThinLTO、O3
- BORE + dynamic/full preemption，300 Hz tick
- MGLRU、THP `madvise`、ZRAM Zstd
- `schedutil`，兼顾触控响应、性能和功耗
- 保留 `xiaomipad2_defconfig` 的屏幕、触控、音频、Wi-Fi、蓝牙等设备驱动

## GitHub Actions 构建

打开 **Actions → Build CachyOS DNX package → Run workflow**。成功后下载 `xiaomi-latte-cachyos-dnx` artifact。

artifact 内含：

```text
images/gpt.bin
images/xiaomi-latte-boot.img
images/xiaomi-latte-rootfs.img
device_files/*
DNX_flash_all.bat
DNX_flash-boot.bat
SHA256SUMS
```

## 刷入

Windows 下解压 artifact 和其中的 `.tar.zst`，安装 Intel Android/DNX 驱动及 `fastboot`，以管理员身份运行 `DNX_flash_all.bat`。

Linux 下也可手动执行：

```bash
fastboot boot device_files/fastboot.efi
fastboot flash gpt images/gpt.bin
fastboot flash boot images/xiaomi-latte-boot.img
fastboot flash system images/xiaomi-latte-rootfs.img
fastboot reboot
```

默认用户：`user`，默认密码：`123456`。
