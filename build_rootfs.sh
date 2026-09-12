#!/bin/bash
set -e
# set -x
shopt -s expand_aliases

UserName="${UserName:-user}"
UserPasswd="${UserPasswd:-123456}"
HostName="${HostName:-mipad2}"
desktop_type="${desktop_type:-plasma}"
ROOTFS_SIZE="${ROOTFS_SIZE:-8G}"
KERNEL_PACKAGE="${KERNEL_PACKAGE:-}"
KERNEL_PKGBASE="linux-latte-cachyos"

if [[ ! -d /sys/module/nbd ]]; then
	modprobe nbd max_part=8
fi
boot_dev=/dev/nbd0
rootfs_dev=/dev/nbd1
mount_dir="$(realpath -m ./rootfs)"
device_file="$(realpath -m ./device_files)"
mkdir -p ./images /run/lock

# 判断是否是root用户，如果不是则退出
if [[ $EUID -ne 0 ]]; then
   echo "This script must be run as root" 
   exit 1
fi

# 判断文件夹是否存在，不存在则创建
if [ ! -d $mount_dir ]; then
	mkdir -p $mount_dir
fi

is_mount() {
	findmnt --mountpoint "$mount_dir" &>/dev/null
}

convert() {
	echo 转换镜像格式，从qcow2到img
	# qcow2 to img
	pushd ./images
	echo convert boot.qcow2 to xiaomi-latte-boot.img
	qemu-img convert -p -f qcow2 -O raw -S 4k boot.qcow2 xiaomi-latte-boot.img
	echo convert rootfs.qcow2 to xiaomi-latte-rootfs.img
	qemu-img convert -p -f qcow2 -O raw -S 4k rootfs.qcow2 xiaomi-latte-rootfs.img
	popd
}

gpt(){
	python gpt_ini2bin.py
}

rm_img() {
	umount_img
	sleep 1
	pushd ./images
	rm -f ./boot.qcow2 ./rootfs.qcow2 ./xiaomi-latte-boot.img ./xiaomi-latte-rootfs.img
	popd
}

create_img() {
	pushd ./images
	# Must match gpt.ini and the USB image ESP exactly.
	qemu-img create -f qcow2 boot.qcow2 256M
	qemu-img create -f qcow2 rootfs.qcow2 "$ROOTFS_SIZE"
	popd
}

# 初始状态没有连接镜像
flag_connect=0
connect_img() {
	if [[ $flag_connect != 0 ]]; then
		umount_img
		disconnect_img
	fi
	pushd ./images
	echo connect boot.qcow2 to $boot_dev
    qemu-nbd -n -c $boot_dev -f qcow2 boot.qcow2
	echo connect rootfs.qcow2 to $rootfs_dev
	qemu-nbd -n -c $rootfs_dev -f qcow2 rootfs.qcow2
	popd
	flag_connect=1
}

disconnect_img() {
	if [[ $flag_connect == 0 ]]; then
		return
	fi
	qemu-nbd -d $boot_dev || true
	qemu-nbd -d $rootfs_dev || true
	flag_connect=0
}

format() {
	connect_img
	sleep 1

    mkfs.vfat -F 32 -n boot $boot_dev
	mkfs.btrfs -L rootfs $rootfs_dev

	mount $rootfs_dev $mount_dir
	pushd $mount_dir
	btrfs subvolume create @
	btrfs subvolume create @home
	btrfs subvolume set-default @
	popd
	umount $mount_dir
}

mount_img() {
	if is_mount; then
		return
	fi
	connect_img
	sleep 1

	echo mount rootfs
    mount -t btrfs -o compress=zstd,subvol=@ $rootfs_dev $mount_dir
	mkdir -p $mount_dir/{boot,home}
	echo mount boot
	mount $boot_dev $mount_dir/boot
	echo mount home
	mount -t btrfs -o compress=zstd,subvol=@home $rootfs_dev $mount_dir/home
}

umount_img() {
	if ! is_mount; then
		disconnect_img
		return
	fi
    umount -R $mount_dir || true
	disconnect_img
}

firmware=(
	linux-firmware-broadcom
	linux-firmware-intel
	wireless-regdb
	libva-intel-driver
	intel-ucode
	vulkan-intel
)

