#!/bin/bash
set -e
# set -x
shopt -s expand_aliases

CURRENT_DIR=$(pwd)
BUILD_TMP=${CURRENT_DIR}/build_tmp
DEVICE_FILE_DIR=${CURRENT_DIR}/device_files
SYSTEM_PACCKAGE_FILE=$(ls uotanos-*.7z|head -n 1)

mkdir -p ${BUILD_TMP}

NORMAL_COLOR='\e[0m'
BLUE_COLOR='\e[1;34m'
GREEN_COLOR='\e[1;32m'
RED_COLOR="\e[1;31m"
YELLOW_COLOR='\e[1;33m'

info(){
    echo -e "${BLUE_COLOR}$@${NORMAL_COLOR}"
}

warning(){
    echo -e "${YELLOW_COLOR}$@${NORMAL_COLOR}"
}

error(){
    echo -e "${RED_COLOR}$@${NORMAL_COLOR}"
    exit 1
}

success(){
    echo -e "${GREEN_COLOR}$@${NORMAL_COLOR}"
}

is_mount() {
    if [ -z "$1" ]; then
        echo "Usage: is_mount <mount_point>"
        return 1
    fi
    grep "$1" /proc/mounts &>/dev/null
	return $?
}

gpt.bin(){
    info "Generating gpt.bin..."
    python3 gpt_ini2bin.py
    info "gpt.bin generated."
}

unpack_system_package(){
    if [ -d "${BUILD_TMP}/uotanos" ];then
        # rm -rf ${BUILD_TMP}/uotanos
        return
    fi
    if [ ! -f "${SYSTEM_PACCKAGE_FILE}" ];then
        error "System package file ${SYSTEM_PACCKAGE_FILE} not found!"
    fi
    info "Unpacking system package ${SYSTEM_PACCKAGE_FILE}..."
    7z x ${SYSTEM_PACCKAGE_FILE} -o${BUILD_TMP}
    info "Unpacking done."
}

unpack_ramdisk(){
    if [ ! -d "${BUILD_TMP}/uotanos" ];then
        warning "System package not found in build tmp, unpacking it first..."
        unpack_system_package
    fi
    if [ -d "${BUILD_TMP}/ramdisk" ];then
        rm -rf ${BUILD_TMP}/ramdisk
    fi
    ramdisk_img=$(ls ${BUILD_TMP}/uotanos/boot/ramdisk.img|head -n 1)
    if [ ! -z "${1}" ];then
        ramdisk_img=$(readlink -f ${1})
    fi
    if [ ! -f "${ramdisk_img}" ];then
        error "Ramdisk.img not found in system package!"
    fi
    info "Unpacking ramdisk.img..."
    pushd ${BUILD_TMP}
    mkdir -p ramdisk
    cd ramdisk
    gunzip -c ${ramdisk_img} | cpio -idmv
    popd
    info "Unpacking done."
}

config_ramdisk(){
    if [ ! -d "${BUILD_TMP}/ramdisk" ];then
        warning "Ramdisk not found in build tmp, unpacking it first..."
        unpack_ramdisk
    fi
    info "Configuring ramdisk..."
    pushd ${BUILD_TMP}/ramdisk
    rm -rf lib/firmware/{amdgpu,radeon,nvidia}

    mkdir -p lib/firmware/brcm
    pushd lib/firmware/brcm
    cp ${DEVICE_FILE_DIR}/BCM4356A2.hcd .
    mv brcmfmac4356-pcie.XiaomiInc-Mipad2.txt brcmfmac4356-pcie.XiaomiInc\ Mipad2.txt
    popd

    mkdir -p lib/firmware/intel
    pushd lib/firmware/intel
    cp ${DEVICE_FILE_DIR}/fw_sst_22a8.bin .
    mkdir -p ipu
    cp ${DEVICE_FILE_DIR}/shisp_2401a0_v21.bin ipu/
    popd

    popd
    info "Configuring done."
}

pack_ramdisk(){
    if [ ! -d "${BUILD_TMP}/ramdisk" ];then
        warning "Ramdisk not found in build tmp, unpacking it first..."
        unpack_ramdisk
        config_ramdisk
    fi
    OUTPUT_DIR=${DEVICE_FILE_DIR}/boot/EFI/ohos/ramdisk.img
    if [ ! -z "$1" ];then
        OUTPUT_DIR=$(readlink -f ${1})
    fi
    info "Packing ramdisk.img..."
    pushd ${BUILD_TMP}/ramdisk
    find . | cpio -o -H newc | gzip > ${OUTPUT_DIR}
    popd
    info "Packing done."
}

