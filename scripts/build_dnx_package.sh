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
platform_archive="${repo_root}/work/platform-tools-windows.zip"
platform_unpack="${repo_root}/work/platform-tools-windows"
platform_url="${PLATFORM_TOOLS_URL:-https://dl.google.com/android/repository/platform-tools-latest-windows.zip}"
rm -rf "${stage}" "${out}" "${platform_unpack}"
mkdir -p "${stage}/images" "${stage}/device_files" "${out}"

install -m0644 images/gpt.bin images/xiaomi-latte-boot.img \
  images/xiaomi-latte-rootfs.img "${stage}/images/"
cp -a device_files/. "${stage}/device_files/"
install -m0644 DNX_flash_all.bat DNX_flash-boot.bat ONE_KEY_FLASH.bat \
  flash-one-click.ps1 "${stage}/"
install -m0644 README.md "${stage}/README.md"

echo 'Downloading official Android SDK Platform-Tools for Windows'
curl --fail --location --retry 5 --retry-all-errors \
  --output "${platform_archive}" "${platform_url}"
mkdir -p "${platform_unpack}"
bsdtar -xf "${platform_archive}" -C "${platform_unpack}"
[[ -f "${platform_unpack}/platform-tools/fastboot.exe" ]] || {
  echo 'Downloaded Platform-Tools package has no fastboot.exe' >&2
  exit 1
}
cp -a "${platform_unpack}/platform-tools" "${stage}/platform-tools"

(
  cd "${stage}"
  find . -type f ! -name SHA256SUMS -print0 | sort -z | xargs -0 sha256sum > SHA256SUMS
)

if [[ ${BUILD_DNX_TAR:-0} == 1 ]]; then
  archive="${out}/xiaomi-latte-cachyos-dnx-${GITHUB_RUN_NUMBER:-local}.tar.zst"
  tar --sparse --zstd -cf "${archive}" -C "${stage}" .
  (cd "${out}" && sha256sum "$(basename "${archive}")" > "$(basename "${archive}").sha256")
fi
bash ./scripts/build_usb_image.sh
printf '%s\n' "${stage}" > "${out}/package-path"
