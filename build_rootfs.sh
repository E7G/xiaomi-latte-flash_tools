#!/bin/bash
set -e
# set -x
shopt -s expand_aliases

UserName="user"
UserPasswd="123456"
HostName="mipad2"
desktop_type="gnome" # plasma or gnome

modprobe nbd max_part=8
boot_dev=/dev/nbd0
rootfs_dev=/dev/nbd1
mount_dir=./rootfs
device_file=./device_files

# 判断文件夹是否存在，不存在则创建
if [ ! -d $mount_dir ]; then
	mkdir -p $mount_dir
fi

is_mount() {
	mount | grep $mount_dir &>/dev/null
	return $?
}

convert() {
	echo 转换镜像格式，从qcow2到img
	# qcow2 to img
	pushd ./images
	echo convert boot.qcow2 to xiaomi-latte-boot.img
	qemu-img convert -f qcow2 -O raw boot.qcow2 xiaomi-latte-boot.img
	echo convert rootfs.qcow2 to xiaomi-latte-rootfs.img
	qemu-img convert -f qcow2 -O raw rootfs.qcow2 xiaomi-latte-rootfs.img
	popd
}

gpt(){
	python gpt_ini2bin.py
}

rm_img() {
	umount_img
	sleep 1
	pushd ./images
	rm -rf ./boot.qcow2 ./rootfs.qcow2
	popd
}

create_img() {
	pushd ./images
	qemu-img create -f qcow2 boot.qcow2 300M
	qemu-img create -f qcow2 rootfs.qcow2 5G
	popd
}

# 假定已经连接了镜像
flag_connect=1
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
	pushd ./images
    qemu-nbd -d $boot_dev
	qemu-nbd -d $rootfs_dev
	popd
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
		return
	fi
    umount -R $mount_dir || true
	disconnect_img
}

firmware=(
	linux-firmware-broadcom
	linux-firmware-intel
	libva-intel-driver
	intel-ucode
	vulkan-intel
)

packages=(
base-devel
# Shell
bash-completion zsh-completions sudo reflector pkgfile less btop
zsh-autocomplete zsh-syntax-highlighting
vim
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
mpv
# 电源配置
power-profiles-daemon
# 线程优化
irqbalance
# zram
zram-generator
)

plasma=(
# sddm
sddm sddm-kcm # kde 控制模块
# Kde 最小安装
plasma-{desktop,pa,nm,systemmonitor} breeze-gtk kde-gtk-config powerdevil kscreen kgamma kinfocenter konsole fcitx5-im kcm-fcitx5 fcitx5-chinese-addons kate dolphin colord-kde gpm ark kwalletmanager kdeconnect sshfs
# 蓝牙
bluedevil
# 屏幕跟随传感器旋转
iio-sensor-proxy

plasma-wayland-protocols
krdp
)

# gnome 最小安装
gnome=(
# 显示器管理器
gdm
# 桌面环境
gnome-shell gnome-shell-extension-appindicator gnome-backgrounds adw-gtk-theme
# 设置
gnome-control-center gnome-tweaks dconf-editor
# 文件管理器
nautilus gvfs-smb
# 终端
gnome-console
# 文本编辑器
gnome-text-editor
# 任务管理器
gnome-system-monitor
# 密钥管理器
seahorse
# 输入法
ibus ibus-libpinyin
# 远程桌面服务器
gnome-remote-desktop
# 摄像头
snapshot
)

alias run="arch-chroot $mount_dir"
install_packages() {
	# 安装基础包
	pacstrap -C "${device_file}"/pacman.conf -c $mount_dir base iptables-nft ${firmware[@]} grub efibootmgr sbsigntools

	echo Install linux-upstream-6.14.0-2-x86_64.pkg.tar.zst
	pacstrap -C "${device_file}"/pacman.conf -U $mount_dir "${device_file}"/linux-upstream-6.14.0-2-x86_64.pkg.tar.zst
	run sh -c 'cp /usr/lib/modules/*/vmlinuz /boot/vmlinuz-linux-upstream'

	declare -n desktop=$desktop_type
	pacstrap -C "${device_file}"/pacman.conf -c $mount_dir ${packages[@]} ${desktop[@]} mkinitcpio

	if ! grep -qs "archlinuxcn" $mount_dir/etc/pacman.conf;then
		cat <<EOF >> $mount_dir/etc/pacman.conf
[archlinuxcn]
Server = https://mirrors.cernet.edu.cn/archlinuxcn/\$arch

EOF
	fi

	# 添加源后必须立马更新，不让报错
	run pacman -Sy archlinuxcn-keyring --noconfirm
	run pacman -S paru timeshift pamac-aur plymouth --noconfirm
}

