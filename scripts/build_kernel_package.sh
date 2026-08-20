#!/usr/bin/env bash
set -Eeuo pipefail

repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
work_dir="${repo_root}/work/kernel"
out_dir="${repo_root}/kernel-output"
source_repo="${KERNEL_REPO:-xiaomi-latte-dev/linux_latte}"
source_ref="${KERNEL_REF:-e89ea264f5ca311c9dca9088d964b80ec40472b4}"
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

pkgver="${kernel_release//-/_}"
pkgrel=1
installed_size="$(du -sb "${work_dir}/pkg/usr" | cut -f1)"
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
EOF

package="${out_dir}/${pkgbase}-${pkgver}-${pkgrel}-x86_64.pkg.tar.zst"
bsdtar --zstd -cf "${package}" -C "${work_dir}/pkg" .PKGINFO usr
pacman -Qp "${package}"
(cd "${out_dir}" && sha256sum "$(basename "${package}")" > "$(basename "${package}").sha256")
printf '%s\n' "${package}" > "${out_dir}/package-path"
