#!/usr/bin/env bash
set -Eeuo pipefail

repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
work_dir="${repo_root}/work/kernel"
out_dir="${repo_root}/kernel-output"
source_repo="${KERNEL_REPO:-E7G/linux_latte}"
source_ref="${KERNEL_COMMIT:-${KERNEL_REF:-cachyos-mipad2}}"
pkgbase="linux-latte-cachyos"
kernel_commit="${KERNEL_COMMIT:-}"
source_date_epoch="${SOURCE_DATE_EPOCH:-}"

[[ "${kernel_commit}" =~ ^[0-9a-f]{40}$ ]] || {
  echo "KERNEL_COMMIT must be a full 40-character SHA" >&2
  exit 1
}
[[ "${source_date_epoch}" =~ ^[0-9]+$ ]] && (( source_date_epoch > 0 )) || {
  echo "SOURCE_DATE_EPOCH must be a positive integer" >&2
  exit 1
}

pacman -Syu --noconfirm --needed \
  base-devel bc bison clang cpio curl flex git kmod libelf lld llvm \
  openssl pahole perl python rsync tar xz zstd

rm -rf "${work_dir}" "${out_dir}"
mkdir -p "${work_dir}/src" "${work_dir}/pkg/usr/lib/modules" "${out_dir}"

curl --fail --location --retry 5 \
  "https://github.com/${source_repo}/archive/${source_ref}.tar.gz" \
  | tar -xz --strip-components=1 -C "${work_dir}/src"

cd "${work_dir}/src"

# Accept only the two explicitly integrated kernel families, not arbitrary
# newer releases. The 7.2 package must not replace the stable 6.14 package.
version="$(sed -n 's/^VERSION[[:space:]]*=[[:space:]]*//p' Makefile)"
patchlevel="$(sed -n 's/^PATCHLEVEL[[:space:]]*=[[:space:]]*//p' Makefile)"
kernel_family="${version}.${patchlevel}"
case "$kernel_family" in
  6.14)
    expected_localversion='CONFIG_LOCALVERSION="-mipad2-cachyos"'
    localversion_suffix=''
    ;;
  7.2)
    grep -Eq '^SUBLEVEL[[:space:]]*=[[:space:]]*0$' Makefile
    pkgbase='linux-latte-integrated-7-2'
    expected_localversion='CONFIG_LOCALVERSION="-mipad2-integrated"'
    revision="${KERNEL_INTEGRATED_REVISION:-3}"
    [[ "$revision" =~ ^[1-9][0-9]*$ ]] || { echo 'Positive integrated revision required' >&2; exit 1; }
    localversion_suffix="-r${revision}"
    ;;
  *) echo 'Only integrated 6.14 and 7.2 kernel families are supported' >&2; exit 1 ;;
esac
python "${repo_root}/scripts/stage_kernel_support.py" \
  "${work_dir}/src" "${work_dir}/pkg" --dry-run >/dev/null
export KBUILD_BUILD_USER=github-actions
export KBUILD_BUILD_HOST=archlinux
export KBUILD_BUILD_TIMESTAMP="$(date -u -d "@${SOURCE_DATE_EPOCH:-0}" '+%a %b %d %T UTC %Y')"
build_flags=(LLVM=1 LLVM_IAS=1 LOCALVERSION="$localversion_suffix")

# CachyOS/BORE source and the Mi Pad 2 profile live in linux_latte's
# explicitly pinned integration branch. Build it directly; applying another patch/config
# overlay here would create an untracked second kernel variant.
make "${build_flags[@]}" xiaomipad2_defconfig

make "${build_flags[@]}" olddefconfig

sh fix_file/tests/mipad2-kernel-config-audit.sh .config

required=(
  "$expected_localversion"
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

# Stage tracked package sources from this exact kernel commit. makepkg's
# generated src/ directories do not exist in a clean GitHub source archive.
python "${repo_root}/scripts/stage_kernel_support.py" \
  "${work_dir}/src" "${work_dir}/pkg"

install -d "${work_dir}/pkg/usr/share/doc/${pkgbase}"
printf '%s\n' "${kernel_commit}" > "${work_dir}/pkg/usr/share/doc/${pkgbase}/source-commit"
printf '%s\n' "${source_repo}" > "${work_dir}/pkg/usr/share/doc/${pkgbase}/source-repository"
printf '%s\n' "${kernel_release}" > "${work_dir}/pkg/usr/share/doc/${pkgbase}/kernel-release"

source_stamp="$(date -u -d "@${source_date_epoch}" '+%Y%m%d%H%M%S')"
pkgver="${kernel_release//-/_}.r${source_stamp}.g${kernel_commit:0:12}"
pkgrel=1
installed_size="$(du -sb "${work_dir}/pkg" | cut -f1)"
cat > "${work_dir}/pkg/.PKGINFO" <<EOF
pkgname = ${pkgbase}
pkgbase = ${pkgbase}
pkgver = ${pkgver}-${pkgrel}
pkgdesc = Mi Pad 2 linux_latte kernel with CachyOS optimizations
url = https://github.com/${source_repo}
builddate = ${source_date_epoch}
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
printf '%s\n' "${pkgbase}" > "${out_dir}/pkgbase"
python "${repo_root}/scripts/resolve_kernel_artifact.py" create \
  --package "${package}" --source-commit "${kernel_commit}" \
  --output "${out_dir}/kernel-artifact.json"
