V ?= 0
ifeq ($(V),0)
.SILENT:
endif

# LineageOS 21.1	为 Android 14 6.12.30-zenith
# LineageOS 17.1	为 Android 10 5.8.0-android-x86_64-93451-g2eba2073e8a6
# ProjectSakura-5.2	为 Android 11 5.10.61-GoogleLTS-xanmod1-pledge
# BlissOS 15		为 Android 12 6.1.112-gloria-xanmod1
# BlissOS 16		为 Android 13 6.1.112-gloria-xanmod1
# BlissOS-Zenith 16	为 Android 13 6.9.9-zenith
# BlissOS-Zenith17.2为 Android 14 6.7.10-zenith-xanmod1
# BlissOS 18.4		为 Android 15 6.6.89-crimson-xanmod1
VER_LIST := 17.1 5 14 15 16 17.2 18 21
VER ?= 16
# 判断输入版本是否在范围内
ifeq ($(filter $(VER),$(VER_LIST)),)
$(error "VER must be one of $(VER_LIST)")
endif

NO_SUPPORT_EROFS_LIST := 17 5
RAW_SYSTEM_IMAGE_LIST := 
HAVE_DROPBEAR := n

UID := $(shell id -u)
GID := $(shell id -g)
MOUNT := sudo mount
UMOUNT := sudo umount
CHOWN := sudo chown
CHMOD := sudo chmod
INSTALL := sudo install
CP := sudo cp
RM := sudo rm -rf

BOOT_SIZE ?= 64
DATA_SIZE ?= 1024

PWD = $(shell pwd)
DEVICE_FILES_DIR := $(PWD)/device_files

# 输出文件夹
O := $(PWD)
IMAGES_DIR := $(O)/images
BUILD_DIR := $(O)/build
SHIM_GRUB_DIR := $(BUILD_DIR)/shim_grub
KERNEL_DIR := $(BUILD_DIR)/kernel
ISO_DIR := $(BUILD_DIR)/iso-$(VER)
INITRD_DIR := $(BUILD_DIR)/initrd-$(VER)
BOOT_DIR := $(BUILD_DIR)/boot
SYSTEM_DIR := $(BUILD_DIR)/system
DATA_DIR := $(BUILD_DIR)/data

OVERLAY_DIR := $(PWD)/overlay
OVERLAY_BOOT_DIR := $(OVERLAY_DIR)/boot
OVERLAY_SYSTEM_DIR := $(OVERLAY_DIR)/system
OVERLAY_DATA_DIR := $(OVERLAY_DIR)/data

SHIM_URL := https://dl.fedoraproject.org/pub/fedora/linux/releases/43/Everything/x86_64/os/Packages/s/shim-x64-15.8-3.x86_64.rpm
GRUB2_EFI_URL := https://dl.fedoraproject.org/pub/fedora/linux/releases/43/Everything/x86_64/os/Packages/g/grub2-efi-x64-2.12-40.fc43.x86_64.rpm

SHIM_FILE := $(O)/shim-x64.rpm
GRUB2_EFI_FILE := $(O)/grub2-efi-x64.rpm
$(SHIM_FILE): | $(O)
	wget --quiet "$(SHIM_URL)" -O "$@"
$(GRUB2_EFI_FILE): | $(O)
	wget --quiet "$(GRUB2_EFI_URL)" -O "$@"

SHIM_GRUB_STAMP := $(BUILD_DIR)/.shim-grub.stamp
$(SHIM_GRUB_STAMP): $(SHIM_FILE) $(GRUB2_EFI_FILE) | $(SHIM_GRUB_DIR)
	echo "解包shim文件"
	rpm2cpio $(SHIM_FILE) | cpio -idm -D "$(SHIM_GRUB_DIR)"
	rpm2cpio $(GRUB2_EFI_FILE) | cpio -idm -D "$(SHIM_GRUB_DIR)"
	touch $@
	echo "解包shim文件:" "完成"
unpack_shim_grub: $(SHIM_GRUB_STAMP)
.PHONY: unpack_shim_grub

