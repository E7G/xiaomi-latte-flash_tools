# 小米平板 2 CachyOS 一键刷机包

面向 Xiaomi Mi Pad 2（`latte`）的 CachyOS/Arch Linux 镜像。默认桌面为精简
KDE Plasma Wayland，内核来自 [`E7G/linux_latte`](https://github.com/E7G/linux_latte)。

## 一键刷机

1. 在 GitHub Actions 下载 `xiaomi-latte-cachyos-one-click`。
2. 完整解压 ZIP，不能在压缩包预览界面中运行。
3. 平板进入 DNX/Fastboot 模式并用 USB 连接电脑。
4. 双击 `ONE_KEY_FLASH.bat`。

包内已经包含 Google 官方 Windows Platform-Tools，不需要安装或配置
`fastboot.exe`。脚本会自动：

1. 校验所有刷机镜像的 SHA256；
2. 等待 fastboot 设备；
3. 启动原版 `fastboot.efi`；
4. 验证设备代号必须为 `latte`；
5. 写入原版 OEM 变量和 GPT；
6. 写入 boot 与 CachyOS KDE system；
7. 自动重启。

任一步失败都会立即停止，不会继续写入后续分区。

只修复启动分区可运行：

```text
DNX_flash-boot.bat
```

## 生成物

### Windows 一键刷机

```text
xiaomi-latte-cachyos-one-click
├── ONE_KEY_FLASH.bat
├── flash-one-click.ps1
├── platform-tools/fastboot.exe
├── images/gpt.bin
├── images/xiaomi-latte-boot.img
├── images/xiaomi-latte-rootfs.img
├── device_files/fastboot.efi
└── SHA256SUMS
```

### 一键 U 盘安装盘

`xiaomi-latte-cachyos-usb-imgxz` 只包含 U 盘安装镜像 `.img.xz` 和对应
SHA256，不再与 Windows 一键刷机包混装。

1. 用 Rufus、balenaEtcher 或 `xzcat | dd` 把 `.img.xz` 写入整个 U 盘；
2. 小米平板 2 从该 U 盘启动；
3. KDE 自动登录后会自动打开安装窗口；
4. 输入 `FLASH`，安装器会清空内部 `/dev/mmcblk0`，复制当前完整系统、
   写入同一套签名 EFI、更新 UUID/GRUB 并自动关机；
5. 拔掉 U 盘，再开机即可进入内部 eMMC 上的系统。

安装器会验证启动源不是内部 eMMC、校验目标容量，并使用 Btrfs 只读快照复制
系统和用户数据；不会把运行中的可变文件系统直接 `dd` 到内部存储。

## 启动链

启动分区同时提供：

- 从当前可启动系统逐字节提取的 Proxmox shim/mm 组合；shim 的
  `BOOTX64.EFI` 仍由 Microsoft UEFI CA 2011 链签名；
- 原项目 MOK 签名的独立 `grubx64.efi`；
- 内嵌 ESP UUID/标签搜索逻辑的 GRUB bootstrap；
- 外置 `EFI/BOOT/grub.cfg` 和 `EFI/arch/grub.cfg` 双重回退；
- 原项目 MOK 签名的内核。

Mi Pad 2 不同 BIOS 的 Secure Boot 数据库并不一致。原版 DNX 包本身使用的
`BOOTX64.EFI` 是未签名 GRUB，并不具备 Secure Boot 能力。若固件不信任
Microsoft UEFI CA 2011，只能使用 BIOS 中已经登记的证书或关闭 Secure Boot；
重新使用相同 MOK 证书不能让固件自动信任 shim。

## 首次启动

首次启动会自动执行 `btrfs filesystem resize max /`，让 system 分区使用
GPT 分配的全部剩余空间。

默认账户：

```text
用户名：user
密码：123456
```

测试防息屏默认不启用，需要时执行：

```bash
sudo mp2-test-no-idle enable
sudo mp2-test-no-idle disable
```
