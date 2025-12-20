V ?= 0
ifeq ($(V),0)
.SILENT:
endif

VER_LIST := 14 15 16
# 14 15 16
VER ?= 15
# 判断输入版本是否在范围内
ifeq ($(filter $(VER),$(VER_LIST)),)
$(error "VER must be one of $(VER_LIST)")
endif

UID := $(shell id -u)
GID := $(shell id -g)
MOUNT := sudo mount
UMOUNT := sudo umount
CHOWN := sudo chown
CHMOD := sudo chmod
INSTALL := sudo install
CP := sudo cp

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
INITRD_DIR := $(BUILD_DIR)/initrd
BOOT_DIR := $(BUILD_DIR)/boot
SYSTEM_DIR := $(BUILD_DIR)/system
DATA_DIR := $(BUILD_DIR)/data

OVERLAY_DIR := $(PWD)/overlay
OVERLAY_BOOT_DIR := $(OVERLAY_DIR)/boot
OVERLAY_SYSTEM_DIR := $(OVERLAY_DIR)/system
OVERLAY_DATA_DIR := $(OVERLAY_DIR)/data

SHIM_URL := https://dl.fedoraproject.org/pub/fedora/linux/releases/43/Everything/x86_64/os/Packages/s/shim-x64-15.8-3.x86_64.rpm
GRUB2_EFI_URL := https://dl.fedoraproject.org/pub/fedora/linux/releases/43/Everything/x86_64/os/Packages/g/grub2-efi-x64-2.12-40.fc43.x86_64.rpm

# 
DIR_VARS := $(filter %_DIR,$(.VARIABLES)) $(O)
ALL_DIRS := $(foreach v,$(DIR_VARS),$($(v)))
$(ALL_DIRS):
	mkdir -p $@

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

KERNEL_ZIP := $(wildcard kernel-*-package.zip)
KERNEL_STAMP := $(KERNEL_DIR)/.stamp
$(KERNEL_STAMP): $(KERNEL_ZIP) | $(KERNEL_DIR)
	echo "解包内核文件:" $<
	unzip $< -d "$(BUILD_DIR)"
	tar -xzf $(BUILD_DIR)/kernel-*-zenith.tar.gz -C "$(KERNEL_DIR)"
	touch $@
	echo "解包内核文件:" "完成"
unpack_kenrel: $(KERNEL_STAMP)
.PHONY: unpack_kenrel

ISO_FILE := $(wildcard Bliss-*$(VER)*.iso)
ISO_STAMP := $(ISO_DIR)/.stamp
$(ISO_STAMP): $(ISO_FILE) | $(ISO_DIR)
	echo "解包ISO文件:" $<
	7z x "$<" -o"$(ISO_DIR)"
	touch $@
	echo "解包ISO文件:" "完成"
unpack_iso: $(ISO_STAMP)
.PHONY: unpack_iso

INITRD_STAMP := $(BUILD_DIR)/.initrd.stamp
$(INITRD_STAMP): $(ISO_STAMP) | $(INITRD_DIR)
	echo "解包initrd文件"
	zcat "$(ISO_DIR)/initrd.img" | (cd "$(INITRD_DIR)" && cpio -id)
	touch $@
	echo "解包initrd文件:" "完成"
unpack_initrd: $(INITRD_STAMP)
.PHONY: unpack_initrd

INITRD_PATCH_STAMP := $(BUILD_DIR)/.initrd.patch.stamp
$(INITRD_PATCH_STAMP): $(INITRD_STAMP) $(DEVICE_FILES_DIR)/initrd.patch
	echo "initrd 打补丁"
	patch -p1 < $(DEVICE_FILES_DIR)/initrd.patch -d "$(INITRD_DIR)"
	touch $@
	echo "initrd 打补丁:" "完成"
patch_initrd: $(INITRD_PATCH_STAMP)
.PHONY: patch_initrd

INITRD_FILE := $(BUILD_DIR)/initrd.cpio.gz
$(INITRD_FILE): $(INITRD_PATCH_STAMP)
	echo "initrd 打包"
	find "$(INITRD_DIR)" | cpio -o -H newc | gzip > "$(INITRD_FILE)"
	echo "initrd 打包:" "完成"
pack_initrd: $(INITRD_FILE)
.PHONY: pack_initrd

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
mount_boot: $(BOOT_FILE)
	$(MOUNT) -o loop "$<" "$(BOOT_DIR)"
umount_boot:
	$(UMOUNT) "$(BOOT_DIR)"
.PHONY: boot.img mount_boot umount_boot