config_packages() {
	echo 复制 pacman 内核 hook
	cp "${device_file}"/kernel.hook $mount_dir/etc/pacman.d/hooks/
	echo 复制 屏幕触控按键配置
	cp "${device_file}"/61-keyboard.hwdb $mount_dir/usr/lib/udev/hwdb.d/
	run udevadm hwdb --update
	echo 复制 蓝牙固件
	cp "${device_file}"/BCM4356A2.hcd $mount_dir/usr/lib/firmware/brcm/
	echo 创建 alsa 配置文件
	run sh -c 'echo "snd_soc_rt5659" >> /etc/modules-load.d/modules.conf'
	run mkdir -p /usr/share/alsa/ucm2/conf.d/cht-bsw-rt5659
	cat <<EOF > $mount_dir/usr/share/alsa/ucm2/conf.d/cht-bsw-rt5659/cht-bsw-rt5659.conf
Syntax 3

SectionUseCase."HiFi" {
	File "HiFi.conf"
	Comment "Default"
}
EOF
	cat <<EOF > $mount_dir/usr/share/alsa/ucm2/conf.d/cht-bsw-rt5659/HiFi.conf
SectionVerb {
	If.Controls {
		Condition {
			Type ControlExists
			Control "name='media0_in Gain 0 Switch'"
		}
		Before.EnableSequence "0"
		True {
			Include.pe.File "/platforms/bytcr/PlatformEnableSeq.conf"
			Include.pd.File "/platforms/bytcr/PlatformDisableSeq.conf"
		}
	}
    EnableSequence [
		cset "name='codec_out0 Gain 0 Volume' 72%"
		cset "name='IF2 ADC Mux' DAC_REF"
		cset "name='IF3 ADC Mux' IF_ADC1"
		# 音量50%
		# cset "name='DAC1 Playback Volume' 50%"
		# 设置右扬声器使用右声道
		cset "name='Amp Input1' 1" 
    ]
	DisableSequence []
	Value {}
}

SectionDevice."Speaker" {
	Comment "Stereo Speakers"

	ConflictingDevice []

	Value {
		PlaybackPCM "hw:\${CardId}"
		# The speaker ampl. path on the 5659 has no speaker vol control
		# Use the digital DAC1 master control as MixerElem
		PlaybackMixerElem "DAC1"
	}

	EnableSequence [
		cset "name='DAC1 Playback Switch' on"
	]
	DisableSequence [
		cset "name='DAC1 Playback Switch' off"
	]
}

SectionDevice."IntMic" {
	Comment "Microphone"

	ConflictingDevice []

	EnableSequence [
		# 开启 Int Mic
		cset "name='Int Mic Switch' on"
		cset "name='RECMIX1L BST3 Switch' on"
		cset "name='RECMIX1R BST4 Switch' on"
		cset "name='STO1 ADC Capture Switch' on"

		# 开启 Boost（如果需要）
		cset "name='IN3 Boost Volume' 45"
		cset "name='IN4 Boost Volume' 45"

		# 设置 ADC 源 (选择录音混音器的输出作为 ADC 输入)
		cset "name='Stereo1 ADC Source' 'ADC1'"
		cset "name='Stereo1 ADC1 Source' 'ADC'"

		# 设置录音混音器输出到 ADC
		cset "name='Stereo1 ADC MIXL ADC1 Switch' on"
		cset "name='Stereo1 ADC MIXR ADC1 Switch' on"
		cset "name='DAC1 MIXL Stereo ADC Switch' off"
		cset "name='DAC1 MIXR Stereo ADC Switch' off"
		cset "name='media_loop2_out mix 0 codec_in0 Switch' on"
		cset "name='pcm1_out mix 0 media_loop2_in Switch' on"

		# 设置 ADC 音量
		cset "name='IN Capture Volume' 23"
		cset "name='STO1 ADC Capture Volume' 70"
	]

	DisableSequence [
		cset "name='Int Mic Switch' off"
		cset "name='RECMIX1L BST3 Switch' off"
		cset "name='RECMIX1R BST4 Switch' off"
	]

	Value {
		CapturePCM "hw:\${CardId}"
		CaptureMixerElem "Main Mic"
	}
}
EOF
	echo 生成 fstab
	genfstab -U $mount_dir >> $mount_dir/etc/fstab
	# fix fstab
	sed -i 's/\\0[^ ]*//' $mount_dir/etc/fstab
	sed -i '/swapfile/d' $mount_dir/etc/fstab

	echo 链接 vi 到 vim
	run ln -s /usr/bin/vim /usr/bin/vi

	echo 配置 sudo
	sed -i 's/# %wheel ALL=(ALL:ALL) N/%wheel ALL=(ALL:ALL) N/' $mount_dir/etc/sudoers

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
	if [[ $desktop_type == 'gnome' ]];then
		run $enable gdm
	fi
	if [[ $desktop_type =~ 'plasma' ]];then
		run $enable sddm
		balooctl=`run sh -c 'ls /usr/bin/balooctl*'`
		run $balooctl suspend
		run $balooctl disable
			echo 配置 sddm
		mkdir $mount_dir/etc/sddm.conf.d

		cat <<EOF > $mount_dir/etc/sddm.conf.d/autologin.conf
[General]
Numlock=on
[Autologin]
Relogin=false
Session=plasma
User=$UserName
[Theme]
Current=breeze
EOF
		cat <<EOF > $mount_dir/etc/sddm.conf.d/10-wayland.conf
[General]
DisplayServer=wayland
GreeterEnvironment=QT_WAYLAND_SHELL_INTEGRATION=layer-shell

[Wayland]
CompositorCommand=kwin_wayland --drm --no-lockscreen --no-global-shortcuts --locale1 --inputmethod maliit-keyboard
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
EOF
	fi

	run $enable bluetooth

	echo 配置 paru
	run sed -i 's/#Color/Color/' /etc/pacman.conf
	run sed -i 's/#BottomUp/BottomUp/' /etc/paru.conf

	echo 配置 i915
	echo 'options i915 enable_fbc=1' > $mount_dir/etc/modprobe.d/i915.conf
	echo 配置 plymouth mkinitramfs.conf hooks
	run sed -i 's/^HOOKS=(\([^)]*\))/HOOKS=(\1 plymouth)/' /etc/mkinitcpio.conf
	run mkinitcpio -P

	echo 配置 ENVIRONMENT
	cat <<EOF >> $mount_dir/etc/environment
# intel vulkan 视频加速
ANV_DEBUG=video-decode,video-encode

EOF
}

