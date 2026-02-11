#!/bin/sh

SWAP_FILE=/data/swap.img
SWAP_SIZE=1G

if [ ! -f ${SWAP_FILE} ]; then
    echo "正在创建 ${SWAP_SIZE} 的 swap 文件: ${SWAP_FILE}"
    dd if=/dev/zero of=${SWAP_FILE} bs=${SWAP_SIZE} count=1 || { echo "创建失败"; exit 1; }
    chmod 600 ${SWAP_FILE}
    mkswap -L swap ${SWAP_FILE} || { echo "mkswap 失败，请确认系统支持"; exit 1; }
    echo 创建 ${SWAP_SIZE} ${SWAP_FILE} 文件成功
fi

if [ -f "${SWAP_FILE}" ] && ! grep -q "$(basename ${SWAP_FILE})" /proc/swaps; then
    swapon ${SWAP_FILE} && echo "Swap 已启用: ${SWAP_FILE}"
fi