build_ramdisk(){
    unpack_ramdisk $1
    config_ramdisk
    pack_ramdisk $2
}

build_boot(){
    info "Building boot..."
    if [ ! -d "${CURRENT_DIR}/images" ];then
        warning "Images directory not found, creating it..."
        mkdir -p ${CURRENT_DIR}/images
    fi
    mkdir -p ${BUILD_TMP}/boot_mount
    if is_mount ${BUILD_TMP}/boot_mount;then
        umount ${BUILD_TMP}/boot_mount
    fi
    if [ -f "${CURRENT_DIR}/images/boot.img" ];then
        rm -f ${CURRENT_DIR}/images/boot.img
    fi

    echo "Creating boot.img..."
    truncate -s 256MiB ${CURRENT_DIR}/images/boot.img
    echo "Formatting boot.img..."
    mkfs.vfat -n BOOT -F 32 ${CURRENT_DIR}/images/boot.img
    
    echo "Mounting boot.img..."
    mount -o loop ${CURRENT_DIR}/images/boot.img ${BUILD_TMP}/boot_mount

    echo "Copying boot files..."
    cp -r ${DEVICE_FILE_DIR}/boot/* ${BUILD_TMP}/boot_mount/

    echo "Unmounting boot.img..."
    umount ${BUILD_TMP}/boot_mount
    info "Building boot done."
}

build_vendor(){
    info "Building vendor..."
    if [ ! -d "${BUILD_TMP}/uotanos" ];then
        warning "System package not found in build tmp, unpacking it first..."
        unpack_system_package
    fi
    if [ ! -d "${CURRENT_DIR}/images" ];then
        warning "Images directory not found, creating it..."
        mkdir -p ${CURRENT_DIR}/images
    fi

    mkdir -p ${BUILD_TMP}/vendor_mount
    if is_mount ${BUILD_TMP}/vendor_mount;then
        umount ${BUILD_TMP}/vendor_mount
    fi
    cp ${BUILD_TMP}/uotanos/vendor.img ${CURRENT_DIR}/images/vendor.img
    mount -o loop ${CURRENT_DIR}/images/vendor.img ${BUILD_TMP}/vendor_mount

    sed -i 's|/dev/block/sda4|/dev/block/mmcblk0p4|' ${BUILD_TMP}/vendor_mount/etc/fstab.x86_general

    umount ${BUILD_TMP}/vendor_mount
    info "Building vendor done."
}

build_system(){
    info "Building system..."
    if [ ! -d "${BUILD_TMP}/uotanos" ];then
        warning "System package not found in build tmp, unpacking it first..."
        unpack_system_package
    fi
    if [ ! -d "${CURRENT_DIR}/images" ];then
        warning "Images directory not found, creating it..."
        mkdir -p ${CURRENT_DIR}/images
    fi

    mkdir -p ${BUILD_TMP}/system_mount
    if is_mount ${BUILD_TMP}/system_mount;then
        umount ${BUILD_TMP}/system_mount
    fi
    cp ${BUILD_TMP}/uotanos/system.img ${CURRENT_DIR}/images/system.img
    mount -o loop ${CURRENT_DIR}/images/system.img ${BUILD_TMP}/system_mount

    # TODO: Add your customizations here

    umount ${BUILD_TMP}/system_mount
    info "Building system done."
}

build_images(){
    info "Building images..."
    gpt.bin

    unpack_system_package

    build_ramdisk
    build_ramdisk "${BUILD_TMP}/uotanos/用于调试的ramdisk/ramdisk.img" "${DEVICE_FILE_DIR}/boot/EFI/ohos/ramdisk_dbg.img"
    build_boot
    build_vendor
    build_system

    success "Building done."
}
all(){
    build_images
}

usage(){
    echo "Usage: $0 [options] subcommand [args...]"
    echo "Options:"
    echo "  -h, --help    Show this help message and exit"
    echo "Available subcommands:"
    echo "  build-image"
    echo "  unpack-system-package"
    echo "  unpack-ramdisk"
    echo "  config-ramdisk"
    echo "  pack-ramdisk"
    exit ${1:-0}
}

# ARGUMENT PARSING
paras=`getopt -o "h" -l "help" -n $(basename $0) -u -- "$@"` || usage 1
set -- $paras
while [ $1 ];do
    case "$1" in
        -h|--help) usage ;;
        --) shift; break ;;
        *) break ;;
    esac
    shift
done

if [ -n "$1" ];then
    subcommand=$1
    shift
    $subcommand "$@"
fi