packages=(
base-devel
# Shell
bash-completion zsh-completions sudo reflector pkgfile less btop
zsh-autosuggestions zsh-syntax-highlighting
vim
# 日用浏览器
firefox
# 字体
noto-fonts-{cjk,emoji} ttf-cascadia-code
# 音频
alsa-utils pipewire-{alsa,audio,pulse}
# 文件系统
btrfs-progs exfatprogs
# 网络
networkmanager
# 蓝牙
bluez-utils
# 视频
mpv v4l-utils i2c-tools
# 电源配置
power-profiles-daemon
# 线程优化
irqbalance
# zram
zram-generator
)

plasma=(
# 精简 Plasma Wayland 桌面和原生登录管理器
plasma-{desktop,pa,nm,systemmonitor} plasma-login-manager breeze-gtk kde-gtk-config
powerdevil kscreen kinfocenter systemsettings
# 日用组件
konsole dolphin kate ark okular gwenview spectacle kcalc kamoso kdeconnect sshfs
# 中文输入法、屏幕键盘、自动旋转
fcitx5-im kcm-fcitx5 fcitx5-chinese-addons plasma-keyboard iio-sensor-proxy
# 蓝牙
bluedevil
plasma-wayland-protocols
)

alias run="arch-chroot $mount_dir"
install_packages() {
	# 安装基础包
	pacstrap -C "${device_file}"/pacman.conf -c $mount_dir base iptables-nft ${firmware[@]} grub efibootmgr sbsigntools

	if [[ -z "$KERNEL_PACKAGE" ]]; then
		KERNEL_PACKAGE="$(find "$device_file" -maxdepth 1 -name 'linux-latte-cachyos-*.pkg.tar.zst' -print -quit)"
	fi
	[[ -f "$KERNEL_PACKAGE" ]] || { echo "Kernel package not found: $KERNEL_PACKAGE" >&2; exit 1; }
	echo "Install $KERNEL_PACKAGE"
	pacstrap -C "${device_file}"/pacman.conf -U $mount_dir "$KERNEL_PACKAGE"
	kernel_release="$(find "$mount_dir/usr/lib/modules" -mindepth 1 -maxdepth 1 -type d -printf '%f\n' | head -n1)"
	[[ -n "$kernel_release" ]] || { echo 'Installed kernel modules not found' >&2; exit 1; }
	install -Dm0644 "$mount_dir/usr/lib/modules/$kernel_release/vmlinuz" \
		"$mount_dir/boot/vmlinuz-$KERNEL_PKGBASE"

	declare -n desktop=$desktop_type
	pacstrap -C "${device_file}"/pacman.conf -c $mount_dir ${packages[@]} ${desktop[@]} mkinitcpio
	cat > "$mount_dir/etc/mkinitcpio.d/$KERNEL_PKGBASE.preset" <<EOF
ALL_config="/etc/mkinitcpio.conf"
ALL_kver="/usr/lib/modules/$kernel_release/vmlinuz"
PRESETS=('default' 'fallback')
default_image="/boot/initramfs-$KERNEL_PKGBASE.img"
fallback_image="/boot/initramfs-$KERNEL_PKGBASE-fallback.img"
fallback_options="-S autodetect"
EOF

	if ! grep -qs "archlinuxcn" $mount_dir/etc/pacman.conf;then
		cat <<EOF >> $mount_dir/etc/pacman.conf
[archlinuxcn]
SigLevel = Optional TrustAll
Server = https://mirrors.cernet.edu.cn/archlinuxcn/\$arch

EOF
	fi

	# 添加源后必须立马更新，不让报错
	run pacman -Sy archlinuxcn-keyring --noconfirm
	run pacman -S yay timeshift pamac-aur plymouth --noconfirm
}

