#!/usr/bin/env bash
set -Eeuo pipefail

repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
work_dir="${repo_root}/work/kernel"
out_dir="${repo_root}/kernel-output"
source_repo="${KERNEL_REPO:-E7G/linux_latte}"
source_ref="${KERNEL_REF:-bc851227257b9d96f9d098459454d9bcc73e70e8}"
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
git apply --check "${repo_root}/kernel/0001-cachyos-base-6.14.patch"
git apply "${repo_root}/kernel/0001-cachyos-base-6.14.patch"
git apply --check "${repo_root}/kernel/0002-bore-cachy-6.14.patch"
git apply "${repo_root}/kernel/0002-bore-cachy-6.14.patch"

# linux_latte carries the newer RUN_TO_PARITY condition than vanilla 6.14.
# Port the one BORE hunk that therefore cannot be kept in the upstream patch.
python3 - <<'PY'
from pathlib import Path

path = Path("kernel/sched/fair.c")
text = path.read_text()
old = """\
\tif (sched_feat(RUN_TO_PARITY) && curr && curr->vlag == curr->deadline)
\t\treturn curr;
"""
new = """\
\tif (sched_feat(RUN_TO_PARITY) && curr && curr->vlag == curr->deadline)
#ifdef CONFIG_SCHED_BORE
\t\tif (!(likely(sched_bore) && likely(sched_burst_parity_threshold) &&
\t\t\tsched_burst_parity_threshold < cfs_rq->nr_queued))
#endif // CONFIG_SCHED_BORE
\t\treturn curr;
"""
if text.count(old) != 1:
    raise SystemExit("Unexpected linux_latte RUN_TO_PARITY implementation")
path.write_text(text.replace(old, new), newline="\n")
PY

cp arch/x86/configs/xiaomipad2_defconfig .config
scripts/kconfig/merge_config.sh -m .config "${repo_root}/kernel/latte-cachyos.config"

export KBUILD_BUILD_USER=github-actions
export KBUILD_BUILD_HOST=archlinux
export KBUILD_BUILD_TIMESTAMP="$(date -u -d "@${SOURCE_DATE_EPOCH:-0}" '+%a %b %d %T UTC %Y')"
build_flags=(LLVM=1 LLVM_IAS=1)

make "${build_flags[@]}" olddefconfig

required=(
  'CONFIG_LOCALVERSION="-latte-cachyos"'
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