DATA_FILE := $(IMAGES_DIR)/data.img
$(DATA_FILE): $(OVERLAY_DATA_DIR) | $(IMAGES_DIR) $(DATA_DIR)
	echo "打包data.img"
	if grep -q "$(DATA_DIR)" /proc/mounts;then $(UMOUNT) "$(DATA_DIR)";fi
	sudo truncate -s $(DATA_SIZE)M "$@"
	$(CHOWN) $(UID):$(GID) "$@"
	if command -v mkfs.f2fs &> /dev/null;then \
        echo "f2fs-tools found, using f2fs for data image."; \
        sudo mkfs.f2fs -l data -f "$@"; \
    else \
        echo "f2fs-tools not found, using ext4 for data image."; \
        sudo mkfs.ext4 -L data -s -F "$@"; \
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
mount_data: $(DATA_FILE)
	$(MOUNT) -o loop "$<" "$(DATA_DIR)"
umount_data:
	$(UMOUNT) "$(DATA_DIR)"
.PHONY: data.img mount_data umount_data

KEY_REMAP_PROG := $(BUILD_DIR)/key-remap
$(KEY_REMAP_PROG): $(DEVICE_FILES_DIR)/mipad2_keymap.c
	gcc -o $@ $< -static

SYSTEM_FILE := $(IMAGES_DIR)/system.img
SYSTEM_STAMP := $(BUILD_DIR)/system_$(VER).img
$(SYSTEM_STAMP): $(ISO_STAMP) | $(SYSTEM_DIR)
	echo "解包system.img"
	if [ -f "$(BUILD_DIR)/system.img" ]; then \
        rm "$(BUILD_DIR)/system.img"; \
    fi
	if [ -f "$(ISO_DIR)/system.sfs" ]; then \
        unsquashfs -d "$(BUILD_DIR)" "$(ISO_DIR)/system.sfs"; \
    elif [ -f "$(ISO_DIR)/system.efs" ]; then \
        fsck.erofs --extract="$(BUILD_DIR)/" "$(ISO_DIR)/system.efs"; \
    fi
	mv "$(BUILD_DIR)/system.img" "$@"
	echo "解包system.img:" "完成"
unpack_system: $(SYSTEM_STAMP)
$(SYSTEM_FILE): $(OVERLAY_SYSTEM_DIR) $(SYSTEM_STAMP) $(KERNEL_STAMP) $(KEY_REMAP_PROG) | $(SYSTEM_DIR) $(IMAGES_DIR)
	echo "修改system"
	if grep -q "$(SYSTEM_DIR)" /proc/mounts;then $(UMOUNT) "$(SYSTEM_DIR)";fi
	$(MOUNT) -o loop "$(SYSTEM_STAMP)" "$(SYSTEM_DIR)"
	$(INSTALL) -dm755 "$(SYSTEM_DIR)/system/lib/modules"
	$(CP) -r "$(KERNEL_DIR)/lib/modules/"* "$(SYSTEM_DIR)/system/lib/modules"
	$(INSTALL) -Dm755 "$(KEY_REMAP_PROG)" "$(SYSTEM_DIR)/system/bin/key-remap"
	cd "$(SYSTEM_DIR)"; if [ -f "$(OVERLAY_DIR)/system_modify.sh" ]; then sudo sh "$(OVERLAY_DIR)/system_modify.sh"; fi
	$(CP) -r "$(OVERLAY_SYSTEM_DIR)/"* "$(SYSTEM_DIR)" || echo OVERLAY_SYSTEM_DIR为空, 跳过复制.
	$(CHMOD) -R 755 "$(SYSTEM_DIR)/"
	echo "修改system:" "完成"
	echo "打包system.img"
	if command -v mkfs.erofs &> /dev/null;then \
        echo "erofs-utils found, using erofs for system image."; \
        mkfs.erofs -L system -zlzma "$@" "$(SYSTEM_DIR)"; \
    elif command -v mksquashfs &> /dev/null;then \
        echo "squashfs-tools found, using squashfs for system image."; \
        mksquashfs "$(SYSTEM_DIR)" "$@" -comp xz -Xcompression-level 19 -b 1M -Xdict-size 1M -noappend; \
    else \
        echo "erofs-utils and squashfs-tools not found, no package"; \
        sudo umount "$(SYSTEM_DIR)"; \
        cp "$BUILD_DIR/system.img" "$@"; \
    fi
	$(UMOUNT) "$(SYSTEM_DIR)" || true
	echo "打包system.img:" "完成"
pack_system system.img: $(SYSTEM_FILE)
mount_system: $(SYSTEM_FILE)
	$(MOUNT) -o loop "$<" "$(SYSTEM_DIR)"
umount_system:
	$(UMOUNT) "$(SYSTEM_DIR)"
.PHONY: unpack_system pack_system system.img mount_system umount_system

GPT_FILE := $(IMAGES_DIR)/gpt.bin
$(GPT_FILE): $(PWD)/gpt.ini | $(IMAGES_DIR)
	python3 gpt_ini2bin.py
gpt.bin: $(GPT_FILE)
.PHONY: gpt.bin

clean:
	rm -rf $(BUILD_DIR)
clean_images:
	rm -rf $(IMAGES_DIR)
clean_all: clean clean_images
	rm -rf $(SHIM_FILE) $(GRUB2_EFI_FILE)
.PHONY: clean clean_images clean_all

all: gpt.bin boot.img system.img data.img
.PHONY: all
