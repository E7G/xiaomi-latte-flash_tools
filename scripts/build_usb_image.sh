#!/usr/bin/env bash
set -Eeuo pipefail

repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${repo_root}"

boot_image=images/xiaomi-latte-boot.img
root_image=images/xiaomi-latte-rootfs.img
[[ -f $boot_image && -f $root_image ]] || {
  echo 'Boot/root filesystem images are missing' >&2
  exit 1
}
fsck.fat -vn "$boot_image"
btrfs check --readonly "$root_image"

out_dir=${USB_IMAGE_OUT_DIR:-dist}
name="xiaomi-latte-cachyos-kde-${GITHUB_RUN_NUMBER:-local}"
raw="${out_dir}/${name}.img"
compressed="${raw}.xz"
mkdir -p "$out_dir"
rm -f "$raw" "$compressed" "${compressed}.sha256"

sector_size=512
esp_start=2048
esp_sectors=$((256 * 1024 * 1024 / sector_size))
root_start=$((esp_start + esp_sectors))
root_bytes=$(stat -c %s "$root_image")
(( root_bytes % sector_size == 0 )) || {
  echo 'Root image size is not sector aligned' >&2
  exit 1
}
root_sectors=$((root_bytes / sector_size))
disk_sectors=$((root_start + root_sectors + 2048))

truncate -s $((disk_sectors * sector_size)) "$raw"
sgdisk --clear \
  --new=1:${esp_start}:$((root_start - 1)) --typecode=1:ef00 --change-name=1:boot \
  --new=2:${root_start}:$((root_start + root_sectors - 1)) --typecode=2:8300 --change-name=2:system \
  "$raw"
dd if="$boot_image" of="$raw" bs=$sector_size seek=$esp_start conv=notrunc,sparse status=progress
dd if="$root_image" of="$raw" bs=$sector_size seek=$root_start conv=notrunc,sparse status=progress
sgdisk --verify "$raw"

xz -T0 -6 --keep "$raw"
rm -f "$raw"
(cd "$out_dir" && sha256sum "$(basename "$compressed")" > "$(basename "$compressed").sha256")
printf '%s\n' "$compressed"