config_user() {
	echo 添加 $UserName 用户
	run useradd -m -G wheel,lp -s '/usr/bin/zsh' $UserName
	run su $UserName -c 'paru -S oh-my-zsh-git --noconfirm'

	run sed -i 's|#[[:space:]]*ZSH_CUSTOM=.*|ZSH_CUSTOM=/usr/share/zsh|' /usr/share/oh-my-zsh/zshrc
	run chmod -R 666 /usr/share/oh-my-zsh/zshrc
	run cp /usr/share/oh-my-zsh/zshrc /home/$UserName/.zshrc
	run su $UserName -c 'source ~/.zshrc;omz theme set ys;omz plugin enable sudo safe-paste extract command-not-found zsh-autocomplete zsh-syntax-highlighting'
	run cp /home/$UserName/.zshrc /root/.zshrc
	run chown root:root /root/.zshrc

	echo 设置 密码
	run bash -c "echo root:$UserPasswd|chpasswd"
	run bash -c "echo $UserName:$UserPasswd|chpasswd"
}

config_grub(){
	# grub 不注册efi
	run grub-install --target=x86_64-efi --efi-directory=/boot --bootloader-id=arch --removable
	run sed -i 's/GRUB_CMDLINE_LINUX_DEFAULT="loglevel=3 quiet"/GRUB_CMDLINE_LINUX_DEFAULT="loglevel=3 quiet splash plymouth.nolog"/' /etc/default/grub
	run grub-mkconfig -o /boot/grub/grub.cfg
	kernel=`run sh -c 'ls /boot/vmlinuz*'`
	cp -r ./EFI $mount_dir/boot/
	echo 签名内核
	run sbsign --key /boot/EFI/MOK.key --cert /boot/EFI/MOK.crt --output $kernel $kernel
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

    umount_img
}

if [ -z $1 ];then
    all
else
    $1
fi