KERNEL_PACKAGE_FILE := $(wildcard kernel-*-zenith.tar.gz)
KERNEL_STAMP := $(KERNEL_DIR)/.stamp
$(KERNEL_STAMP): $(KERNEL_PACKAGE_FILE) | $(KERNEL_DIR)
	echo "解包内核文件:" $<
	tar -xzf $< -C "$(KERNEL_DIR)"
	touch $@
	echo "解包内核文件:" "完成"
unpack_kenrel: $(KERNEL_STAMP)
clean_kenrel:
	$(RM) "$(KERNEL_DIR)" "$(KERNEL_STAMP)"
.PHONY: unpack_kenrel clean_kenrel

ifeq ($(VER),5)
ISO_FILE := $(wildcard ProjectSakura-$(VER).*.iso)
else
ISO_FILE := $(wildcard *$(VER)*.iso)
endif
ISO_FILE := $(firstword $(ISO_FILE))
ISO_STAMP := $(ISO_DIR)/.stamp
$(ISO_STAMP): $(ISO_FILE) | $(ISO_DIR)
	echo "解包ISO文件:" $<
	7z x -aos -o"$(ISO_DIR)" "$<"
	touch $@
	echo "解包ISO文件:" "完成"
unpack_iso: $(ISO_STAMP)
clean_iso:
	$(RM) "$(ISO_DIR)" "$(ISO_STAMP)"
.PHONY: unpack_iso clean_iso

DSDT_FILE := $(DEVICE_FILES_DIR)/dsdt.aml
$(DSDT_FILE): $(DEVICE_FILES_DIR)/dsdt.dsl
	iasl -ve -ts -w1 "$<"

INITRD_FILE := $(BUILD_DIR)/initrd-$(VER).cpio.gz
INITRD_STAMP := $(BUILD_DIR)/.initrd-$(VER).stamp
INITRD_PATCH_FILE := $(DEVICE_FILES_DIR)/initrd-$(VER).patch
ifeq ($(wildcard $(INITRD_PATCH_FILE)),)
INITRD_PATCH_FILE := $(DEVICE_FILES_DIR)/initrd.patch
endif
INITRD_PATCH_STAMP := $(BUILD_DIR)/.initrd-$(VER).patch.stamp
$(INITRD_STAMP): $(ISO_STAMP)
	echo "解包initrd文件"
	$(RM) "$(INITRD_DIR)"
	mkdir -p "$(INITRD_DIR)"
	zcat "$(ISO_DIR)/initrd.img" | (cd "$(INITRD_DIR)" && cpio -id)
	touch $@
	echo "解包initrd文件:" "完成"
unpack_initrd: $(INITRD_STAMP)
$(INITRD_PATCH_STAMP): $(INITRD_STAMP) $(INITRD_PATCH_FILE) $(DSDT_FILE)
	echo "initrd 打补丁"
	patch -p1 < $(INITRD_PATCH_FILE) -d "$(INITRD_DIR)"
	sed -i 's|bliss.model="$$BOARD"|bliss.model="$$PRODUCT"|' "$(INITRD_DIR)/init"
	$(INSTALL) -Dm755 "$(DSDT_FILE)" "$(INITRD_DIR)/kernel/firmware/acpi/dsdt.aml"
	touch $@
	echo "initrd 打补丁:" "完成"
patch_initrd: $(INITRD_PATCH_STAMP)
$(INITRD_FILE): $(INITRD_PATCH_STAMP)
	echo "initrd 打包"
	cd "$(INITRD_DIR)";find . | cpio -o -H newc | gzip > "$(INITRD_FILE)"
	echo "initrd 打包:" "完成"
pack_initrd: $(INITRD_FILE)
clean_initrd:
	$(RM) "$(INITRD_DIR)" "$(INITRD_FILE)" "$(INITRD_STAMP)" "$(INITRD_PATCH_STAMP)"
.PHONY: unpack_initrd patch_initrd pack_initrd