config_packages() {
	echo 安装 pacman 内核签名 hook
	install -Dm0644 "${device_file}"/kernel.hook $mount_dir/etc/pacman.d/hooks/
	echo 更新 udev hwdb
	run udevadm hwdb --update

	echo 生成 fstab
	boot_uuid=$(blkid -s UUID -o value "$boot_dev")
	root_uuid=$(blkid -s UUID -o value "$rootfs_dev")
	[[ -n $boot_uuid && -n $root_uuid ]] || {
		echo 'Unable to read filesystem UUIDs' >&2
		return 1
	}
	cat > "$mount_dir/etc/fstab" <<EOF
UUID=$root_uuid / btrfs rw,relatime,compress=zstd:3,ssd,discard=async,space_cache=v2,subvol=/@ 0 0
UUID=$boot_uuid /boot vfat rw,relatime,fmask=0022,dmask=0022,codepage=437,iocharset=ascii,shortname=mixed,utf8,errors=remount-ro 0 2
UUID=$root_uuid /home btrfs rw,relatime,compress=zstd:3,ssd,discard=async,space_cache=v2,subvol=/@home 0 0
EOF
	grep -Eq '^[^#]+[[:space:]]+/boot[[:space:]]+vfat[[:space:]]' $mount_dir/etc/fstab || {
		echo 'Generated fstab has no valid /boot vfat mount' >&2
		return 1
	}
	if [[ ! -L $mount_dir/lib || $(readlink "$mount_dir/lib") != usr/lib ]]; then
		echo '/lib must be the standard usr/lib symlink' >&2
		return 1
	fi

	echo 链接 vi 到 vim
	run ln -sf /usr/bin/vim /usr/bin/vi

	echo 配置 sudo
	install -Dm0440 /dev/stdin "$mount_dir/etc/sudoers.d/10-wheel" <<'EOF'
%wheel ALL=(ALL:ALL) NOPASSWD: ALL
EOF

	echo 配置 timezone
	run ln -sf /usr/share/zoneinfo/Asia/Shanghai /etc/localtime

	echo 配置 locale
	sed -i 's/#zh_CN.U/zh_CN.U/' $mount_dir/etc/locale.gen
	run locale-gen
	echo 'LANG=zh_CN.UTF-8' > $mount_dir/etc/locale.conf

	echo 配置 hostname
	echo $HostName > $mount_dir/etc/hostname

	echo 配置 zram
	cat <<EOF > $mount_dir/etc/systemd/zram-generator.conf
[zram0]
zram-size = min(ram / 2, 4096)
compression-algorithm = zstd
EOF

	echo 配置 service
	enable="systemctl enable"
	cat <<EOF >> $mount_dir/usr/lib/systemd/system/systemd-zram-setup@.service
[Install]
WantedBy=multi-user.target
EOF
	run $enable systemd-zram-setup@zram0.service
	run $enable irqbalance
	run $enable NetworkManager
	if [[ $desktop_type =~ 'plasma' ]];then
		run $enable plasmalogin.service
		run sh -c 'command -v balooctl6 >/dev/null && balooctl6 suspend || true'
		run sh -c 'command -v balooctl6 >/dev/null && balooctl6 disable || true'
		echo 配置 Plasma Login Manager
		mkdir -p $mount_dir/etc/plasmalogin.conf.d
		cat <<EOF > $mount_dir/etc/plasmalogin.conf.d/autologin.conf
[Autologin]
User=$UserName
Session=plasma.desktop
EOF

		echo 修复 dolphin ntfs报错
		cat <<EOF >> $mount_dir/etc/udisks2/mount_options.conf
[defaults]
ntfs_defaults=uid=\$UID,gid=\$GID,noatime,prealloc
EOF

		echo 配置 fcitx ENVIRONMENT
		cat <<EOF >> $mount_dir/etc/environment
XMODIFIERS=@im=fcitx
SDL_IM_MODULE=fcitx
GLFW_IM_MODULE=ibus
KWIN_IM_SHOW_ALWAYS=1
EOF
	fi

	run $enable bluetooth
	run $enable mipad2-usb-serial.service
	install -Dm0755 "$device_file/mipad2-grow-root" \
		"$mount_dir/usr/local/libexec/mipad2-grow-root"
	install -Dm0644 "$device_file/mipad2-grow-root.service" \
		"$mount_dir/etc/systemd/system/mipad2-grow-root.service"
	run $enable mipad2-grow-root.service
	mkdir -p "$mount_dir/etc/systemd/system/serial-getty@ttyGS0.service.d"
	cat > "$mount_dir/etc/systemd/system/serial-getty@ttyGS0.service.d/autologin.conf" <<EOF
[Service]
ExecStart=
ExecStart=-/sbin/agetty --autologin $UserName --noclear %I \$TERM
EOF

	echo 配置 包管理器
	run sed -i 's/#Color/Color/' /etc/pacman.conf

	echo 配置 i915
	echo 'options i915 enable_fbc=1' > $mount_dir/etc/modprobe.d/i915.conf
	echo 配置 plymouth mkinitramfs.conf hooks
	run sed -i 's/^HOOKS=(\([^)]*\))/HOOKS=(\1 plymouth)/' /etc/mkinitcpio.conf
	# Action runner is not Mi Pad 2: do not let autodetect drop tablet modules.
	run sed -i 's/[[:space:]]autodetect//g' /etc/mkinitcpio.conf
	# mkinitcpio 某些版本默认启用sd_vconsole hook导致报错修复
	echo "KEYMAP=us" > $mount_dir/etc/vconsole.conf
	run mkinitcpio -P

	echo 配置 ENVIRONMENT
	cat <<EOF >> $mount_dir/etc/environment
# intel vulkan 视频加速
ANV_DEBUG=video-decode,video-encode
LIBVA_DRIVER_NAME=i965

EOF
}

