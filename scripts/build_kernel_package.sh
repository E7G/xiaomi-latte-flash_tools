#!/usr/bin/env bash
set -Eeuo pipefail

repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
work_dir="${repo_root}/work/kernel"
out_dir="${repo_root}/kernel-output"
source_repo="${KERNEL_REPO:-E7G/linux_latte}"
source_ref="${KERNEL_COMMIT:-${KERNEL_REF:-cachyos-mipad2}}"
pkgbase="linux-latte-cachyos"

pacman -Syu --noconfirm --needed \
  base-devel bc bison clang cpio curl flex git kmod libelf lld llvm \
  openssl pahole perl python rsync tar xz zstd

rm -rf "${work_dir}" "${out_dir}"
mkdir -p "${work_dir}/src" "${work_dir}/pkg/usr/lib/modules" "${out_dir}"

curl --fail --location --retry 5 \
  "https://github.com/${source_repo}/archive/${source_ref}.tar.gz" \
  | tar -xz --strip-components=1 -C "${work_dir}/src"

cd "${work_dir}/src"
export KBUILD_BUILD_USER=github-actions
export KBUILD_BUILD_HOST=archlinux
export KBUILD_BUILD_TIMESTAMP="$(date -u -d "@${SOURCE_DATE_EPOCH:-0}" '+%a %b %d %T UTC %Y')"
build_flags=(LLVM=1 LLVM_IAS=1)

# CachyOS/BORE source and the Mi Pad 2 profile live in linux_latte's
# cachyos-mipad2 branch. Build it directly; applying another patch/config
# overlay here would create an untracked second kernel variant.
make "${build_flags[@]}" xiaomipad2_defconfig

make "${build_flags[@]}" olddefconfig

sh fix_file/tests/mipad2-kernel-config-audit.sh .config

required=(
  'CONFIG_LOCALVERSION="-mipad2-cachyos"'
  'CONFIG_MSILVERMONT=y'
  'CONFIG_CC_OPTIMIZE_FOR_PERFORMANCE_O3=y'
  'CONFIG_SCHED_BORE=y'
  'CONFIG_HZ_300=y'
  'CONFIG_PREEMPT=y'
  'CONFIG_LTO_CLANG_THIN=y'
  'CONFIG_IOSCHED_BFQ=y'
  'CONFIG_LRU_GEN_ENABLED=y'
  'CONFIG_BRCMFMAC=m'
  'CONFIG_BT_BCM=m'
  'CONFIG_VIDEO_OV5693=m'
  'CONFIG_VIDEO_T4KA3=m'
  'CONFIG_VIDEO_DW9719=m'
  'CONFIG_VIDEO_ATOMISP=m'
  'CONFIG_USB_CONFIGFS_ACM=y'
  'CONFIG_VFAT_FS=y'
  'CONFIG_NLS_CODEPAGE_437=y'
  'CONFIG_NLS_ASCII=y'
)
for option in "${required[@]}"; do
  grep -Fqx "${option}" .config || {
    echo "Required kernel option missing: ${option}" >&2
    exit 1
  }
done

jobs="${KERNEL_JOBS:-$(nproc)}"
make -j"${jobs}" "${build_flags[@]}"

kernel_release="$(make -s "${build_flags[@]}" kernelrelease)"
mod_dir="${work_dir}/pkg/usr/lib/modules/${kernel_release}"
make "${build_flags[@]}" INSTALL_MOD_PATH="${work_dir}/pkg/usr" \
  INSTALL_MOD_STRIP=1 DEPMOD=true modules_install
install -Dm0644 "$(make -s "${build_flags[@]}" image_name)" "${mod_dir}/vmlinuz"
install -Dm0644 .config "${mod_dir}/config"
printf '%s\n' "${pkgbase}" > "${mod_dir}/pkgbase"
rm -f "${mod_dir}/build" "${mod_dir}/source"

# Ship the exact support payload validated with this kernel.  Keeping this in
# the same package prevents a fresh DNX image from booting a new kernel with
# stale camera firmware, UCM routes, or USB debug helpers.
install -Dm0644 fix_file/packages/mipad2-camera-support/src/intel/ipu/shisp_2401a0_v21.bin \
  "${work_dir}/pkg/usr/lib/firmware/intel/ipu/shisp_2401a0_v21.bin"