BOOT_FILE := $(IMAGES_DIR)/boot.img
$(BOOT_FILE): $(OVERLAY_BOOT_DIR) $(SHIM_GRUB_STAMP) $(INITRD_FILE) $(KERNEL_STAMP) | $(IMAGES_DIR) $(BOOT_DIR)
	echo "打包boot.img"
	if grep -q "$(BOOT_DIR)" /proc/mounts;then $(UMOUNT) "$(BOOT_DIR)";fi
	sudo truncate -s $(BOOT_SIZE)M "$@"
	$(CHOWN) $(UID):$(GID) "$@"
	mkfs.vfat -F 32 -n ESP "$@"
	$(MOUNT) -o loop "$@" "$(BOOT_DIR)"
	$(INSTALL) -D "$(SHIM_GRUB_DIR)/boot/efi/EFI/BOOT/BOOTX64.EFI" "$(BOOT_DIR)/EFI/boot/bootx64.efi"
	$(INSTALL) -D "$(SHIM_GRUB_DIR)/boot/efi/EFI/fedora/mmx64.efi" "$(BOOT_DIR)/EFI/boot/mmx64.efi"
	$(INSTALL) -D "$(SHIM_GRUB_DIR)/boot/efi/EFI/fedora/grubx64.efi" "$(BOOT_DIR)/EFI/boot/grubx64.efi"
	$(INSTALL) -D "$(INITRD_FILE)" "$(BOOT_DIR)/EFI/BlissOS/initrd.cpio.gz"
	$(INSTALL) -D "$(KERNEL_DIR)"/vmlinuz-* "$(BOOT_DIR)/EFI/BlissOS/vmlinuz"
	$(CP) -r "$(OVERLAY_BOOT_DIR)"/* "$(BOOT_DIR)"
	$(CHMOD) -R 644 "$(BOOT_DIR)/"
	$(UMOUNT) "$(BOOT_DIR)"
	echo "打包boot.img:" "完成"
boot.img: $(BOOT_FILE)
mount_boot: $(BOOT_FILE) umount_boot
	$(MOUNT) -o loop "$<" "$(BOOT_DIR)"
umount_boot:
	$(UMOUNT) "$(BOOT_DIR)" || echo "未挂载boot.img"
clean_boot: umount_boot
	$(RM) "$(BOOT_FILE)"
.PHONY: boot.img mount_boot umount_boot clean_boot

F2FS :=
DATA_FILE := $(IMAGES_DIR)/data.img
$(DATA_FILE): $(OVERLAY_DATA_DIR) | $(IMAGES_DIR) $(DATA_DIR)
	echo "打包data.img"
	if grep -q "$(DATA_DIR)" /proc/mounts;then $(UMOUNT) "$(DATA_DIR)";fi
	sudo truncate -s $(DATA_SIZE)M "$@"
	$(CHOWN) $(UID):$(GID) "$@"
	if (command -v mkfs.f2fs &> /dev/null) && [ -z "$(F2FS)" ];then \
        echo "f2fs-tools found, using f2fs for data image."; \
        sudo mkfs.f2fs -l userdata -f "$@"; \
    else \
        echo "f2fs-tools not found, using ext4 for data image."; \
        sudo mkfs.ext4 -L userdata -F "$@"; \
    fi
	$(MOUNT) -o loop "$@" "$(DATA_DIR)"
	$(CP) -r "$(OVERLAY_DATA_DIR)/"* "$(DATA_DIR)" || echo OVERLAY_DATA_DIR为空, 跳过复制.
	$(CHMOD) -R 755 "$(DATA_DIR)/"
	$(UMOUNT) "$(DATA_DIR)"
	if command -v img2simg &> /dev/null; then \
        img2simg "$@" "$(IMAGES_DIR)/data.simg"; \
    else \
        echo "img2simg not found, skipping sparse conversion."; \
    fi
	echo "打包data.img:" "完成"
data.img: $(DATA_FILE)
mount_data: $(DATA_FILE) umount_data
	$(MOUNT) -o loop "$<" "$(DATA_DIR)"
umount_data:
	$(UMOUNT) "$(DATA_DIR)" || echo "未挂载data.img"
clean_data: umount_data
	$(RM) "$(DATA_FILE)" "$(IMAGES_DIR)/data.simg"
.PHONY: data.img mount_data umount_data clean_data

KEY_REMAP_PROG := $(BUILD_DIR)/key-remap
$(KEY_REMAP_PROG): $(DEVICE_FILES_DIR)/mipad2_keymap.c | $(BUILD_DIR)
	gcc -o "$@" "$<" -static

DROPBEAR_URL := https://github.com/ribbons/android-dropbear/releases/latest/download/dropbear-x86_64-linux-android.zip
DROPBEAR_ZIP := $(O)/dropbear-x86_64-linux-android.zip
DROPBEAR_FILE := $(BUILD_DIR)/dropbear
$(DROPBEAR_ZIP): | $(O)
	wget --quiet $(DROPBEAR_URL) -O "$@"
$(DROPBEAR_FILE): $(DROPBEAR_ZIP) | $(BUILD_DIR)
	unzip "$<" -d "$(BUILD_DIR)" dropbear
	touch $@

EROFS :=
SQUASHFS_COMP := -comp xz -Xdict-size 1M
ifneq ($(filter $(VER),$(NO_SUPPORT_EROFS_LIST)),)
EROFS := n
SQUASHFS_COMP := -comp gzip
else ifneq ($(filter $(VER),$(RAW_SYSTEM_IMAGE_LIST)),)
EROFS := n
SQUASHFS := n
endif
SYSTEM_FILE := $(IMAGES_DIR)/system.img
SYSTEM_UNCOMP_DIR := $(BUILD_DIR)/system_uncomp_$(VER)
SYSTEM_UNCOMP_FILE := $(SYSTEM_UNCOMP_DIR)/system.img
$(SYSTEM_UNCOMP_FILE): $(ISO_STAMP) | $(SYSTEM_UNCOMP_DIR)
	echo "解包system.img"
	if [ -f "$(SYSTEM_UNCOMP_FILE)" ]; then \
        $(RM) "$(SYSTEM_UNCOMP_FILE)"; \
    fi
	if [ -f "$(ISO_DIR)/system.sfs" ]; then \
        unsquashfs -d "$(SYSTEM_UNCOMP_DIR)" "$(ISO_DIR)/system.sfs"; \
    elif [ -f "$(ISO_DIR)/system.efs" ]; then \
		$(RM) "$(SYSTEM_UNCOMP_DIR)"/*.txt*; \
        fsck.erofs --extract="$(SYSTEM_UNCOMP_DIR)/" "$(ISO_DIR)/system.efs"; \
    fi
	touch $@
	echo "解包system.img:" "完成"
unpack_system: $(SYSTEM_UNCOMP_FILE)
$(SYSTEM_FILE): $(OVERLAY_SYSTEM_DIR) $(SYSTEM_UNCOMP_FILE) $(KERNEL_STAMP) $(KEY_REMAP_PROG) \
				$(DROPBEAR_FILE) $(SSH_KEY_PUB) | $(SYSTEM_DIR) $(IMAGES_DIR)
	echo "修改system"
	if grep -q "$(SYSTEM_DIR)" /proc/mounts;then $(UMOUNT) "$(SYSTEM_DIR)";fi
	$(MOUNT) -o loop "$(SYSTEM_UNCOMP_FILE)" "$(SYSTEM_DIR)"

	$(RM) "$(SYSTEM_DIR)/system/lib/modules"
	$(INSTALL) -dm755 "$(SYSTEM_DIR)/system/lib/modules"
	$(CP) -r "$(KERNEL_DIR)/lib/modules/"* "$(SYSTEM_DIR)/system/lib/modules"

	$(INSTALL) --strip -Dm755 "$(KEY_REMAP_PROG)" "$(SYSTEM_DIR)/system/bin/key-remap"

	cd "$(SYSTEM_DIR)"; if [ -f "$(OVERLAY_DIR)/system_modify.sh" ]; then sudo sh "$(OVERLAY_DIR)/system_modify.sh"; fi
	$(CP) -r "$(OVERLAY_SYSTEM_DIR)/"* "$(SYSTEM_DIR)" || echo OVERLAY_SYSTEM_DIR为空, 跳过复制.

	if [ -z "$(HAVE_DROPBEAR)" ];then \
		$(INSTALL) --strip -Dm755 "$(DROPBEAR_FILE)" "$(SYSTEM_DIR)/system/bin/dropbear";\
		$(INSTALL) -Dm755 "$(SSH_KEY_PUB)" "$(SYSTEM_DIR)/system/etc/dropbear/authorized_keys";\
	else \
		$(RM) -rf "$(SYSTEM_DIR)/system/etc/dropbear";\
		$(RM) -rf "$(SYSTEM_DIR)/system/etc/init/sshd.rc";\
	fi

	$(CHMOD) -R 755 "$(SYSTEM_DIR)/"

	echo "修改system:" "完成"
	echo "打包system.img"
	$(UMOUNT) "$(SYSTEM_DIR)" || true
	$(RM) "$(SYSTEM_UNCOMP_DIR)"/*.txt*;
	if (command -v mkfs.erofs &> /dev/null) && [ -z "$(EROFS)" ];then \
        echo "erofs-utils found, using erofs for system image."; \
        mkfs.erofs -L system -zlzma "$@" "$(SYSTEM_UNCOMP_DIR)"; \
    elif (command -v mksquashfs &> /dev/null) && [ -z "$(SQUASHFS)" ];then \
        echo "squashfs-tools found, using squashfs for system image."; \
        mksquashfs "$(SYSTEM_UNCOMP_DIR)" "$@" -b 1M $(SQUASHFS_COMP) -noappend; \
    else \
        echo "erofs-utils and squashfs-tools not found, no package"; \
        cp "$(SYSTEM_UNCOMP_FILE)" "$@"; \
    fi
	touch $@
	echo "打包system.img:" "完成"
pack_system system.img: $(SYSTEM_FILE)
mount_system: $(SYSTEM_UNCOMP_FILE) umount_system
	$(MOUNT) -o loop "$<" "$(SYSTEM_DIR)"
umount_system:
	$(UMOUNT) "$(SYSTEM_DIR)" || echo "未挂载system.img"
clean_system:
	$(RM) $(SYSTEM_UNCOMP_FILE) $(SYSTEM_UNCOMP_DIR)/system.img $(SYSTEM_UNCOMP_DIR)/system_image_info.txt
.PHONY: unpack_system pack_system system.img mount_system umount_system clean_system

GPT_FILE := $(IMAGES_DIR)/gpt.bin
$(GPT_FILE): $(DEVICE_FILES_DIR)/gpt.ini | $(IMAGES_DIR)
	python3 "$(DEVICE_FILES_DIR)/gpt_ini2bin.py" -c "$<" "$@"
gpt.bin: $(GPT_FILE)
.PHONY: gpt.bin

clean: umount_boot umount_system umount_data
	$(RM) $(BUILD_DIR)
clean_images:
	$(RM) $(IMAGES_DIR)
clean_all: clean clean_images
	$(RM) $(SHIM_FILE) $(GRUB2_EFI_FILE)
	$(RM) $(DEVICE_FILES_DIR)/dsdt.{aml,hex}
.PHONY: clean clean_images clean_all

flash_gpt: $(GPT_FILE)
	fastboot flash gpt "$<"
flash_boot: $(BOOT_FILE)
	fastboot flash boot "$<"
flash_system: $(SYSTEM_FILE)
	fastboot flash system "$<"
flash_data: $(DATA_FILE)
	fastboot flash data "$<"
flash_boot_system: flash_boot flash_system
flash_reboot:
	fastboot reboot
flash_all: flash_gpt flash_boot flash_system flash_data flash_reboot
.PHONY: flash_gpt flash_boot flash_system flash_boot_system flash_data flash_reboot flash_all

all: gpt.bin boot.img system.img data.img
.PHONY: all

SSH_KEY := $(DEVICE_FILES_DIR)/id_rsa
SSH_KEY_PUB := $(DEVICE_FILES_DIR)/id_rsa.pub
$(SSH_KEY) $(SSH_KEY_PUB): | $(DEVICE_FILES_DIR)
	ssh-keygen -t rsa -N "" -f "$@"

ssh: $(SSH_KEY)
# 依赖 内核 PTY 支持
	echo 如果遇到连接时间过长问题，开个新终端执行 ping 192.168.255.1
	ssh -i "$(SSH_KEY)" -t root@192.168.255.1 || true
.PHONY: ssh

QEMU_VIRGL := y
QEMU_DEBUG := 0
KERNEL_DEFAULT_CMDLINE := console=tty1 console=ttyS0,115200 DATA=/dev/sdb DEBUG=$(QEMU_DEBUG)
EXTRA_KERNEL_CMDLINE := 
QEMU_KERNEL_CMDLINE = $(KERNEL_DEFAULT_CMDLINE) $(EXTRA_KERNEL_CMDLINE)

ifeq ($(QEMU_VIRGL),n)
	QEMU_KERNEL_CMDLINE += nomodeset HWACCEL=0
else
	QEMU_KERNEL_CMDLINE += 
endif
ifeq ($(QEMU_DEBUG),0)
	QEMU_KERNEL_CMDLINE += quiet
endif
KVM := y
QEMU_KVM :=
ifeq ($(KVM),y)
	QEMU_KVM := -enable-kvm
endif
QEMU_MEM := 1800
QEMU_KERNEL_FILE := $(wildcard $(KERNEL_DIR)/vmlinuz-* )
QEMU_INITRD_FILE := $(INITRD_FILE)
QEMU_SYSTEM_FILE := $(SYSTEM_FILE)
QEMU_DATA_FILE := $(BUILD_DIR)/data.qcow2
$(QEMU_DATA_FILE): $(DATA_FILE)
	qemu-img convert -f raw -O qcow2 "$<" "$@"
qemu: $(QEMU_INITRD_FILE) $(QEMU_SYSTEM_FILE) $(QEMU_DATA_FILE)
	qemu-system-x86_64 -cpu Broadwell -M q35 -device virtio-tablet-pci \
	-kernel $(QEMU_KERNEL_FILE) -initrd "$(QEMU_INITRD_FILE)" -append "$(QEMU_KERNEL_CMDLINE)" \
	-drive if=pflash,format=raw,readonly=on,file=/usr/share/edk2/x64/OVMF_CODE.4m.fd \
	-device virtio-vga-gl -display gtk,gl=on,zoom-to-fit=off \
	-nic user,model=virtio-net-pci,mac=52:54:00:12:34:56,hostfwd=tcp::5555-:5555,hostfwd=tcp::5522-:22 \
	-serial stdio -hda "$(QEMU_SYSTEM_FILE)" -hdb "$(QEMU_DATA_FILE)" \
	-m "$(QEMU_MEM)" -smp 4 $(QEMU_KVM)
qemu-iso: $(QEMU_DATA_FILE)
	qemu-system-x86_64 -cpu Broadwell -M q35 -device virtio-tablet-pci \
	-drive if=pflash,format=raw,readonly=on,file=/usr/share/edk2/x64/OVMF_CODE.4m.fd \
	-device virtio-vga-gl -display gtk,gl=on,zoom-to-fit=off \
	-nic user,model=virtio-net-pci,mac=52:54:00:12:34:56,hostfwd=tcp::5555-:5555,hostfwd=tcp::5522-:22 \
	-serial stdio -cdrom "$(ISO_FILE)" -hda "$(QEMU_DATA_FILE)" \
	-m "$(QEMU_MEM)" -smp 4 $(QEMU_KVM)
mount_qemu_data: $(QEMU_DATA_FILE) umount_qemu_data
	sudo guestmount -a "$<" -m /dev/sda "$(DATA_DIR)"
umount_qemu_data:
	sudo guestunmount "$(DATA_DIR)" || echo "未挂载data.img"
clean_qemu:
	$(RM) $(QEMU_DATA_FILE)
.PHONY: qemu mount_qemu_data umount_qemu_data clean_qemu

dnx.7z: all
	7z a DNX_Fastboot.7z $(IMAGES_DIR)/*.img $(IMAGES_DIR)/*.simg $(PWD)/*.bat
.PHONY: dnx.7z

# 文件夹创建目标自动生成
DIR_VARS := $(filter %_DIR,$(.VARIABLES)) $(O)
ALL_DIRS := $(foreach v,$(DIR_VARS),$($(v)))
$(ALL_DIRS):
	mkdir -p $@
