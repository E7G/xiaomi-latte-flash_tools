# 小米平板 2 CachyOS 一键刷机包

面向 Xiaomi Mi Pad 2（`latte`）的 CachyOS/Arch Linux 镜像。当前默认桌面为针对平板优化的
GNOME Wayland（构建脚本仍保留 Plasma 可选配置），内核来自 [`E7G/linux_latte`](https://github.com/E7G/linux_latte)。


## Secure Boot / MOK security note

The current legacy Mi Pad 2 MOK is retained only for compatibility with tablets that already enrolled its certificate. The private key must never be copied into a finished image; the build now keeps it only in a temporary build-time path and deletes it immediately after signing. Because the legacy private key has existed in repository history, it should be considered compromised for trust purposes. A future device-side migration should generate a new MOK, enroll the new certificate on the tablet first, then switch signing to the new key and remove the legacy private key from active builds.

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
3. systemd 安装服务会在登录界面前自动运行；
4. 无需点击或输入，安装器会自动清空内部 `/dev/mmcblk0`，复制当前完整系统、
   写入同一套签名 EFI、更新 UUID/GRUB 并自动关机；
5. 拔掉 U 盘，再开机即可进入内部 eMMC 上的系统。

安装器会验证启动源不是内部 eMMC、校验目标容量，并使用 Btrfs 只读快照复制
系统和用户数据；不会把运行中的可变文件系统直接 `dd` 到内部存储。
从内部 eMMC 启动时，安装服务会自动跳过，不会覆盖自身。

## 启动链

启动分区提供：

- 使用原项目 MOK 直接签名的 U 盘入口 `BOOTX64.EFI`；
- 内容相同、使用原项目 MOK 签名的 `grubx64.efi`；
- 内嵌 ESP UUID/标签搜索逻辑的 GRUB bootstrap；
- 外置 `EFI/BOOT/grub.cfg` 和 `EFI/arch/grub.cfg` 双重回退；
- 原项目 MOK 签名的内核。

Mi Pad 2 的固件会在进入 GRUB 前直接校验 U 盘回退入口，并拒绝第三方
Microsoft UEFI CA 签名的 shim。因此 U 盘入口不再使用 shim，而是直接复用
原系统已经登记的项目 MOK 证书。

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

## Mi Pad 2 默认体验优化

`arch_linux` 镜像构建时会直接应用以下平板优化，无需首次启动后再手工配置：

- GNOME 50 原生屏幕键盘使用紧凑 4 行 extended 布局，保留 Tab、Ctrl、Alt 和方向键，并缩小按键/候选栏间距；
- GNOME 更新到新的 50.x 版本后通过 Pacman hook 自动重新应用 OSK 补丁；跨 GNOME 大版本会安全跳过；
- zram 使用 `lz4`、容量为内存的 75%，并使用 `vm.swappiness=60`、`vm.page-cluster=0`；
- NetworkManager 默认关闭 Wi-Fi powersave，减少流媒体和交互时的短暂停顿；
- 默认安装 `rtkit`，供 PipeWire/WirePlumber 获取实时调度；
- 默认浏览器使用 Brave，启用经 Mi Pad 2 实机验证的 Wayland/VA-API 参数，并关闭 VP9/AV1 软件解码路径；
- Brave 默认关闭 Rewards、Wallet、VPN、Talk、AI Chat、News、Tor、IPFS、后台模式和遥测；
- GNOME 保留 `IBus + libpinyin`，默认输入源为 US + Intelligent Pinyin；
- Mi Pad 2 不具备的 Thunderbolt、WWAN、打印、Smartcard 和 Sharing 后台服务会被屏蔽，以减少常驻内存。

这些优化不修改自定义 GRUB 菜单或 GRUB 字体，也不包含 Snapshot 相机源码；相机应用的 Mi Pad 2 专用修复继续由 `E7G/snapshot` 维护。


### Mi Pad 2 navigation keys

Current `linux_latte:cachyos-mipad2` kernels handle the capacitive Menu/Home/Back keys in-kernel. New `arch_linux` images therefore do not install or enable the legacy Python `mipad2-navkeys` daemon. The old files remain in `device_files/` only for recovery with older kernels.


### Mi Pad 2 rear camera factory calibration

On kernels that expose `mipad2-t4ka3-otp`, the image runs a one-shot calibration
cache service at boot. It validates Xiaomi's 578-byte rear-camera factory OTP and
writes the safe parsed values to:

`/var/lib/mipad2-camera/calibration.env`

The helper `mipad2-camera-focus` uses the factory AF endpoints and never drives
the lens outside the calibrated range. Useful commands:

`mipad2-camera-focus info`
`mipad2-camera-focus infinity`
`mipad2-camera-focus macro`
`mipad2-camera-focus auto`

`auto` is on-demand only; there is no resident autofocus daemon.