install -Dm0644 fix_file/packages/mipad2-camera-support/src/mipad2-camera.conf \
  "${work_dir}/pkg/etc/modules-load.d/mipad2-camera.conf"
install -Dm0644 fix_file/brcmfmac4356-pcie.Xiaomi\ Inc-Mipad2.txt \
  "${work_dir}/pkg/usr/lib/firmware/brcm/brcmfmac4356-pcie.Xiaomi Inc-Mipad2.txt"
install -Dm0644 fix_file/BCM4356A2.hcd \
  "${work_dir}/pkg/usr/lib/firmware/brcm/BCM4356A2.hcd"

install -Dm0644 fix_file/packages/mipad2-alsa-ucm/src/cht-bsw-rt5659/cht-bsw-rt5659.conf \
  "${work_dir}/pkg/usr/share/alsa/ucm2/conf.d/cht-bsw-rt5659/cht-bsw-rt5659.conf"
install -Dm0644 fix_file/packages/mipad2-alsa-ucm/src/cht-bsw-rt5659/HiFi.conf \
  "${work_dir}/pkg/usr/share/alsa/ucm2/conf.d/cht-bsw-rt5659/HiFi.conf"

install -Dm0755 fix_file/packages/mipad2-usb-serial/src/mipad2-usb-serial \
  "${work_dir}/pkg/usr/local/libexec/mipad2-usb-serial"
install -Dm0644 fix_file/packages/mipad2-usb-serial/src/mipad2-usb-serial.service \
  "${work_dir}/pkg/etc/systemd/system/mipad2-usb-serial.service"
install -Dm0755 fix_file/packages/mipad2-recovery/src/mp2-backup \
  "${work_dir}/pkg/usr/local/sbin/mp2-backup"
install -Dm0755 fix_file/packages/mipad2-recovery/src/mp2-recover \
  "${work_dir}/pkg/usr/local/sbin/mp2-recover"
install -Dm0755 fix_file/packages/mipad2-test-no-idle/src/mp2-test-no-idle \
  "${work_dir}/pkg/usr/local/sbin/mp2-test-no-idle"
install -Dm0644 fix_file/packages/mipad2-test-no-idle/src/mipad2-test-no-idle.service \
  "${work_dir}/pkg/etc/systemd/system/mipad2-test-no-idle.service"
install -Dm0755 fix_file/tests/mipad2-hardware-smoke.sh \
  "${work_dir}/pkg/usr/local/libexec/mipad2-hardware-smoke"
install -Dm0644 fix_file/tests/mipad2-hardware-audit.service \
  "${work_dir}/pkg/etc/systemd/system/mipad2-hardware-audit.service"

pkgver="${kernel_release//-/_}"
pkgrel=1
installed_size="$(du -sb "${work_dir}/pkg" | cut -f1)"
cat > "${work_dir}/pkg/.PKGINFO" <<EOF
pkgname = ${pkgbase}
pkgbase = ${pkgbase}
pkgver = ${pkgver}-${pkgrel}
pkgdesc = Mi Pad 2 linux_latte kernel with CachyOS optimizations
url = https://github.com/${source_repo}
builddate = $(date +%s)
packager = GitHub Actions
size = ${installed_size}
arch = x86_64
license = GPL-2.0-only
depend = coreutils
depend = kmod
optdepend = wireless-regdb: regulatory database
optdepend = timeshift: mp2-backup snapshot support
optdepend = v4l-utils: camera topology and smoke tests
EOF

package="${out_dir}/${pkgbase}-${pkgver}-${pkgrel}-x86_64.pkg.tar.zst"
bsdtar --zstd -cf "${package}" -C "${work_dir}/pkg" .PKGINFO etc usr
pacman -Qp "${package}"
(cd "${out_dir}" && sha256sum "$(basename "${package}")" > "$(basename "${package}").sha256")
printf '%s\n' "${package}" > "${out_dir}/package-path"