config_user() {
	echo 添加 $UserName 用户
	run useradd -m -G wheel,lp -s '/usr/bin/zsh' $UserName
	run su $UserName -c 'yay -S oh-my-zsh-git --noconfirm'

	run sed -i 's|#[[:space:]]*ZSH_CUSTOM=.*|ZSH_CUSTOM=/usr/share/zsh|' /usr/share/oh-my-zsh/zshrc
	run chmod -R 666 /usr/share/oh-my-zsh/zshrc
	run cp /usr/share/oh-my-zsh/zshrc /home/$UserName/.zshrc
	run su $UserName -c 'source ~/.zshrc;omz theme set ys;omz plugin enable sudo safe-paste extract command-not-found zsh-autosuggestions zsh-syntax-highlighting'
	run cp /home/$UserName/.zshrc /root/.zshrc
	run chown root:root /root/.zshrc
	mkdir -p "$mount_dir/home/$UserName/.config/autostart"
	cat > "$mount_dir/home/$UserName/.config/kwinrc" <<'EOF'
[Wayland]
InputMethod[$e]=/usr/share/applications/org.kde.plasma.keyboard.desktop
VirtualKeyboardEnabled=true

[Xwayland]
Scale=2
EOF
	cat > "$mount_dir/home/$UserName/.config/autostart/mipad2-display.desktop" <<'EOF'
[Desktop Entry]
Type=Application
Name=Mi Pad 2 display scale
Exec=/usr/local/libexec/mipad2-plasma-display
OnlyShowIn=KDE;
X-KDE-autostart-phase=1
EOF
	install -Dm0755 "$device_file/mipad2-plasma-display" \
		"$mount_dir/usr/local/libexec/mipad2-plasma-display"
	run chown -R $UserName:$UserName /home/$UserName/.config

	echo 设置 密码
	run bash -c "echo root:$UserPasswd|chpasswd"
	run bash -c "echo $UserName:$UserPasswd|chpasswd"
}

