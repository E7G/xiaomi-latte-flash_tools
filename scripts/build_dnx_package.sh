#!/usr/bin/env bash
set -Eeuo pipefail

repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${repo_root}"

kernel_pkg="$(find kernel-output -maxdepth 1 -name 'linux-latte-cachyos-*.pkg.tar.zst' -print -quit)"
[[ -n "${kernel_pkg}" ]] || { echo 'Kernel package not found' >&2; exit 1; }
install -Dm0644 "${kernel_pkg}" "device_files/$(basename "${kernel_pkg}")"

export KERNEL_PACKAGE="./device_files/$(basename "${kernel_pkg}")"
export ROOTFS_SIZE="${ROOTFS_SIZE:-8G}"
bash ./build_rootfs.sh

stage="${repo_root}/work/dnx-package"
out="${repo_root}/dist"
rm -rf "${stage}" "${out}"
mkdir -p "${stage}/images" "${stage}/device_files" "${out}"

install -m0644 images/gpt.bin images/xiaomi-latte-boot.img \
  images/xiaomi-latte-rootfs.img "${stage}/images/"
cp -a device_files/. "${stage}/device_files/"
install -m0644 DNX_flash_all.bat DNX_flash-boot.bat "${stage}/"
install -m0644 README.md "${stage}/README.md"

(
  cd "${stage}"
  find . -type f ! -name SHA256SUMS -print0 | sort -z | xargs -0 sha256sum > SHA256SUMS
)

archive="${out}/xiaomi-latte-cachyos-dnx-${GITHUB_RUN_NUMBER:-local}.tar.zst"
tar --sparse --zstd -cf "${archive}" -C "${stage}" .
sha256sum "${archive}" > "${archive}.sha256"
printf '%s\n' "${archive}" > "${out}/package-path"