config_grub(){
	# grub 不注册efi
	run grub-install --target=x86_64-efi --efi-directory=/boot --bootloader-id=arch \
		--removable --no-nvram \
		--modules="part_gpt fat btrfs search search_fs_uuid search_label test configfile normal linux"
	run sed -i 's/GRUB_CMDLINE_LINUX_DEFAULT="loglevel=3 quiet"/GRUB_CMDLINE_LINUX_DEFAULT="loglevel=3 quiet splash plymouth.nolog"/' /etc/default/grub
	run grub-mkconfig -o /boot/grub/grub.cfg
	if [[ -d ./EFI ]]; then
		cp -a ./EFI/. "$mount_dir/boot/EFI/"
	fi
	chown -R root:root $mount_dir/boot/EFI
	boot_uuid=$(blkid -s UUID -o value "$boot_dev")
	cat > "$mount_dir/tmp/mipad2-grub-bootstrap.cfg" <<EOF
insmod part_gpt
insmod fat
insmod btrfs
search --no-floppy --fs-uuid --set=esp $boot_uuid
if [ -z "\$esp" ]; then
  search --no-floppy --label --set=esp boot
fi
set prefix=(\$esp)/grub
configfile \$prefix/grub.cfg
EOF
	install -Dm0644 "$mount_dir/tmp/mipad2-grub-bootstrap.cfg" \
		"$mount_dir/boot/EFI/BOOT/grub.cfg"
	install -Dm0644 "$mount_dir/tmp/mipad2-grub-bootstrap.cfg" \
		"$mount_dir/boot/EFI/arch/grub.cfg"
	install -Dm0644 $device_file/MOK.cer $mount_dir/boot/
	install -Dm0600 $device_file/MOK.key $mount_dir/boot/EFI/
	install -Dm0644 $device_file/MOK.crt $mount_dir/boot/EFI/

	# Firmware trusts Microsoft's UEFI CA, not a user MOK directly.  Keep the
	# Microsoft-signed shim byte-for-byte intact and let it validate the GRUB
	# binary with the already-enrolled, original project MOK certificate.
	# Keep the exact Proxmox shim/mm pair from the tablet's previously working
	# boot partition.  This shim looks for grubx64.efi in its own directory.
	run grub-mkstandalone --format=x86_64-efi \
		--output=/boot/EFI/BOOT/grubx64.efi \
		--modules="part_gpt fat btrfs search search_fs_uuid search_label test configfile normal linux" \
		boot/grub/grub.cfg=/tmp/mipad2-grub-bootstrap.cfg
	install -Dm0644 $device_file/shimx64.efi $mount_dir/boot/EFI/BOOT/BOOTX64.EFI
	install -Dm0644 $device_file/mmx64.efi $mount_dir/boot/EFI/BOOT/mmx64.efi
	echo 使用 Microsoft 签名 shim 和原项目 MOK 签名 GRUB/内核
	run sbsign --key /boot/EFI/MOK.key --cert /boot/EFI/MOK.crt \
		--output /boot/EFI/BOOT/grubx64.efi.signed /boot/EFI/BOOT/grubx64.efi
	run mv /boot/EFI/BOOT/grubx64.efi.signed /boot/EFI/BOOT/grubx64.efi
	run sbsign --key /boot/EFI/MOK.key --cert /boot/EFI/MOK.crt \
		--output /boot/vmlinuz-$KERNEL_PKGBASE /boot/vmlinuz-$KERNEL_PKGBASE
	run sbverify --list /boot/vmlinuz-$KERNEL_PKGBASE
	run sbverify --list /boot/EFI/BOOT/BOOTX64.EFI
	run sbverify --list /boot/EFI/BOOT/grubx64.efi
	run sh -ec 'sbverify --list /boot/EFI/BOOT/BOOTX64.EFI 2>&1 | grep -F "Microsoft Corporation UEFI CA 2011"'
	run sh -ec 'sbverify --list /boot/EFI/BOOT/grubx64.efi 2>&1 | grep -F "my Machine Owner Key"'
	run sh -ec 'sbverify --list /boot/vmlinuz-'$KERNEL_PKGBASE' 2>&1 | grep -F "my Machine Owner Key"'
	cmp $device_file/shimx64.efi $mount_dir/boot/EFI/BOOT/BOOTX64.EFI
	run grub-script-check /tmp/mipad2-grub-bootstrap.cfg
	run grub-script-check /boot/EFI/BOOT/grub.cfg
	run grub-script-check /boot/grub/grub.cfg
}

cleanup_rootfs() {
	run sh -c 'rm -rf /var/cache/pacman/pkg/* /home/*/.cache/yay /tmp/*' || true
}

update_pkgfile() {
    run pkgfile --update
}

all() {
	gpt
	rm_img
	create_img
	format
	mount_img

	install_packages
	config_packages
	config_user
	config_grub
	update_pkgfile
	cleanup_rootfs

	umount_img
	convert
}

if [ -z $1 ];then
	trap 'umount_img || true; disconnect_img || true' EXIT
	all
else
    $1
fi
